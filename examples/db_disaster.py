"""
Disaster Demo: delete vs backup (v2)
====================================

This demo shows how SIPA Core can detect an order-sensitive,
destructive conflict before irreversible execution.

Run:
    python examples/db_disaster_v2.py
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
    print("Scenario: delete parent path vs backup child path")
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


def handle_fuse_blown(report):
    resource = report.intent_a.get("resource", "unknown")

    print("[SIPA] FUSE_BLOWN: DATA AT RISK")
    print(f"resource       : {resource}")
    print(f"risk_score     : {report.logical_residual:.4f}")
    print("residual_type  : Logical Residual")
    print("recommendation : BLOCK and request human arbitration")
    if report.actionable_advice:
        print("advice         :")
        for tip in report.actionable_advice:
            print(f"  - {tip}")
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
            "/data": {
                "exists": True,
                "backed_up": False,
                "synced": False,
                "renamed_to": None,
                "writes": 0,
                "local_commits": 0,
                "history_rewritten": False,
                "last_actor": None,
            },
            "/data/logs": {
                "exists": True,
                "backed_up": False,
                "synced": False,
                "renamed_to": None,
                "writes": 0,
                "local_commits": 0,
                "history_rewritten": False,
                "last_actor": None,
            },
        },
        "role": "ops-assistant",
        "tokens_used": 2400,
        "max_window": 16000,
    }

    intent_a = {
        "actor": "user_a",
        "action": "delete",
        "resource": "/data",
        "content": "rm -rf /data",
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
            print("Potential consequence: child backup may fail because the parent path has been removed.")

        elif decision == "reorder":
            reordered = auditor.audit_pair(intent_b, intent_a, context)
            print()
            print("[Reordered Audit]")
            print_report(reordered)
            print("[Execution Trace]")
            print("B -> A executed.")
            print("Backup occurs first. Data-loss risk is lower, but the later delete remains destructive.")

        elif decision == "abort":
            print()
            print("[System State]")
            print("No irreversible action executed.")

    else:
        print("[SIPA] SAFE")
        print("No circuit break triggered.")


if __name__ == "__main__":
    main()
