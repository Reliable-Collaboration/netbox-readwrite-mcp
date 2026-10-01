# API-first Community coverage

The MCP uses native NetBox REST for existing operations and the Apache-2.0
[companion plugin](../companion/README.md) for confirmed API gaps. Both target
**NetBox Community 4.7.2 only**. Branching, commercial products, and qualification
of arbitrary third-party plugins are outside this stock Community scope.

An agent discovers IDs, model fields and filters at runtime. It uses `query` and
`execute_action` for native and companion actions, and guarded object tools for
ordinary CRUD. It does not need an HTML session for the mapped Community workflows.
The optional HTML tools remain experimental and are not the basis for parity.

## Pinned operation map

[The generated parity audit](netbox-4.7-parity.json) classifies all 1,543 website
routes into 40 operation families, checks native CRUD verbs against registered
REST actions, and links each operational family to live tests. The input is
[the source route inventory](netbox-4.7-surface.json). Repeated aliases and model
subclasses share families; 1,543 routes do not mean 1,543 independent features or
successful tests. An unclassified route or missing mapped CRUD verb fails the
offline audit test.

| Operation | API implementation |
| --- | --- |
| Model CRUD, relationships, child tabs, history, contacts, journals, attachments | Native REST collections, detail endpoints and relationship filters |
| Dynamic custom-field filters omitted from OpenAPI | Companion native FilterSet metadata |
| IP/prefix/VLAN/ASN allocation, cable traces, rack elevations, primary MAC | Native actions and relationships |
| CSV/JSON/YAML imports, including nested component templates | Companion native import forms and related saves, with scoped permissions and atomic rollback |
| Bulk rename, field edit/clear, tag/VLAN deltas, range/component patterns | Companion native forms/helpers, atomic batches and explicit stale guards where applicable |
| Bulk delete | Native REST; companion guarded DataFile/Job/ScriptModule deletion for omitted destroy actions |
| Bulk disconnect and synchronized data | Companion guarded native actions; native worker-backed data-source sync |
| Virtual chassis position swaps | Companion atomic native member formset; native CRUD adds/removes members |
| Configuration context and rendering | Native template, device and VM actions |
| CSV/table/YAML/saved-template export and binary download | Companion native export handlers and permission-checked bounded file reads |
| Script upload/replacement, execution, scheduling, file variables and results | Native REST/jobs; companion variable metadata and source reads |
| Queues, workers and tasks | Native administration actions; companion registry/status views |
| Configuration revisions and dashboard editing | Companion native validation, permissions and conditional writes |
| Own preferences, profile/password and notifications | Companion validated self-service APIs; native own tokens/bookmarks/subscriptions |
| Own external account disconnection | Companion native authentication-backend pipeline with stale/last-login guards |
| Search, Markdown, system/plugin information and database schema | Companion native implementations and permission gates |

The APIs call native forms, models, transactions, change logging and job machinery.
They do not wrap HTML scraping. The additional installed plugin is the cost of
exposing server-side operations that native REST omits; upgrades require renewed
qualification against the pinned internals.

## Qualification and recovery boundaries

The [worklist](parity-worklist.md) records remaining qualification and the
[validation record](validation.md) records exact tested revisions. Live assertions
check resulting state, rejection, permissions, relationships, native history and
worker completion. Discovery/schema sweeps are recorded separately from lifecycle
tests. The [consuming-agent scenarios](agent-evaluation.md) independently inspect
NetBox after natural-language tasks, including conflicts, replay and issue feedback.

Database transactions cannot undo external webhooks, queue effects or filesystem
changes. A lost response retains an uncertain receipt for reconciliation; it does
not authorize replay. Native-history writes and non-history operations have distinct
completion evidence. There is no universal graph restoration or automatic undo.

Browser login/logout and OAuth consent establish identity; the MCP uses the
operator-provisioned token instead. Browser layout and static-error pages have no
inventory operation to reproduce. Account disconnection uses configured native
backends; custom interactive authentication pipelines require separate qualification.
Third-party plugins likewise require their own fixtures. Functional operation
coverage does not establish a reliability rate for every model or every combination
of fields, nor does it promise identical browser presentation.
