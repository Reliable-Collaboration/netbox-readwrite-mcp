# Architecture and failure model

## Two independent systems

The stdio MCP server owns a SQLite journal and calls NetBox REST. NetBox/PostgreSQL and SQLite do not share a transaction. This client-side design cannot make their commits atomic.

For a supported edit:

1. Validate arguments, device scope, identity, and qualified NetBox version.
2. Verify local evidence and refresh the full native ObjectChange archive. Missing or altered previously archived rows block mutation.
3. Resolve outstanding writes only when native evidence proves their result; otherwise block further writes to that device.
4. Read current values and compare the ETag with the caller's precondition.
5. Commit raw intent, version-qualified normalized intent, previous values, inverse field scope, and operation key with SQLite synchronous FULL. Refuse edits whose previous values cannot round-trip exactly through REST.
6. Durably record dispatch before sending PATCH.
7. Send one PATCH with If-Match and a unique netbox-rw operation UUID marker.
8. Retain the HTTP response as a receipt, then correlate native history by marker, actor, model, object ID, action, request ID when available, pre-image, and normalized expected effect. The matched native record supplies the committed post-image. NetBox can re-query after commit, so a response body can already show another writer's values.

Same-key/same-argument requests retrieve the original operation. Different arguments with the same key are refused. This is **local idempotency**, not exactly-once remote execution.

## States

| State | Meaning and response |
| --- | --- |
| prepared | Durable intent, dispatch not entered. Later locked reconciliation can mark an abandoned operation failed without sending it. |
| dispatched | Request might have been sent. Reconcile; missing evidence alone does not prove non-commit. |
| uncertain | Transport loss or ambiguous result. Preserve the key; never automatically repeat with a new key. |
| applied_unverified | Successful HTTP receipt, native evidence not yet verified. Reconcile. |
| applied | Matching native evidence verifies the edit. Eligible for guarded undo. |
| no_change | No effective supported-field change. Retain attempt; no correction needed. |
| failed | Abandoned before dispatch or definite rejection. Inspect receipt before a deliberate new attempt. |

Storage failure after remote commit can prevent the final receipt being saved. The earlier dispatch record remains discoverable by operation key. A generic tool error is never proof of non-commit.

Native 400/401/403/404/405/409/412/422 responses are definitive rejection under the trusted NetBox/proxy contract. 408/429, unexpected statuses, malformed success responses, and connection loss do not authorize replay. Proxies must preserve NetBox semantics.

## Compensation

Undo checks current field values and intervening history, then builds an inverse containing only originally changed fields. Unrelated newer fields survive. Same-field differences or intervening changes, including ABA, produce conflicts.

A fresh ETag guards inverse dispatch. NetBox 4.6 introduced conditional PATCH; the qualified 4.6.10, 4.7.0, and 4.7.1 versions recheck under its object lock. See [REST documentation](https://netbox.readthedocs.io/en/stable/integrations/rest-api/) and [release notes](https://netbox.readthedocs.io/en/stable/release-notes/version-4.6/).

Only verified correction pairs whose actual post-image exactly equals the original inverse can be treated as net-zero while undoing earlier task operations. Corrections are observable writes. Task recovery follows the durable prepared-event sequence in reverse, independent of wall-clock time, stops on conflict or uncertainty, and resumes from persisted corrections. It offers neither cross-object atomicity nor redo.

## Durability and limits

SQLite uses WAL, synchronous FULL, foreign keys, append-only triggers, a hash chain, and operation-projection verification. POSIX file locks serialize writers sharing a journal. Evidence readers use a single SQLite snapshot, including nested verification, so legitimate concurrent commits cannot produce a mixed report or false corruption finding. Network filesystems and distributed journal replicas are unsupported.

Hashes have no external trust anchor. A privileged administrator can rewrite the archive; independent backups/checkpoints and OS controls are required for stronger audit assurance.

Full history scans are O(total accessible history). No large-estate throughput qualification has been performed. Scaling needs a carefully qualified archival strategy, not deletion of old evidence.

The server cannot prove history completeness before its first observation, detect all deletion of never-seen rows, reverse webhooks, or survive loss of every evidence copy. History must remain complete and visible throughout recovery. Database restores and schema-changing upgrades require lineage review.
