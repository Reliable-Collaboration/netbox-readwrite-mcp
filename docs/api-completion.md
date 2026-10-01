# API-first feature completion

Inventory agents should use typed API tools. The HTML form adapter is an
experimental fallback, not the architecture for full feature coverage. It logs
in with a native session, parses server-rendered fields, and submits CSRF-protected
requests. It does not execute JavaScript, model all browser behavior, or provide
conditional-write protection or automatic undo for form submissions. A UI change
can break parsing or change the meaning of a submission.

## Boundary and implementation choice

For each requested workflow, prefer these implementations in order:

1. The existing NetBox REST API, exposed through MCP discovery and typed arguments.
2. An MCP workflow composing existing endpoints where their semantics are sufficient
   (for example, renaming a selected set of objects with fresh ETags).
3. A small permissively licensed NetBox plugin exposing an explicitly typed endpoint
   for a confirmed server-side gap. This endpoint must use native validation,
   object permissions, transactions, change logging and job machinery as applicable.
4. Experimental form interaction only when specifically requested and qualified.

A wrapper around HTML scraping would hide the dependency without removing its
brittleness. A plugin runs inside NetBox and can expose the underlying operation
directly. The MCP side keeps stable semantic tool inputs and outputs; agents
should not have to understand a Django form or import internal Python classes.
NetBox Community supports [plugin REST endpoints](https://netboxlabs.com/docs/netbox/plugins/development/rest-api/).
The tradeoff is one additional installed component and compatibility testing
against the pinned NetBox version. Branching and commercial extensions remain
outside scope. The first [companion plugin](../companion/README.md) now implements
native filter metadata, a gap demonstrated by the consuming-agent evaluation,
guarded configuration revisions, and validated first-use personal dashboards.
Other missing operations still need action-specific implementation and qualification.

## Initial audit against the actual 4.7.2 source

The registered route inventory is a starting point, not a proof of parity.
Comparing only model-backed ViewSets misses custom API views. Source inspection
of the running pinned image established these examples:

| Workflow | Existing interface | Consequence |
| --- | --- | --- |
| Dynamic custom-field filter metadata | Companion `filter-schema` endpoint reads the native FilterSet | OpenAPI omits these fields; accurate metadata prevents silently broadened queries |
| Inventory CRUD and relationships | Native model REST endpoints | No HTML or new plugin required for the evaluated greenfield task |
| Data-source synchronization | `POST /api/core/data-sources/{id}/sync/` | Existing custom action checks `core.sync_datasource`; do not duplicate it |
| Current user's dashboard | Native raw JSON API plus companion `self/dashboard/` and `dashboard-widgets/` | Companion fills first-use and native-form-validation gaps, with self-service permissions, per-widget PATCH, conditional writes and reset; all five widgets live-tested |
| Background queues, workers and task administration | Native `core/background-queues/`, `background-workers/`, and task `enqueue`, `requeue`, `stop`, `delete` actions | No duplicate plugin needed; worker-name lookup is live-tested, queue mutation lifecycles still need qualification |
| Current user's preferences | Native `GET` / `PATCH users/config/` | Live-tested merge semantics and user isolation; MCP audit metadata no longer pollutes preferences; no native ETag or ObjectChange contract |
| Synchronized contexts, context profiles and templates | Native per-object `sync/` from `SyncedDataMixin` | Existing API checks native `sync` permission; bulk composition and failure semantics still need qualification |
| Notifications, subscriptions, bookmarks and account management | Native extras/users APIs | Routes exist; self-service versus administrative permissions still need action-level equivalence tests |
| Configuration revisions | Companion `config-revisions/` and `configuration-schema/` | Native validation/activation, permission constraints, stale-write guards, restore and inactive deletion tested against real NetBox; no native ObjectChange history or automatic undo |
| CSV import, bulk rename, rendering and other specialized views | Some have native actions or can be composed from CRUD | Audit their transaction, validation and result semantics before declaring equivalence |

Worker names illustrate a transport gap rather than a missing NetBox API: native
routes permit `@` and `+`, which the MCP path validator previously rejected.
It now accepts those characters while retaining the relative-path boundary.
A real synthetic RQ worker verifies lookup through MCP and the native denial
for a non-superuser. This does not qualify all RQ task state transitions.

## What full coverage would require

Maintain an action-level matrix, with a row for each supported open-source
workflow, its native or extension endpoint, authorization, required fixtures,
observable postconditions and recovery boundary. A discovered route or an OPTIONS
response counts as discovery coverage only. It is not a successful lifecycle test.

Every supported row needs positive and negative tests against real NetBox:
permissions, valid/invalid input, relationships, updates/deletes, concurrent edits,
request loss and job completion where relevant. UI/API equivalence checks must
assert resulting state and native history, not identical HTTP status codes.
Third-party plugins need their own fixtures and qualification.

Agent evaluation is a separate layer: natural-language tasks through a real MCP
client and model, verified by an independent state oracle. It must cover repeated
requests, conflicts and honest reporting, not just valid JSON tool calls. Passing
one or two models on a few tasks does not establish all-feature coverage or a
reliability rate. See [agent evaluation](agent-evaluation.md).
