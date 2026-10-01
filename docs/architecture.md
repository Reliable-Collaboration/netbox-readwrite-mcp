# Architecture and failure model

The MCP server calls NetBox directly and retains a local SQLite journal. NetBox
and SQLite are independent transaction systems; a crash can leave a committed
NetBox mutation without its final local receipt. Stable keys, durable dispatch
records and native history reconciliation address that ambiguity without
repeating the write.

## Components

- server.py exposes tool schemas and stdio; http_server.py provides authenticated
  loopback Streamable HTTP with the same dispatcher.
- catalog.py discovers the running server's API roots and live schemas.
- workspace.py handles general reads, writes, tasks, jobs, workflows and diagnostics.
- service.py retains the qualified narrow device compensation engine.
- recovery.py assesses general field compensation and graph-recovery conflicts.
- The companion package exposes native Community forms/models through typed REST,
  enforcing native permissions and validation inside NetBox.
- feedback.py exposes the optional constrained GitHub issue bridge with a durable outbox.
- web.py retains experimental authenticated forms with cookies and CSRF.
- workflow.py interprets a bounded Python-syntax language without host access.
- store.py owns append-only evidence, integrity verification, snapshots and backup.

## General write path

1. Validate the request and exact NetBox version/connection policy.
2. Under the journal's process lock, check the operation key, local integrity,
   complete retained native history and unresolved operations.
3. For detail updates/deletes, read the pre-image and compare the supplied ETag.
4. Commit the full intent and fingerprint, then the dispatch record, before I/O.
5. Send one request with If-Match where supplied and a correlation marker where
   a JSON object payload supports it. Never automatically retry mutations.
6. Retain the HTTP result. Correlate native changes using actor, request ID or
   the operation marker, including affected children/cascades.
7. Distinguish verified native changes, completed HTTP exchanges, async acceptance,
   definite rejection and uncertainty. Track recognized jobs through reconciliation.

Same-key/same-argument calls retrieve the original receipt. Different arguments
with the same key are refused. The key namespace spans old and general writes.
An unresolved general operation blocks new general writes and device edits.
History loss or corruption also blocks mutations.

The immutable event stream projects into the existing operations table and the
additive resource_operations table. Both projections are verified. Old evidence
is not rewritten by the new table. SHA-256 chains detect corruption but do not
provide an external trust anchor against a privileged administrator.

## Recovery and boundaries

Native committed snapshots are evidence; a post-request GET or HTTP body may
already show another writer's state. General PATCH recovery checks current
values and intervening field history, then sends only the guarded inverse.
Creates/deletes/cascades and arbitrary actions retain evidence and explicit graph
recovery guidance. Original-ID graph restoration is not supplied by the client
alone. Compensation cannot retract external effects.

Website form success must be assessed from the result and native evidence:
HTTP 200 can contain validation errors. The website adapter uses native login
and CSRF, does not execute page scripts, and does not bypass SSO/MFA or native
permissions. Plugin and external product availability are deployment properties.

Full history scans and process serialization are retained for small home labs.
There is no distributed writer or high-availability contract. Complete native
history, durable local storage, correct instance lineage and tested backups are
operational prerequisites.
