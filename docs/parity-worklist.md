# Stock Community operation closure

Target: **NetBox Community 4.7.2 only**, excluding Branching and commercial
extensions. [The pinned audit](netbox-4.7-parity.json) maps all 1,543 website
routes to 40 semantic families, with no unknown routes or missing mapped native
CRUD verbs. Route classification is separate from execution evidence.

The implementation covers the stock operation families through native REST or
typed companion APIs. The table records deterministic qualification by family.
The full suite and strict combined consuming-agent scenario have passed:
585 tests plus 6 subtests, including 231 real-NetBox cases, and all 23 strict
GLM scenario checks. Exact revisions, results and limits are recorded in
[validation](validation.md) and [agent evaluation](agent-evaluation.md).

| Operation family | Live qualification |
| --- | --- |
| CRUD, discovery, filters, GraphQL and relationships | Physical/virtual inventory, IPAM, circuits/providers/virtual circuits, VPN/IKE/IPSec, wireless, contacts/journals, users/groups/constrained permissions and custom fields |
| Imports | Every handler's schema; CSV delimiters, JSON/YAML, partial update, nested device/module templates, malformed input and parent/child permission rollback; lost-response replay protection |
| Bulk rename | Literal/regex substitution, native field validation, stale preview and uniqueness rollback |
| Bulk field edit | Update, clearing, tag deltas and interface VLAN deltas; native handler schema sweep, stale guards and permission denials |
| Pattern creation | Native range allocation plus all 26 component forms, front/rear-port relationships and atomic multi-parent rollback |
| Bulk deletion | Native protected-object rollback and complete correlated history; companion DataFile/Job/ScriptModule deletion, data-file regeneration, queue cancellation, source-file removal, dependent SET_NULL guard and token denial |
| Child tabs, history, journals and contacts | Native relationship filters and assignments; immutable history reads remain valid with native port-mapping changes |
| Cable traces, rack elevations and availability actions | Real topology and allocation fixtures for IP/prefix/VLAN/ASN; independent agent topology checks |
| Chassis and primary MAC | Atomic member position swaps, invalid/stale requests; physical and VM primary-MAC assignments and foreign-assignment rejection |
| Bulk disconnect | All eight native component types, mixed permission constraints, read-only token rejection, lost-response reconciliation without duplicate dispatch |
| Data synchronization | Real source worker, four synchronized object families, guarded bulk application, stale source/object state and invalid-file atomic rollback |
| Configuration rendering and exports | Template/device/VM rendering, native render permissions and failure response; CSV/table/YAML/template exports and every export handler's schema/empty output |
| Scripts and jobs | Real uploads, file variables, choices/defaults, scheduling, source discovery and worker completion |
| Queue/worker/task administration | Enqueue, requeue, stop, delete, registry/status views, worker-name lookup and superuser boundaries |
| Configuration revisions | Native lifecycle, activation/restore, permissions, concurrency, stale guards and response loss; dedicated GLM scenario |
| Dashboards | All native widgets, first-use/reset, isolation, concurrency and response loss; dedicated GLM scenario |
| Preferences, notifications, bookmarks, subscriptions and tokens | Own-object lifecycles, partial preferences/table clearing, ETag guards, notification read/dismiss semantics and identity isolation |
| Profile/password/account disconnection | Native validation, password receipt redaction, stale association guards, last-login protection and read-only token denial |
| Search, Markdown, system/plugin information and schema | Scoped search, malformed inputs, native rendering and administrative boundaries |
| Media | Attachment and both device-type image fields; DataFile binary content, bounded chunks, content hashes and permissions |
| Webhooks/event rules | Real worker delivery to an isolated receiver, event conditions, HMAC signature and native request-ID correlation |
| Agent observability/GitHub feedback | Durable receipts and diagnostics; GLM issue #3 publication, idempotent replay and verified maintainer reply |

Browser session creation and external OAuth consent are replaced by the
operator-provisioned API identity. Browser layout/static-error presentation has
no inventory operation to reproduce. The companion uses configured native account
disconnection backends; custom interactive pipelines and arbitrary third-party
plugins require separate qualification. These boundaries are explicit in the map.

Qualification establishes stock operation coverage and the listed scenarios. It
does not mean every possible field combination, plugin or browser presentation
has been tested. Database transactions cannot roll back webhook delivery, queue
side effects or filesystem deletion; uncertainty must be reconciled. There is no
universal automatic undo or statistical model-reliability guarantee.
