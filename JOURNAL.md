# Development journal

Earlier experiment logs and release-specific evidence remain in Git history.
Current support is NetBox 4.7.2 only.

## Recovery foundation

The initial implementation established durable intent, conditional device writes,
retained native history, field-aware compensation and explicit uncertain outcomes.
Review regressions added serializer normalization, protection against post-commit
response re-query races, consistent observer snapshots, durable event ordering,
and bounded MCP parsing. Those regressions remain in the maintained test suites.

Original-ID deletion recovery research found useful NetBox core machinery and
hazards involving occupied IDs, missing dependencies and partial graph restoration.
The proposed recovery extension remains separate from general CRUD execution.
See docs/deletion-recovery.md.

## 2026-09-30 — greenfield Community inventory

The user requested a single current target, broad agent operations, real integration
tests, website access and GitHub feedback before consumer handoff. Upstream release
metadata identified 4.7.2 as the latest stable target. The lab and compatibility
policy now pin exactly that release.

The official community and managed MCP feature lists informed the capability
inventory. The user clarified that only fully open-source features belong in
scope: Branching and commercial integrations are excluded.

General resource discovery and schemas replace the need for pre-supplied IDs.
CRUD, filtered reads, GraphQL, native actions, bulk operations, uploads, scripts,
job tracking, website forms, a bounded workflow interpreter and authenticated HTTP
extend the existing stdio interface. The general journal uses an additive projection
without rewriting old events. General PATCH compensation checks native snapshots,
current values and intervening field history; graph restoration remains explicit.

Live tests use isolated Podman containers, a non-superuser inventory actor and
synthetic fixtures. Scenarios include a greenfield physical/virtual lifecycle,
CRUD, IPAM allocations, cabling, rendering, scripts, website forms, native denials,
response loss, last-moment conditional-write races, and recovery conflicts.
The final validation record contains measured results and remaining limits.

A synthetic GitHub issue verified submission, maintainer read access, response
and closure: https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/1.
No private inventory, credentials or raw recovery bundles were published.

## 2026-10-02 — v0.4.3 published and independently verified

- Published tag `v0.4.3` from `0aa3b72` through release CI `37011423929`.
- Release qualification: 400 unit + 234 real-NetBox tests, six subtests, 92.23% MCP runtime coverage; full test step 2055.451 seconds. Python 3.11–3.14, builds and upstream companion bundle passed.
- Final local GLM-5.3-Flash runs passed through Claude Code (`0fe913dfb3`), Codex (`f7262ba4df`) and OpenCode (`9ccd9a9280`) using Reliable Collaboration's unofficial NetBox read/write MCP server. Original failed attempts and narration limits remain in the record.
- Downloaded all nine assets without authentication; checksums, candidate application members and tagged wheel modules match. Private configure and live doctor passed.
- Provider key absent from reachable Git objects, tracked files, public asset contents and completed release logs. Repository Actions secrets: zero. Model tests remained local only.
- Exact evidence: `docs/release-validation-0.4.3.json` and `docs/client-agent-evaluations-0.4.3.json`.

## 2026-10-02 — local deterministic timing and modest fixture optimization

- Ran all 400 unit and 234 integration tests locally with coverage: 634 passed plus six subtests, 92.23% runtime coverage, 3365.54 seconds wall time. Zero LLM calls; Python 3.14.4, existing isolated NetBox 4.7.2 lab.
- Lint, both builds, asset checks and upstream-image companion check passed in 12.68 seconds combined.
- Batched creation of two per-test users into one Django startup; retained all assertions, separate users/tokens/permissions/journals and function-scoped isolation. Median setup improved from 8.64 to 4.15 seconds over three measurements per variant.
- All 37 affected tests passed unchanged; summed durations improved from 786.21 to 647.43 seconds. No full optimized local rerun was claimed.
- Full CI `37022455057` on `d0185df` passed 634 tests plus six subtests, unchanged 92.23% coverage, all Python 3.11–3.14 builds and upstream bundle checks. Test step 1729.753 seconds; CI variability is explicitly recorded. Provider key absent from its completed log.
- Retained only this small fixture optimization; no reduced checks or runtime safety changes. Evidence: `docs/deterministic-timing-0.4.3.json`.
