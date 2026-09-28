# Tool reference

All tools reject missing/extra arguments and wrong top-level types. IDs and operation keys are strings; device IDs are positive integers. Device writes are constrained by both configured IDs and native permissions.

| Tool | Required arguments | Result |
| --- | --- | --- |
| capabilities | None | Supported model/fields, write path, exclusions, limitations |
| begin_task | purpose | task_id; purpose is 1–1000 characters |
| read_device | device_id | Supported values, name, ETag, untrusted-content flag |
| update_device | task_id, operation_key, device_id, expected_etag, changes | Durable operation and authoritative state/receipt |
| find_operation | operation_key | found flag, original operation, guidance |
| get_operation | operation_id | Raw/normalized intent, previous/resulting values, receipts, state, evidence IDs |
| get_task | task_id | Task and ordered operations |
| get_device_history | device_id | Retained native changes and freshness |
| preview_undo | operation_id | ready, conflicted, blocked, no_change, already_undone, correction_pending, incomplete_restore, or unsupported |
| undo_operation | operation_id, operation_key | New correction receipt or a refusal/conflict assessment |
| undo_task | task_id | undone or partial_or_blocked, correction task, per-operation results, atomic=false |
| reconcile | None | Refreshed history, resolved outcomes where provable, observability |
| observability | None | State/event counts, unresolved operations, archive health, integrity |
| recovery_bundle | operation_id | Offline inverse values, identity, operation, native evidence, journal events |

Operation keys contain 8–160 ASCII letters, digits, periods, underscores, colons, or hyphens. Supported values are strings up to the transport guard of 10,000 characters; NetBox applies its tighter field validators. Status choices are validated by NetBox so deployment-specific choices can be honored.

The protocol supports stdio versions 2024-11-05, 2025-03-26, 2025-06-18, and 2025-11-25. Requests are bounded to 1 MiB and 64 JSON nesting levels and responses from NetBox to 16 MiB. Initialize the session first. No HTTP MCP transport, arbitrary API tool, shell tool, resources, or approval workflow is provided.

## Error contract

Tool errors return isError=true with structured content:

~~~json
{
  "status": "blocked",
  "code": "STALE_STATE",
  "warning": "Stale expected_etag: read current state; no write was dispatched",
  "action": "Read the device again. Compare current values before making a new deliberate edit.",
  "automatic_retry_allowed": false,
  "mutation_outcome": "inspect_durable_receipt"
}
~~~

When an operation key is available and storage is usable, receipt_lookup identifies any durable operation. Storage failure can prevent this lookup. Do not infer non-commit from an exception.

Codes include UNRESTORABLE_VALUE, STALE_STATE, KEY_REUSED, UNSUPPORTED_EDIT, OUT_OF_SCOPE, UNRESOLVED_OPERATION, HISTORY_UNAVAILABLE, INTEGRITY_FAILURE, UNSUPPORTED_VERSION, UNKNOWN_TASK, UNKNOWN_OPERATION, DEPENDENCY_UNAVAILABLE, INVALID_REQUEST, and OPERATION_BLOCKED.

NetBox validation/permission rejection is a durable failed operation, not a transport exception. Inspect last_receipt.status and last_receipt.body for native field errors. Conflict assessments are normal tool results with warnings; clients must inspect their status, not only isError.


Description/serial whitespace is normalized before no-op detection and dispatch.
The raw requested map remains the idempotency input. normalized_requested is the
retained canonical intent; after_values represents that expected effect until
native verification establishes it. A response receipt may legitimately contain
a later writer's state; use the verified operation/native record for this
operation's effect.

incomplete_restore is a blocking undo assessment: an older correction committed,
but did not restore the exact prior values. Its inverse and warning support operator
review. Task undo stops rather than treating that correction as complete.
