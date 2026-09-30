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
