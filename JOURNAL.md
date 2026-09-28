# Development journal

## 2026-09-28 — Public product baseline

Committed and pushed the preliminary research (7a0c6b6) after scanning tracked
candidates for known generated credentials. Created this separate public repository
at the user's request. All product commits are on feat/auditable-write-recovery.

The initial release will harden the proven direct REST/device update recovery
contract, package it independently of the research workspace, and provide both
offline tests and a disposable real-NetBox integration lab. Unsupported mutation
categories must be explicit, actionable refusals. Apache-2.0 applies to this
product; the original research MIT notice is retained.

No claim of universal reversibility or established production maturity is made.

## Direct REST engine and operator boundary

Ported the researched durable-intent/conditional-PATCH/native-history reconciliation
engine into an installable package, preserving its original license notice.
Added lookup by operation key for lost MCP responses, exposed validation receipts,
strict configuration with HTTPS outside loopback, relative config paths, protocol
input limits, stable error codes, and explicit capability annotations. The runtime
has no third-party Python dependencies. The test environment uses pytest,
Hypothesis, and the official MCP SDK to audit behavior independently.

Support is intentionally limited to NetBox 4.6.10 until the new standalone suite
qualifies additional versions. Recovery is compensation, not a database rollback.

## Independent audit suites and fresh lab

The first complete standalone run passed 138 offline tests and 30 integration
tests against a fresh NetBox 4.6.10 database, using new nbrw-audit containers and
a least-privilege API identity. Offline branch-aware coverage was 88%.
Tests include official MCP SDK interoperability, real local HTTP transport,
generated edit sequences, permissions, crash/restart, concurrent processes,
ABA detection, recovery replay, and history-loss refusal.

Fixed a SQLite backup connection leak found during testing. Added conservative
classification for proxy timeout/rate-limit responses: 408/429 remain uncertain,
rather than claiming a definitive rejection. Integration artifacts stay in the
private .lab directory; CI publishes only the synthetic JUnit result, not tokens
or complete lab state. The upcoming final audit will include these changes.

## Public guidance and independent CI validation

The hardened offline suite passed 151 tests with 90.00% combined statement/branch
coverage. GitHub Actions run 36439066279 independently passed Python 3.11–3.14
and a fresh real-NetBox lab, including all 30 integration scenarios. The wheel
and sdist built; an isolated wheel installation launched successfully.

The README now leads with the problems solved and gives concrete installation,
configuration, MCP calls, recovery, and audit commands. Separate documents cover
operator permissions/retention/backups, agent behavior, tools/errors, architecture,
the full supported/refused edit-category matrix, and measured validation limits.
Version 0.1 remains explicitly bounded; passing tests is not evidence of established
production maturity or safe arbitrary NetBox CRUD.

All development remains on feat/auditable-write-recovery. Since this repository
started empty, that feature branch is also its initial public default branch;
no product work was committed to main.

## Review remediation — consistent reads and durable order (R4, R5)

Both findings are actionable in the documented shared-journal deployment.
Evidence readers now use one SQLite read snapshot, reusing an enclosing
transaction without committing it. This avoids introducing nested file-lock
release hazards. Task order now uses the existing immutable prepared-event
sequence, preserving compatibility with existing journals without a schema change.

Nine focused regression cases passed: descending/equal clock timestamps with a
reopened journal; observers, recovery bundles, and exports during concurrent
inserts/state transitions; and nested transaction rollback.
