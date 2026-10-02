# Review decisions and resolution

The review of bed414e found six reproducible defects. All were actionable.
The response/normalization defects directly affected audit and recovery correctness;
the others affected supported concurrency, task recovery, and local protocol robustness.
These findings concern the original device engine. Its regression contract is retained
alongside the general resource engine; see edit-contract.md for the expanded scope.

| Finding | Chosen resolution | Regression evidence |
| --- | --- | --- |
| R1: Inexact undo reported as successful | Refuse non-round-trippable pre-images before editing; refuse historical unrepresentable inverses; report incomplete_restore for inexact historical corrections; require exact equality before treating pairs as net-zero | Offline legacy fixtures and replay/task checks; actual stored noncanonical values in the isolated NetBox lab |
| R2: A committed write recorded as no_change after a response race | Retain response bodies as receipts; establish committed effects from correlated native history, preserving all correlation checks | Actual NetBox perform_update followed by a second real HTTP write before response re-query, for both A and C |
| R3: Normalized lost responses could not reconcile | Commit raw and qualified canonical intent together before dispatch; normalized no-ops avoid dispatch | Lost-response and hard-exit tests for normalized writes; actual serializer qualification, including Unicode whitespace |
| R4: Concurrent readers reported false corruption | Consistent SQLite read snapshots spanning complete evidence reports and nested verification | Concurrent inserts/state changes during observability, recovery bundles, and exports; nested rollback |
| R5: Wall-clock changes broke undo order | Existing durable prepared-event sequence determines order | Descending/equal timestamps with a reopened journal |
| R6: Malformed initialization killed stdio MCP | Type validation, explicit 64-level nesting bound, and protocol errors with session continuation | Invalid protocol-version types, deeply nested JSON, subsequent valid initialization/ping, official SDK |

## Why these choices

Trusting the HTTP body was not repaired with a retry: the response can truthfully
represent a later state. Native correlation now establishes the original effect.
No actor, marker, object, request-ID, or pre-image check was removed.

Normalization was not handled by silently rewriting previous values. New intent is
normalized according to the qualified serializer, while exact pre-images remain
unchanged. A value that cannot be restored through REST is an explicit refusal.

Read snapshots avoid blocking ordinary SQLite WAL writers and avoid unsafe nested
file-lock release. Durable event order works across process restarts and existing
journals without adding a timestamp-based heuristic.

The protocol issue is a local robustness defect, not an unauthenticated public
network endpoint vulnerability. Input rejection remains bounded and actionable.

## Existing journals

No old evidence is deleted or rewritten. Reconciliation appends corrections to
the operation projection when native evidence proves a legacy write. Unprovable
dispatches remain uncertain. Historical inexact corrections are identified rather
than falsely reported as completed undo. Stop old processes, retain a verified
backup, upgrade all clients, and reconcile before resuming; see
[the upgrade procedure](operations.md#existing-journal-migration).

The previous standalone review reproductions remain in the private lab directory
as historical evidence. The maintained regression suite asserts the corrected
behavior and runs in CI.

See [validation](validation.md) and [the journal](../JOURNAL.md) for measured results.

## Review follow-up after v0.4.2

The current source addresses seven reproduced findings from the broader MCP and
companion review. A second pass found an additional task-undo entry point for the
same cross-interface operation-key collision; its regression failed before the
shared undo guard was added. A further permission probe reproduced HTTP 403
for a change-only chassis editor; member discovery now matches the native edit
form without requiring an additional view grant. The job-control pass also
reproduced a blocked native stop action for an acknowledged running job; the
exemption now matches that job's native queue UUID and still rejects unrelated
uncertain operations. Python 3.14 resource warnings then exposed unclosed
SQLite connections in feedback and local agent monitoring. These now close
explicitly, and feedback reads its diagnostic fields in one consistent snapshot.

| Finding | Resolution | Regression evidence |
| --- | --- | --- |
| General undo missed an intervening B → C → B edit during its current-object read | Refresh native history after that read; retain the read's ETag for dispatch | Adversarial current-read hook refuses compensation and preserves newer edits |
| Read-only chassis viewers could see inaccessible members | Restrict member reads to visible devices; preserve the native complete edit formset for chassis editors | Real NetBox permissions: no visible devices, one visible device, then chassis edit permission with and without a view grant |
| Device writes and undo could reuse a general operation key | Check under the shared process lock; preserve outer locks across nested calls; guard both individual and task undo | Interleaved second journal connection, independent flock probe, and task-undo key collision |
| Future jobs blocked inventory work and their own cancellation | Track scheduled jobs separately; allow guarded cancellation and native stopping of the exact known job; record missing acknowledged jobs without claiming success or replaying them | Scheduled script plus inventory write, cancellation, and verified running-task stop in real NetBox; unrelated uncertainty still blocks cancellation |
| Failed general undo could not replay its original key | Find the existing correction before creating another task; require it to reverse the requested operation | Repeated HTTP 412 returns the same correction and creates no new task |
| Abandoned HTTP sessions exhausted the session limit | Expire idle sessions after one hour and refresh active sessions | Fill all 128 slots, preserve an active client, expire abandoned clients, then initialize successfully |
| Feedback excluded device receipts and errors without writes | Accept both operation tables and persisted tool diagnostic references; publish only selected metadata | Redaction checks, official SDK stdio/HTTP response checks, and feedback lookup |
| SQLite handles remained open after feedback and monitoring calls | Close every short-lived connection explicitly, retaining outbox transactions and a consistent diagnostic snapshot | Connection-lifecycle regression and resource warnings treated as errors |

Built-in MCP guidance and operator documentation describe the new job states,
diagnostic references and session lifetime. These are source changes after
v0.4.2; historical release and paid-agent qualification records are unchanged.
