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

## Review remediation — protocol boundary (R6)

The malformed initialize crash is actionable as a local stdio robustness issue.
Initialization now rejects non-string/empty protocol versions with -32602, and
excessive JSON recursion returns a parse error without killing the next request.
Malformed tool arguments also no longer falsely report that storage is unavailable.
The initial nesting regression exposed Python-version differences in JSON decoding;
an explicit 64-level limit now makes the boundary consistent. The 60
protocol/configuration boundary tests passed, including session continuation
after malformed input and official SDK interoperability.

## Review remediation — authoritative effects and exact recovery (R1, R2, R3)

Confirmed NetBox 4.6.10 uses trim_whitespace=True CharFields for description and
serial, and a ChoiceField for status. The three findings share a normalization
and evidence-authority boundary and are fixed together.

Raw intent remains immutable for audit/idempotency. Canonical intent and its
qualified profile are committed in a separate immutable event in the same
pre-dispatch transaction. Normalized no-ops do not dispatch. Native history,
with all existing correlation checks retained, now establishes committed effects;
HTTP response bodies remain receipts and never replace the intended post-image.

Changes whose pre-images cannot round-trip exactly through REST are refused
before dispatch. Historical unrepresentable inverses are refused, and historical
inexact corrections are exposed as incomplete_restore rather than already_undone.
Only exact correction pairs can be ignored as net-zero. Existing journals need
no schema rewrite: reconciliation appends evidence-backed repairs for eligible
legacy receipts; absent evidence remains uncertain. Task undo no longer skips
legacy dispatched no_change records without verification.

The expanded offline suite passed 188 tests. Live regressions exercise response
loss, hard process exit, normalized no-ops, noncanonical baselines, the real NetBox
post-commit response-query race (both A and C), and serializer normalization.
The remediation release is 0.1.1; CI will independently rerun the complete suite.

## Remediation validation and publication

GitHub Actions run 36469085494 passed all five jobs for code commit 48e46fa:
Python 3.11–3.14 and an independently seeded NetBox 4.6.10 lab. Final measurements:
188 offline tests, 36 live integration tests plus 6 subtests, 91.74% combined
statement/branch coverage. The 0.1.1 wheel installed and launched with site
packages disabled; source/wheel archives include required notices, audit inputs,
and regressions without private lab state.

Published explicit decisions for all six findings and instructions for upgrading
existing journals. The code changes are three descriptive commits: consistent
reads/order, protocol boundaries, and native-evidence/normalization recovery.
Documentation and validation records form the final commit. No force-undo path,
automatic uncertain-write retry, or silent approximate restoration was introduced.

## NetBox 4.7 target: compatibility policy and isolated qualification

The requested target is stable 4.7.x. Upstream currently publishes 4.7.0 and
4.7.1; both receive digest-pinned, independently seeded Podman labs. The default
is 4.7.1. Existing 4.6.10 compatibility remains explicit. Prereleases, malformed
versions and other minor versions are refused before any dispatch. Acceptance
of a future stable patch is distinct from qualification of that release.

New normalization events record the actual server version and a 4.7 profile;
existing immutable events are preserved. The capabilities tool exposes the
policy and qualified versions. CI now tests all three pinned NetBox versions.
Versioned ports, containers, credentials and evidence keep prior labs intact.
The offline suite passes 212 tests with 91.96% combined coverage. Real-server
qualification is running against both 4.7 releases, including the response-query
race, crash recovery, native audit correlation and optimistic undo contracts.

## NetBox 4.7 local results

Both 4.7.0 and 4.7.1 passed all 36 live integration tests and six subtests each
on independent databases. No server-contract relaxation was needed. The 0.2.0
wheel and sdist build successfully; the installed wheel launches with site
packages disabled. Archives include the compatibility tests and pinned images,
exclude private lab state, and tracked files pass the local credential scan.

The operations guide distinguishes updating the MCP binary (no schema rewrite)
from migrating the NetBox database (not certified by fresh-database tests).
Preserve paired backups and immutable evidence; do not bypass archive mismatches.
GitHub Actions run 36471841897 independently exercises all three NetBox targets
and four Python versions for code commit 1ee9740.

The first expanded CI run exposed a lab startup issue: the 4.6.10 seeder's first
read-only sites query timed out at 20 seconds immediately after bootstrap,
before any fixture write or integration test. Fixture setup now has a bounded
120-second request timeout for cold API initialization on small runners. Runtime
and contract-test timeouts remain unchanged, and no write retries were added.

Independent CI completed the requested target qualification: both 4.7.0 and
4.7.1 passed, as did Python 3.11–3.14. The overall first run is recorded as failed
because of the legacy fixture timeout, not described as a full green matrix.
A fresh full matrix for the seeding fix is run 36472610494; pending at this entry.
Local 4.7 labs are stopped with all volumes, journals and evidence retained.
