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
