"""Stable error codes and recovery instructions for humans and agents."""

import sqlite3

RULES = [
    (
        "Unrestorable previous value",
        "UNRESTORABLE_VALUE",
        "Ask an operator to review the original values; REST normalization prevents exact restoration.",
    ),
    (
        "Stale",
        "STALE_STATE",
        "Read the target object again and preserve its exact ETag. Compare current values before making a new deliberate edit.",
    ),
    (
        "Idempotency",
        "KEY_REUSED",
        "Reuse the original key only with its original arguments. Inspect find_operation.",
    ),
    ("Idempotency key belongs", "KEY_REUSED", "Use find_operation to inspect the existing correction."),
    (
        "Unsupported edit",
        "UNSUPPORTED_EDIT",
        "Read capabilities. Do not bypass this server with a raw API write.",
    ),
    (
        "allowlist",
        "OUT_OF_SCOPE",
        "Ask the operator to review the configured device scope and native permissions.",
    ),
    (
        "unresolved",
        "UNRESOLVED_OPERATION",
        "Call reconcile and inspect find_operation; do not invent a new key.",
    ),
    (
        "history",
        "HISTORY_UNAVAILABLE",
        "Restore complete history access and inspect observability before writing.",
    ),
    (
        "integrity",
        "INTEGRITY_FAILURE",
        "Stop writers and compare the journal with a verified off-host backup.",
    ),
    (
        "projection",
        "INTEGRITY_FAILURE",
        "Stop writers and compare the journal with a verified off-host backup.",
    ),
    (
        "version",
        "UNSUPPORTED_VERSION",
        "Use the tested NetBox version or qualify an upgrade with the integration suite.",
    ),
    ("Unknown task", "UNKNOWN_TASK", "Use begin_task, or retrieve the existing task ID from your records."),
    ("Unknown operation", "UNKNOWN_OPERATION", "Use find_operation with the original operation key."),
]


def describe(exc):
    code, action = "INVALID_REQUEST", "Read the tool schema and capabilities, then correct the request."
    if isinstance(exc, (OSError, sqlite3.Error)):
        code, action = (
            "DEPENDENCY_UNAVAILABLE",
            "Check storage and connectivity. Inspect find_operation and reconcile before any new attempt.",
        )
    elif not isinstance(exc, ValueError):
        code, action = (
            "OPERATION_BLOCKED",
            "Inspect observability and the original operation key; an error is not proof that no write committed.",
        )
    message = str(exc)
    for text, candidate, guidance in RULES:
        if text in message:
            code, action = candidate, guidance
            break
    return {
        "status": "blocked",
        "code": code,
        "warning": message,
        "action": action,
        "automatic_retry_allowed": False,
        "mutation_outcome": "inspect_durable_receipt",
    }
