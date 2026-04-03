"""
SIPA Core - Logical Residual Auditor
===================================

Alpha-purpose residual engine for SARA / SIPA Core.

Core idea
---------
Logical Residual measures how much predicted system state diverges when
the execution order of intents is swapped.

    R_logic = d( Φ(s, A, B), Φ(s, B, A) )

Design goals
------------
- framework-agnostic
- no OpenClaw dependency
- no LLM dependency
- stdlib only
- easy to plug into demos first, adapters later
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import copy
import posixpath
import re


Context = Dict[str, Any]
IntentLike = Union[str, Dict[str, Any], "Intent"]


# ============================================================
# Data models
# ============================================================

@dataclass
class Intent:
    actor: str
    action: str
    resource: str
    target: Optional[str] = None
    role: Optional[str] = None
    tool: Optional[str] = None
    content: Optional[str] = None
    destructive: bool = False
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PredictedState:
    resources: Dict[str, Dict[str, Any]]
    touched_resources: List[str]
    irreversible_ops: int
    warnings: List[str]
    role: Optional[str]
    tokens_used: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LogicalResidualReport:
    intent_a: Dict[str, Any]
    intent_b: Dict[str, Any]
    state_ab: Dict[str, Any]
    state_ba: Dict[str, Any]
    commutative_residual: float
    intent_collision_rate: float
    context_pressure: float
    logical_residual: float
    severity: str
    reasons: List[str]
    actionable_advice: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# Normalization helpers
# ============================================================

_DELETE_PATTERNS = [
    r"\brm\s+-rf\s+([^\s]+)",
    r"\bdelete\s+([^\s]+)",
    r"\bremove\s+([^\s]+)",
    r"\bdrop\s+table\s+([^\s]+)",
    r"\btruncate\s+table\s+([^\s]+)",
]

_BACKUP_PATTERNS = [
    r"\bbackup\s+([^\s]+)",
    r"\bsync_to_cloud\(([^)]+)\)",
    r"\bsync\s+([^\s]+)",
    r"\bcopy\s+([^\s]+)\s+to\s+([^\s]+)",
]

_RENAME_PATTERNS = [
    r"\brename\s+([^\s]+)\s+to\s+([^\s]+)",
    r"\bmv\s+([^\s]+)\s+([^\s]+)",
]

_WRITE_PATTERNS = [
    r"\bwrite\s+([^\s]+)",
    r"\bmodify\s+([^\s]+)",
    r"\bupdate\s+([^\s]+)",
    r"\bedit\s+([^\s]+)",
]

_READ_PATTERNS = [
    r"\bread\s+([^\s]+)",
    r"\binspect\s+([^\s]+)",
    r"\bsummarize\s+([^\s]+)",
    r"\bopen\s+([^\s]+)",
]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _norm_action(action: str) -> str:
    action = action.strip().lower()
    aliases = {
        "rm": "delete",
        "rm -rf": "delete",
        "remove": "delete",
        "drop": "delete",
        "truncate": "delete",
        "cp": "backup",
        "copy": "backup",
        "sync_to_cloud": "backup",
        "sync": "backup",
        "mv": "rename",
        "edit": "write",
        "update": "write",
        "modify": "write",
        "open": "read",
        "inspect": "read",
        "summarize": "read",
    }
    return aliases.get(action, action)


def _normalize_resource_path(resource: str) -> str:
    """
    Normalize resource paths conservatively using POSIX rules.

    Examples:
    - "/data/logs/" -> "/data/logs"
    - "data/logs"   -> "/data/logs"
    - ""            -> "unknown"
    """
    if not resource:
        return "unknown"

    text = str(resource).strip().strip('"').strip("'")
    if text in {".", "", "unknown"}:
        return "unknown"

    if "://" in text:
        return text.rstrip("/") or text

    normalized = posixpath.normpath(text)
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    return normalized


def _same_parent_path(a: str, b: str) -> bool:
    if a == "unknown" or b == "unknown":
        return False
    return posixpath.dirname(a) == posixpath.dirname(b)


def _is_ancestor_or_descendant(a: str, b: str) -> bool:
    """
    True if a contains b or b contains a at directory boundaries.
    Avoids false positives like /data vs /data1.
    """
    if a == "unknown" or b == "unknown":
        return False
    if a == b:
        return False

    a_prefix = a.rstrip("/") + "/"
    b_prefix = b.rstrip("/") + "/"
    return a_prefix.startswith(b_prefix) or b_prefix.startswith(a_prefix)


def _resource_relation_label(a: str, b: str) -> str:
    if a == "unknown" or b == "unknown":
        return "none"
    if a == b:
        return "same"
    if _is_ancestor_or_descendant(a, b):
        return "hierarchical"
    if _same_parent_path(a, b):
        return "sibling"
    return "none"


def _resource_from_match(groups: Tuple[str, ...]) -> Tuple[str, Optional[str]]:
    if not groups:
        return "unknown", None
    if len(groups) == 1:
        return _normalize_resource_path(groups[0]), None
    resource = _normalize_resource_path(groups[0])
    target = groups[1].strip('"').strip("'")
    if "://" not in target:
        target = _normalize_resource_path(target)
    return resource, target


def _parse_intent_string(text: str) -> Intent:
    raw = text.strip()
    lower = raw.lower()

    for pattern in _DELETE_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            resource, target = _resource_from_match(m.groups())
            return Intent(
                actor="unknown",
                action="delete",
                resource=resource,
                target=target,
                content=raw,
                destructive=True,
            )

    for pattern in _BACKUP_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            resource, target = _resource_from_match(m.groups())
            return Intent(
                actor="unknown",
                action="backup",
                resource=resource,
                target=target,
                content=raw,
                destructive=False,
            )

    for pattern in _RENAME_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            resource, target = _resource_from_match(m.groups())
            return Intent(
                actor="unknown",
                action="rename",
                resource=resource,
                target=target,
                content=raw,
                destructive=False,
            )

    for pattern in _WRITE_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            resource, target = _resource_from_match(m.groups())
            return Intent(
                actor="unknown",
                action="write",
                resource=resource,
                target=target,
                content=raw,
                destructive=False,
            )

    for pattern in _READ_PATTERNS:
        m = re.search(pattern, lower)
        if m:
            resource, target = _resource_from_match(m.groups())
            return Intent(
                actor="unknown",
                action="read",
                resource=resource,
                target=target,
                content=raw,
                destructive=False,
            )

    return Intent(
        actor="unknown",
        action="unknown",
        resource="unknown",
        content=raw,
        destructive=False,
    )


def normalize_intent(intent: IntentLike) -> Intent:
    if isinstance(intent, Intent):
        normalized = copy.deepcopy(intent)
        normalized.action = _norm_action(normalized.action)
        normalized.resource = _normalize_resource_path(normalized.resource)
        if normalized.target and "://" not in normalized.target:
            normalized.target = _normalize_resource_path(normalized.target)
        normalized.destructive = normalized.destructive or normalized.action == "delete"
        return normalized

    if isinstance(intent, str):
        return _parse_intent_string(intent)

    if isinstance(intent, dict):
        resource = _normalize_resource_path(intent.get("resource", "unknown"))
        target = intent.get("target")
        if target and "://" not in str(target):
            target = _normalize_resource_path(str(target))

        normalized = Intent(
            actor=intent.get("actor", "unknown"),
            action=_norm_action(intent.get("action", "unknown")),
            resource=resource,
            target=target,
            role=intent.get("role"),
            tool=intent.get("tool"),
            content=intent.get("content"),
            destructive=bool(intent.get("destructive", False)),
            metadata=intent.get("metadata"),
        )
        if normalized.action == "delete":
            normalized.destructive = True
        return normalized

    raise TypeError(f"Unsupported intent type: {type(intent)!r}")


# ============================================================
# Predictor
# ============================================================

class FastPredictor:
    """
    Lightweight execution predictor.

    It does not try to be semantically complete.
    It only needs to be directionally useful for:
    - resource clashes
    - destructive order asymmetry
    - role drift pressure
    - action side-effect divergence
    """

    _ACTION_TOKEN_COST = {
        "delete": 190,
        "backup": 165,
        "rename": 135,
        "write": 145,
        "read": 80,
        "unknown": 110,
    }

    def clone_context(self, context: Optional[Context]) -> Context:
        if context is None:
            context = {}
        cloned = copy.deepcopy(context)
        cloned.setdefault("resources", {})
        cloned.setdefault("role", None)
        cloned.setdefault("tokens_used", 0)
        cloned.setdefault("max_window", 16000)
        return cloned

    def estimate_token_cost(self, intent: Intent) -> int:
        """
        Dynamic but deterministic token estimate.
        Keeps alpha runs reproducible while giving more realistic pressure than
        a fixed constant.
        """
        base = self._ACTION_TOKEN_COST.get(intent.action, self._ACTION_TOKEN_COST["unknown"])

        content_bonus = 0
        if intent.content:
            content_bonus += min(len(intent.content) // 12, 55)

        metadata_bonus = 15 if intent.metadata else 0
        tool_bonus = 12 if intent.tool else 0
        role_bonus = 10 if intent.role else 0
        destructive_bonus = 25 if intent.destructive else 0

        return int(base + content_bonus + metadata_bonus + tool_bonus + role_bonus + destructive_bonus)

    def apply_intent(self, context: Context, intent: Intent) -> Context:
        ctx = self.clone_context(context)
        resources = ctx["resources"]
        resource_state = copy.deepcopy(resources.get(intent.resource, {
            "exists": True,
            "backed_up": False,
            "synced": False,
            "renamed_to": None,
            "writes": 0,
            "last_actor": None,
        }))

        warnings = ctx.setdefault("warnings", [])
        touched = ctx.setdefault("touched_resources", [])
        irreversible_ops = int(ctx.get("irreversible_ops", 0))

        touched.append(intent.resource)
        resource_state["last_actor"] = intent.actor

        if intent.role:
            ctx["role"] = intent.role

        ctx["tokens_used"] = int(ctx.get("tokens_used", 0)) + self.estimate_token_cost(intent)

        if intent.action == "delete":
            if resource_state.get("backed_up", False):
                warnings.append(f"destructive delete after backup on {intent.resource}")
            resource_state["exists"] = False
            irreversible_ops += 1

        elif intent.action == "backup":
            if not resource_state.get("exists", True):
                warnings.append(f"backup attempted after missing resource: {intent.resource}")
            else:
                resource_state["backed_up"] = True
                resource_state["synced"] = True

        elif intent.action == "rename":
            if not resource_state.get("exists", True):
                warnings.append(f"rename attempted on missing resource: {intent.resource}")
            else:
                resource_state["renamed_to"] = intent.target or f"{intent.resource}.renamed"
                resource_state["exists"] = True

        elif intent.action == "write":
            if not resource_state.get("exists", True):
                warnings.append(f"write attempted on missing resource: {intent.resource}")
            else:
                resource_state["writes"] = int(resource_state.get("writes", 0)) + 1

        elif intent.action == "read":
            if not resource_state.get("exists", True):
                warnings.append(f"read attempted on missing resource: {intent.resource}")

        else:
            warnings.append(f"unknown action: {intent.action}")

        resources[intent.resource] = resource_state
        ctx["resources"] = resources
        ctx["irreversible_ops"] = irreversible_ops
        return ctx

    def predict(self, context: Optional[Context], intents: Sequence[IntentLike]) -> PredictedState:
        ctx = self.clone_context(context)

        for raw_intent in intents:
            intent = normalize_intent(raw_intent)
            ctx = self.apply_intent(ctx, intent)

        return PredictedState(
            resources=copy.deepcopy(ctx["resources"]),
            touched_resources=list(dict.fromkeys(ctx.get("touched_resources", []))),
            irreversible_ops=int(ctx.get("irreversible_ops", 0)),
            warnings=list(ctx.get("warnings", [])),
            role=ctx.get("role"),
            tokens_used=int(ctx.get("tokens_used", 0)),
        )


# ============================================================
# Residual metrics
# ============================================================

class LogicalResidualAuditor:
    def __init__(
        self,
        predictor: Optional[FastPredictor] = None,
        warn_threshold: float = 0.35,
        block_threshold: float = 0.70,
    ) -> None:
        self.predictor = predictor or FastPredictor()
        self.warn_threshold = warn_threshold
        self.block_threshold = block_threshold

    def _resource_conflict_score(self, a: Intent, b: Intent) -> float:
        relation = _resource_relation_label(a.resource, b.resource)
        destructive_pair = a.destructive or b.destructive
        both_write_like = (
            a.action in {"delete", "write", "rename", "backup"}
            and b.action in {"delete", "write", "rename", "backup"}
        )

        score = 0.0

        if relation == "same":
            score += 0.45
        elif relation == "hierarchical":
            score += 0.35
        elif relation == "sibling":
            score += 0.18

        if relation in {"same", "hierarchical"} and destructive_pair:
            score += 0.25

        if relation in {"same", "hierarchical"} and a.action == "delete" and b.action in {"backup", "rename", "write", "read"}:
            score += 0.20

        if relation in {"same", "hierarchical"} and b.action == "delete" and a.action in {"backup", "rename", "write", "read"}:
            score += 0.20

        if relation in {"same", "hierarchical", "sibling"} and both_write_like:
            score += 0.12

        return _clamp(score)

    def _context_pressure(self, context: Optional[Context]) -> float:
        if not context:
            return 0.0
        tokens_used = float(context.get("tokens_used", 0))
        max_window = float(context.get("max_window", 16000))
        if max_window <= 0:
            return 0.0
        return _clamp(tokens_used / max_window)

    def _resource_state_distance(self, state_ab: PredictedState, state_ba: PredictedState) -> float:
        resource_names = set(state_ab.resources.keys()) | set(state_ba.resources.keys())
        if not resource_names:
            return 0.0

        total = 0.0
        for name in resource_names:
            a = state_ab.resources.get(name, {})
            b = state_ba.resources.get(name, {})

            local = 0.0
            local += 0.35 if a.get("exists", True) != b.get("exists", True) else 0.0
            local += 0.20 if bool(a.get("backed_up", False)) != bool(b.get("backed_up", False)) else 0.0
            local += 0.15 if bool(a.get("synced", False)) != bool(b.get("synced", False)) else 0.0
            local += 0.15 if (a.get("renamed_to") or "") != (b.get("renamed_to") or "") else 0.0

            write_gap = abs(int(a.get("writes", 0)) - int(b.get("writes", 0)))
            local += min(write_gap * 0.10, 0.15)

            total += _clamp(local)

        return _clamp(total / len(resource_names))

    def _warning_distance(self, state_ab: PredictedState, state_ba: PredictedState) -> float:
        wa = set(state_ab.warnings)
        wb = set(state_ba.warnings)
        if not wa and not wb:
            return 0.0
        union = wa | wb
        inter = wa & wb
        return _clamp(1.0 - (len(inter) / max(1, len(union))))

    def _role_distance(self, state_ab: PredictedState, state_ba: PredictedState) -> float:
        return 1.0 if state_ab.role != state_ba.role else 0.0

    def _irreversible_distance(self, state_ab: PredictedState, state_ba: PredictedState) -> float:
        gap = abs(state_ab.irreversible_ops - state_ba.irreversible_ops)
        return _clamp(gap / 2.0)

    def _commutative_residual(self, state_ab: PredictedState, state_ba: PredictedState) -> float:
        resource_distance = self._resource_state_distance(state_ab, state_ba)
        warning_distance = self._warning_distance(state_ab, state_ba)
        role_distance = self._role_distance(state_ab, state_ba)
        irreversible_distance = self._irreversible_distance(state_ab, state_ba)

        residual = (
            0.45 * resource_distance
            + 0.20 * warning_distance
            + 0.15 * role_distance
            + 0.20 * irreversible_distance
        )
        return _clamp(residual)

    def _severity(self, logical_residual: float, reasons: List[str]) -> str:
        if logical_residual >= self.block_threshold:
            return "BLOCK"
        if logical_residual >= self.warn_threshold:
            return "WARN"
        if reasons and "destructive order asymmetry" in reasons:
            return "WARN"
        return "SAFE"

    def _actionable_advice(self, severity: str, a: Intent, b: Intent, reasons: List[str]) -> List[str]:
        advice: List[str] = []
        relation = _resource_relation_label(a.resource, b.resource)

        if severity == "BLOCK":
            advice.append(
                f"Critical conflict around {a.resource if a.resource != 'unknown' else 'the target resource'}. "
                "Suggest sequential isolation before execution."
            )
            advice.append("Require explicit human confirmation before any destructive action proceeds.")
            if "destructive order asymmetry" in reasons:
                advice.append("Try manual re-ordering so protective actions run before destructive actions.")
            if relation == "hierarchical":
                advice.append("Inspect parent-child path overlap. One action may invalidate the other's subtree.")
        elif severity == "WARN":
            advice.append("Potential order-sensitive conflict detected. Review action order before execution.")
            if relation in {"same", "hierarchical"}:
                advice.append("Consider locking the shared resource scope to avoid concurrent writes.")
        else:
            advice.append("No immediate fuse condition detected. Continue with normal monitoring.")

        return advice

    def audit_pair(
        self,
        intent_a: IntentLike,
        intent_b: IntentLike,
        current_context: Optional[Context] = None,
    ) -> LogicalResidualReport:
        a = normalize_intent(intent_a)
        b = normalize_intent(intent_b)

        state_ab = self.predictor.predict(current_context, [a, b])
        state_ba = self.predictor.predict(current_context, [b, a])

        commutative_residual = self._commutative_residual(state_ab, state_ba)
        icr = self._resource_conflict_score(a, b)
        cp = self._context_pressure(current_context)

        logical_residual = _clamp(
            0.60 * commutative_residual
            + 0.30 * icr
            + 0.10 * cp
        )

        reasons: List[str] = []
        relation = _resource_relation_label(a.resource, b.resource)

        if relation == "same":
            reasons.append("shared resource target")
        elif relation == "hierarchical":
            reasons.append("hierarchical resource overlap")
        elif relation == "sibling":
            reasons.append("shared parent resource scope")

        if a.destructive != b.destructive and relation in {"same", "hierarchical"}:
            reasons.append("destructive order asymmetry")

        if state_ab.resources != state_ba.resources:
            reasons.append("predicted end-state divergence")

        if state_ab.warnings != state_ba.warnings:
            reasons.append("side-effect warning divergence")

        if cp >= 0.80:
            reasons.append("high context pressure")

        severity = self._severity(logical_residual, reasons)
        actionable_advice = self._actionable_advice(severity, a, b, reasons)

        return LogicalResidualReport(
            intent_a=a.to_dict(),
            intent_b=b.to_dict(),
            state_ab=state_ab.to_dict(),
            state_ba=state_ba.to_dict(),
            commutative_residual=round(commutative_residual, 4),
            intent_collision_rate=round(icr, 4),
            context_pressure=round(cp, 4),
            logical_residual=round(logical_residual, 4),
            severity=severity,
            reasons=reasons,
            actionable_advice=actionable_advice,
        )

    def associative_residual(
        self,
        prior_intents: Sequence[IntentLike],
        new_intent: IntentLike,
        current_context: Optional[Context] = None,
    ) -> float:
        """
        Approximate associative residual for long-running sessions.

        This is a pragmatic MVP metric:
        1. simulate detailed prior path + new intent
        2. compress prior path into a coarse summary state
        3. compare applying new intent to the compressed state

        It is not a formal algebraic associator. It is an engineering proxy
        for context collapse / role drift / summary-loss risk.
        """
        normalized_prior = [normalize_intent(x) for x in prior_intents]
        normalized_new = normalize_intent(new_intent)

        detailed = self.predictor.predict(current_context, normalized_prior + [normalized_new])

        compressed_context = self.predictor.clone_context(current_context)
        compressed_context["tokens_used"] = compressed_context.get("tokens_used", 0) + 0.65 * len(normalized_prior) * 120

        latest_by_resource: Dict[str, Intent] = {}
        for intent in normalized_prior:
            latest_by_resource[intent.resource] = intent

        compressed_prior = list(latest_by_resource.values())
        compressed = self.predictor.predict(compressed_context, compressed_prior + [normalized_new])

        return round(self._commutative_residual(detailed, compressed), 4)


# ============================================================
# Convenience function
# ============================================================

def compute_logical_residual(
    intent_a: IntentLike,
    intent_b: IntentLike,
    current_context: Optional[Context] = None,
) -> Dict[str, Any]:
    auditor = LogicalResidualAuditor()
    return auditor.audit_pair(intent_a, intent_b, current_context).to_dict()


# ============================================================
# Example usage
# ============================================================

if __name__ == "__main__":
    context = {
        "resources": {
            "/data/logs": {"exists": True, "backed_up": False, "synced": False, "writes": 0},
        },
        "role": "ops-assistant",
        "tokens_used": 2400,
        "max_window": 16000,
    }

    a = {"actor": "user_a", "action": "delete", "resource": "/data"}
    b = {"actor": "user_b", "action": "backup", "resource": "/data/logs"}

    report = compute_logical_residual(a, b, context)

    import json
    print(json.dumps(report, indent=2))
