# Changes

## 1.0.0 — Community integration and review follow-up

- Explain receipt outcomes and provide deterministic task summaries through MCP.
- Reuse bounded media/export snapshots while rechecking native access for each chunk.
- Protect new intent fingerprints with salted scrypt and redact known password fields.
- Make configuration and companion enablement failures safely retryable.
- Correct prefixed website origins, HTTP rejection handling and definite-rejection recovery.
- Clarify accepted NetBox versions and retain revision-specific validation evidence.

## 0.4.3 — recovery, permissions and diagnostic fixes

- Close undo history races and enforce operation-key isolation across both write interfaces.
- Match native chassis permissions while filtering inaccessible devices from read results.
- Allow inventory work alongside scheduled jobs and exact native cancellation/stop requests.
- Preserve correction receipts on repeated undo requests and expire idle HTTP sessions.
- Report read/discovery failures and both write interfaces through private diagnostic references.
- Close feedback and local agent-monitor database connections explicitly.

## 0.4.2 — three-client agent qualification

- Qualify Claude Code, Codex and OpenCode with local GLM Community acceptance runs.
- Clarify native trace discovery, import guidance and recovery behavior.

## 0.4.1 — release installation and self-describing MCP

- CI-gated downloadable wheels, standalone Python application and plugin-only container bundle.
- Private configuration wizard, generated client settings and read-only doctor.
- Companion enablement helper and configuration overlay for existing upstream deployments.
- Accept stable NetBox 4.7.x and later while identifying 4.7.2 as the tested release.
- Packaged guidance delivered by MCP initialization and tools; no injected agent guide.

## 0.3.0 — Community parity qualification

- Target only NetBox 4.7.2 with one pinned Podman lab.
- Add live discovery, schemas, filtered reads, GraphQL and general CRUD.
- Add native actions, bulk, uploads, website forms and script/job tracking.
- Add a bounded workflow interpreter and authenticated Streamable HTTP.
- Extend durable receipts, integrity projections, compensation and diagnostics.
- Add greenfield integration scenarios and agent GitHub issue feedback.

Earlier development history is retained in Git and JOURNAL.md.
