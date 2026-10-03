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
diagnostic references and session lifetime. These fixes are included in v0.4.3;
historical v0.4.2 release and paid-agent qualification records remain unchanged.


## PR #2 Copilot findings and full-scope follow-up

The review at `48b3079` identified seven actionable findings. The changes below
are unreleased PR work, not part of the previously published v0.4.3 assets.

| Finding | Resolution and regression evidence |
| --- | --- |
| Media rescanned the entire file for every chunk | Bounded per-user snapshots store separate 64 KiB cache blocks. A live multi-chunk image download opens the native file once; unit checks count retrieved bytes and cover missing/replaced blocks. |
| Password fingerprints permitted fast offline guesses | New general-operation, workflow-source and workflow-step fingerprints use randomly salted scrypt. Tests cover differing salts, exact replay, changed-input rejection and all three durable layers. Old immutable fingerprints retain their historical exposure; see operations.md. |
| Export chunks repeatedly rendered the full export | Reuse generated bytes with the original SHA guard. Live tests verify one render, regeneration after a revision change, and denial after the same user loses permission. Existing all-handler export, chunk/content-guard and permission tests remain intact. |
| Failed setup stranded its new token | Track exclusive creation and clean up only files created by the invocation, including write, permission-setting and buffered-close failures. Tests verify successful retry and preservation of existing credentials. |
| Prefixed website requests sent invalid Origin | Derive scheme and authority for Origin; retain the full URL as Referer. Regression includes a path prefix and nondefault port. |
| Parity worklist reported stale suite totals | Link to the maintained validation record rather than duplicate a changing count. |
| Tool reference claimed compatibility only with 4.7.2 | State stable 4.7.x or later acceptance separately from testing on 4.7.2. |

The independent review covered the complete PR's runtime/protocol boundaries,
journal and recovery paths, companion permission/transaction handling, discovery
and workflows, packaging/setup, CI/release/feedback boundaries, documentation and
test contracts. It found four further actionable defects:

| Additional finding | Resolution and regression evidence |
| --- | --- |
| Native user/bulk payloads retained password fields outside the companion password route | Recursive known-password-field redaction preserves outbound data while removing those fields from persisted intent. A native user-create regression verifies both sides. This is not a general scrubber for secrets embedded in arbitrary strings/files. |
| Companion enablement could not retry after writing its backup but failing before replacement | Reuse only a matching, nonsymlink backup; preserve conflicting backups for inspection. Remove only a newly created partial backup after its write/close failure. A reproduced temporary-file failure now permits retry. |
| Definite 413/415/428 responses were treated as uncertain writes | Recognize request-size, media-type and missing-precondition rejections as failed attempts, retaining receipts and native reconciliation. Red regressions reproduced the unnecessary block on subsequent operations; corrected requests now proceed. Unknown/server failures remain uncertain. |
| HTTP rejection left an unread body on a reusable connection | Close and advertise closure whenever a body is not consumed, including invalid lengths/content types and unsupported paths/methods. Regressions exercise actual sockets and malformed Origin rejection. |

The new red tests reproduced the companion retry and HTTP framing defects before
the fixes. Final validation results are recorded in [validation](validation.md).
Historical agent qualification is retained with its original artifact hashes;
these deterministic changes do not turn prior model failures into passes.

A follow-up review of the remediated code found no further actionable defects
within this scope.


## PR #2 second Copilot review

The review of `278aa2c` confirmed the first seven findings were resolved and raised
two additional issues. Both are fixed:

| Finding | Resolution and validation |
| --- | --- |
| Unreleased fixes still identified as published version 0.4.3 | Bump MCP and companion package metadata and runtime declarations together to 0.4.4. Update release filenames/notes and mark the changelog unreleased. Build both distributions, verify standalone version reporting, and load the companion bundle on upstream NetBox. Existing v0.4.3 download links remain valid and are explicitly distinguished from the candidate. |
| Journal incorrectly limited compatibility to 4.7.2 | State stable 4.7.x-or-later runtime acceptance separately from 4.7.2 qualification; mark the original exact-version policy as historical. Existing compatibility tests pass. |

[Version follow-up evidence](version-review-validation.json) records the tested
revision, timings and private candidate asset hashes. Nothing was published.
