# SARA: Safe Action Residual Arbiter
*The Logic Circuit Breaker for AI Agents.*

SARA is a pre-execution safety middleware for AI agents.  
It uses **SIPA Core** — the **Sequential Intent & Planning Auditor** — to measure **Logical Residuals** between candidate action orders before irreversible tool calls execute.

Instead of asking only **"Who has permission?"**, SARA asks:

> **"Does this sequence of actions still make sense after execution order changes?"**

When the answer is no, SARA raises a warning or blocks execution before the agent damages state, loses context, or enters a destructive correction loop.

---

## Why SARA?

Traditional security layers are good at access control:

- Who can delete a database?
- Who can write to a repository?
- Who can modify a config?

But they usually do **not** answer a more dangerous question:

- What happens if the agent executes **A → B** instead of **B → A**?

SARA focuses on this **logic gap**.

Before an agent performs any irreversible action — such as deleting data, rewriting history, renaming critical paths, or sending messages — SARA previews multiple execution orders and measures whether the resulting states diverge.

If the divergence is large enough, SARA triggers a **logic fuse**.

---

## Core Intuition

If **RBAC** is the key to the gate, then **SARA** is the fuse in the circuit.

When a planned action sequence generates irreversible logical sparks:

$$
R_{logic} > \text{Threshold}
$$

SARA intervenes before disaster happens.

---

## The Math

The core of SARA is the **Logical Residual**:

$$
R_{logic} = \| \Phi(s, A, B) - \Phi(s, B, A) \|
$$

Where:

- $s$ = current system context
- $A, B$ = candidate actions or intents
- $\Phi$ = lightweight execution predictor

In plain language:

- run the predicted world as **A → B**
- run the predicted world as **B → A**
- compare the two end states

If the difference is large, the action pair is **order-sensitive** and potentially unsafe.It quantifies the non-commutative nature of agent actions

---

## What SIPA Core Does

**SIPA Core** stands for **Sequential Intent & Planning Auditor**.

It is the deterministic residual engine inside SARA.

SIPA Core currently models:

- **Logical Residual**: end-state divergence between alternate action orders
- **Intent Collision Rate**: resource overlap and destructive interaction strength
- **Context Pressure**: approximate pressure from growing execution context
- **Actionable Advice**: recovery-oriented guidance when risk is elevated

SIPA Core is designed to stay:

- lightweight
- deterministic
- stdlib-only
- framework-agnostic

It does **not** rely on external LLM calls to make safety decisions.

---

### Use Case 1 — Parent Delete vs Child Backup

**Scenario:** a parent path is deleted while a child path is being backed up.

- **Action A**: `rm -rf /data`
- **Action B**: `backup /data/logs`

A normal resource lock may miss the full semantic risk.  
SARA detects that deleting the parent path invalidates the child backup path and raises a high-risk warning before execution.

### Run

```bash
python examples/db_disaster_v2.py
```
**What this demonstrates**
- hierarchical resource overlap detection
- destructive order asymmetry
- actionable advice for human arbitration

---

### Use Case 2 — Git History Protection

SARA is not just a file auditor. It is a more general **intent arbiter**.

In `repo_conflict.py`, SARA evaluates repository actions in abstract state space.
- **Action A**: `git push --force`
- **Action B**: `git commit`

These actions target the same repository, but their meaning is not symmetric.

A force push rewrites shared history.
A commit grows local state.

SARA detects that the order matters and flags the sequence as logically risky.

**Run**
```
python examples/repo_conflict.py
```
**Example Output**
```
====================================================================
SARA  |  Safe Action Residual Arbiter
SIPA Core  |  Sequential Intent & Planning Auditor
====================================================================
Scenario: git push --force vs git commit

[Audit Result]
severity              : WARN
logical_residual      : 0.4358
commutative_residual  : 0.2990
intent_collision_rate : 0.7900
context_pressure      : 0.1938
reasons               :
  - shared resource target
  - destructive order asymmetry
  - predicted end-state divergence
  - side-effect warning divergence
actionable_advice     :
  - Potential order-sensitive conflict detected. Review action order before execution.
  - Consider locking the shared resource scope to avoid concurrent writes.

[Predicted A -> B]
{
  "resources": {
    "/repos/app": {
      "exists": true,
      "backed_up": false,
      "synced": false,
      "renamed_to": null,
      "writes": 0,
      "local_commits": 1,
      "history_rewritten": true,
      "last_actor": "hotfix_dev"
    }
  },
  "touched_resources": [
    "/repos/app"
  ],
  "irreversible_ops": 1,
  "warnings": [],
  "role": "devops-assistant",
  "tokens_used": 3509
}

[Predicted B -> A]
{
  "resources": {
    "/repos/app": {
      "exists": true,
      "backed_up": false,
      "synced": true,
      "renamed_to": null,
      "writes": 0,
      "local_commits": 0,
      "history_rewritten": true,
      "last_actor": "lead_dev"
    }
  },
  "touched_resources": [
    "/repos/app"
  ],
  "irreversible_ops": 1,
  "warnings": [
    "force push may overwrite unpublished local history: /repos/app"
  ],
  "role": "devops-assistant",
  "tokens_used": 3509
}

[SIPA] WARN
Order-sensitive repo conflict detected. Human review recommended.
```

**Why this matters**

Traditional locks may only see:
- same repo
- same path
- same permission domain

SARA sees something deeper:
- **history rewrite**
- **pending local state**
- **destructive sequencing**
- **state divergence after reordering**

That is the difference between permission control and logical arbitration.

---

# Quick Start
**Requirements**
- Python 3.8+
- no third-party dependencies
- standard library only

**Clone**
```
git clone https://github.com/your-repo/sara.git
cd sara
```
**Run a demo**
```
python examples/db_disaster_v2.py
python examples/repo_conflict.py
```

---

**Repository Structure**
```
SARA-Guardian/
├── legacy/                  # Original SIPA physics / simulator auditing code
├── sipa_core/               # Core logical auditing engine
│   ├── __init__.py
│   ├── auditor_v3.py            
│   ├── circuit_breaker.py   # planned
│   └── predictor.py         # planned (modular extraction planned)
├── adapters/                # Platform-specific adapters
│   └── openclaw/            # planned
├── examples/
│   ├── db_disaster_v2.py
│   └── repo_conflict.py
├── requirements.txt
└── README.md
```

---

**How It Works**

SARA sits between planning and irreversible execution.
1. **Intercept**: Capture candidate intents before they execute.
2. **Predict**: Simulate alternative execution orders ($A \to B$ vs $B \to A$) with SIPA Core.
3. **Audit**: Compute $R_{logic}$, collision rates, and context pressure.
4. **Arbitrate**: Return a safety signal (`SAFE`, `WARN`, or `BLOCK`).
5. **Respond**: Allow, reorder, request human review, or abort.

---

**Planned OpenClaw Integration**

SARA is designed to serve as a **pre-execution middleware layer** for agent frameworks such as OpenClaw.

The intended integration pattern is simple:
- intercept candidate actions before execution
- call `audit_pair(intent_a, intent_b, context)`
- allow, warn, or block based on the result

This integration is intentionally kept adapter-driven so the SIPA Core logic stays independent from framework-specific APIs.

---

**Why Not Just Use RBAC?**

| Dimension              | Traditional RBAC / Access Control | SARA / Logical Arbitration                          |
| ---------------------- | --------------------------------- | --------------------------------------------------- |
| Core question          | Do you have permission?           | Is this execution order logically safe?             |
| Focus                  | identity and static policy        | state and order-sensitive intent flow               |
| Temporal awareness     | low                               | high                                                |
| Conflict model         | locks, permissions, contention    | residual divergence under reordered execution       |
| Goal                   | prevent unauthorized access       | prevent logical collapse and destructive sequencing |
| Typical failure caught | unauthorized delete               | backup fails because parent path was deleted first  |

---

**Key Features**
- **Logic Circuit Breaking**

Detect order-sensitive destructive conflicts before execution.

- **Sequential Audit**

Measure action divergence in state space using SIPA Core.

- **Hierarchical Conflict Detection**

Catch parent/child path overlap such as `/data` vs `/data/logs`.

- **Deterministic Safety Engine**

No external model call required for core arbitration.

- **Actionable Advice**

Return operator-friendly mitigation steps, not just a score.

- **Framework-Agnostic Core**

Designed for adapters, not hard-coded to a single agent framework.

---

**Efficiency & Usability**

**Q: What is the runtime overhead?**

**A**: SARA is a local deterministic audit layer.

For pairwise intent auditing, overhead is small and bounded. It does not require an external LLM request to compute safety signals.

**Q: Does SARA increase token usage?**

**A**: The core audit engine itself does not consume model tokens.

In practice, it can reduce overall cost by preventing expensive correction loops after destructive failures.

**Q: What about false positives?**

**A**: SARA is a **circuit breaker**, not a hard wall.

Typical responses can include:
- continue
- reorder
- request human review
- abort

This makes SARA suitable for human-in-the-loop environments as well as stricter guarded automation.

**Q: Is SARA a replacement for RBAC or sandboxing?**

**A**: No.

SARA is not a permission system. It is a **residual-based pre-execution arbitration layer** that complements RBAC, policy engines, sandboxing, and runtime access controls.

---

**Current Status**

**Alpha scope**
- [x] pairwise logical residual audit
- [x] hierarchical path conflict detection
- [x] deterministic token pressure estimation
- [x] actionable advice
- [x] disaster demos for filesystem and repository state

**Planned next steps**
- [ ] circuit breaker policy layer
- [ ] OpenClaw adapter
- [ ] multi-intent batching
- [ ] richer predictor backends
- [ ] benchmark suite

---

**Reference**

SARA extends the residual-based intuition of **NARH** into agent action streams.

**Non-Associative Residual Hypothesis (NARH)**

https://github.com/ZC502/SIPA/blob/main/README.md#non-associative-residual-hypothesis-narh
