"""
Disaster Demo: delete vs backup
===============================

This demo shows how SIPA Core can detect an order-sensitive,
destructive conflict before irreversible execution.

Run:
    python examples/db_disaster.py

Expected behavior:
- computes Logical Residual
- prints predicted states for A->B and B->A
- triggers FUSE_BLOWN when residual is high
- enters a simple human-arbitration loop:
    force   -> proceed anyway
    reorder -> try B then A
    abort   -> terminate safely
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sipa_core.auditor import LogicalResidualAuditor


def pretty_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False)


def print_banner():
    print("=" * 68)
    print("SARA  |  Safe Action Residual Arbiter")
    print("SIPA Core  |  Sequential Intent & Planning Auditor")
    print("=" * 68)
    print("Scenario: delete vs backup on the same resource")
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
    else:
        print("reasons               : none")

    print()
    print("[Predicted A -> B]")
    print(pretty_json(report.state_ab))
    print()
    print("[Predicted B -> A]")
    print(pretty_json(report.state_ba))
    print()


def handle_fuse_blown(report):
    resource = report.intent_a.get("resource", "unknown")

    print("[SIPA] FUSE_BLOWN: DATA AT RISK")
    print(f"resource       : {resource}")
    print(f"risk_score     : {report.logical_residual:.4f}")
    print("residual_type  : Logical Residual")
    print("recommendation : BLOCK and request human arbitration")
    print()

    while True:
        choice = input("Choose action [force | reorder | abort]: ").strip().lower()

        if choice == "force":
            print()
            print("[Operator Decision] FORCE")
            print("Proceeding with original order A -> B despite detected risk.")
            return "force"

        if choice == "reorder":
            print()
            print("[Operator Decision] REORDER")
            print("Retrying with B -> A to reduce destructive asymmetry.")
            return "reorder"

        if choice == "abort":
            print()
            print("[Operator Decision] ABORT")
            print("Execution terminated safely.")
            return "abort"

        print("Invalid input. Please enter: force, reorder, or abort.")
        print()


def main():
    print_banner()

    context = {
        "resources": {
            "/data/logs": {
                "exists": True,
                "backed_up": False,
                "synced": False,
                "renamed_to": None,
                "writes": 0,
                "last_actor": None,
            }
        },
        "role": "ops-assistant",
        "tokens_used": 2400,
        "max_window": 16000,
    }

    intent_a = {
        "actor": "user_a",
        "action": "delete",
        "resource": "/data/logs",
        "content": "rm -rf /data/logs",
        "destructive": True,
    }

    intent_b = {
        "actor": "user_b",
        "action": "backup",
        "resource": "/data/logs",
        "target": "cloud://ops-backup/logs",
        "content": "backup /data/logs",
        "destructive": False,
    }

    auditor = LogicalResidualAuditor(
        warn_threshold=0.35,
        block_threshold=0.70,
    )

    report = auditor.audit_pair(intent_a, intent_b, context)
    print_report(report)

    if report.severity == "BLOCK":
        decision = handle_fuse_blown(report)

        if decision == "force":
            print()
            print("[Execution Trace]")
            print("A -> B executed.")
            print("Potential consequence: backup may fail because the resource is gone.")

        elif decision == "reorder":
            reordered = auditor.audit_pair(intent_b, intent_a, context)
            print()
            print("[Reordered Audit]")
            print_report(reordered)
            print("[Execution Trace]")
            print("B -> A executed.")
            print("Backup occurs before delete. Data-loss risk is lower, but operation remains destructive.")

        elif decision == "abort":
            print()
            print("[System State]")
            print("No irreversible action executed.")

    else:
        print("[SIPA] SAFE")
        print("No circuit break triggered.")


if __name__ == "__main__":
    main()
