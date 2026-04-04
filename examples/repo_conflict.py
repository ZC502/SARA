"""
Disaster Demo: repo conflict
============================

This demo shows that SARA/SIPA is not just a file auditor.
It can also reason about order-sensitive repository actions.

Scenario:
- Intent A: git push --force on the repo
- Intent B: git commit a hotfix on the same repo

Run:
    python examples/repo_conflict.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sipa_core.auditor_v3 import LogicalResidualAuditor


def pretty_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False)


def print_banner():
    print("=" * 68)
    print("SARA  |  Safe Action Residual Arbiter")
    print("SIPA Core  |  Sequential Intent & Planning Auditor")
    print("=" * 68)
    print("Scenario: git push --force vs git commit")
    print()


def print_report(report):
    print("[Audit Result]")
    print(f"severity              : {report.severity}")
    print(f"logical_residual      : {report.logical_residual:.4f}")
    print(f"commutative_residual  : {report.commutative_residual:.4f}")
    print(f"intent_collision_rate : {report.intent_collision_rate:.4f}")
    print(f"context_pressure      : {report.context_pressure:.4f}")

    if report.reasons:
        print("reasons               :")
        for reason in report.reasons:
            print(f"  - {reason}")

    if report.actionable_advice:
        print("actionable_advice     :")
        for tip in report.actionable_advice:
            print(f"  - {tip}")

    print()
    print("[Predicted A -> B]")
    print(pretty_json(report.state_ab))
    print()
    print("[Predicted B -> A]")
    print(pretty_json(report.state_ba))
    print()


def main():
    print_banner()

    context = {
        "resources": {
            "/repos/app": {
                "exists": True,
                "backed_up": False,
                "synced": True,
                "renamed_to": None,
                "writes": 0,
                "local_commits": 0,
                "history_rewritten": False,
                "last_actor": None,
            }
        },
        "role": "devops-assistant",
        "tokens_used": 3100,
        "max_window": 16000,
    }

    intent_a = {
        "actor": "lead_dev",
        "action": "force_push",
        "resource": "/repos/app",
        "content": "git push --force origin main",
        "destructive": True,
        "tool": "git",
    }

    intent_b = {
        "actor": "hotfix_dev",
        "action": "commit",
        "resource": "/repos/app",
        "content": "git commit -m 'hotfix: patch login flow'",
        "destructive": False,
        "tool": "git",
    }

    auditor = LogicalResidualAuditor(
        warn_threshold=0.35,
        block_threshold=0.70,
    )

    report = auditor.audit_pair(intent_a, intent_b, context)
    print_report(report)

    if report.severity == "BLOCK":
        print("[SIPA] FUSE_BLOWN: REPOSITORY STATE AT RISK")
        print("Potential consequence: history rewrite may invalidate or discard pending local work.")
    elif report.severity == "WARN":
        print("[SIPA] WARN")
        print("Order-sensitive repo conflict detected. Human review recommended.")
    else:
        print("[SIPA] SAFE")
        print("No fuse condition detected.")


if __name__ == "__main__":
    main()
