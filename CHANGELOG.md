# Changelog

## 0.1.1 — recovery and observability correctness

- Derive verified effects from native history instead of post-commit response representations.
- Retain raw and qualified normalized intent; reconcile normalized lost responses.
- Refuse unround-trippable previous values and identify incomplete legacy restorations.
- Repair provable legacy dispatched receipts through append-only reconciliation.
- Read evidence in consistent SQLite snapshots; order task recovery by durable event sequence.
- Reject malformed initialization and excessive JSON nesting without terminating the session.
- Add deterministic and live regression coverage for all six review findings.

## 0.1.0 — initial implementation

- Direct stdio MCP writes for device description, serial, and status.
- Durable intents, previous values, no-op/failure receipts, native history correlation.
- Local idempotency, uncertain outcome reconciliation, optimistic field-aware undo.
- Resumable task compensation, history inspection, recovery bundles, backups and exports.
- Strict object scope and configuration, structured instructional errors.
- Independent offline, HTTP, MCP SDK, property-based, and real-NetBox integration tests.
- Apache-2.0 packaging and operator/agent recovery guidance.

No PyPI release or broad production qualification has been performed.
