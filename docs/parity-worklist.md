# Stock Community parity worklist

Target: NetBox Community 4.7.2, excluding Branching and commercial extensions.
The source route inventory contains 1,543 website routes. Repeated aliases and
model-specific subclasses share operation families; route counts are not test
counts. This checklist tracks family closure and exceptional workflows, not a
claim that discovery alone proves parity.

| Family or special workflow | Current implementation | Remaining qualification or implementation |
| --- | --- | --- |
| Native REST model CRUD, filtering, GraphQL | MCP discovery and generic tools | Continue special model/relationship fixtures; existing greenfield agent proof |
| CSV/JSON/YAML import | Companion native import handlers | All-handler schema sweep; lifecycle, partial update, rejection, rollback and permission fixtures added; GLM run `6a0d7babb0` passed the combined bulk scenario |
| Bulk rename | Native forms plus atomic companion preview/apply | Literal/regex, stale preview and uniqueness rollback tested; additional model-specific fields and permissions |
| Bulk field edit, clearing and tag deltas | Native form/helper companion API | Site update/clear and all-handler schema sweep tested; specialized delta hooks and permissions |
| IP/prefix/VLAN range and component creation | Companion pattern API using native expansion/forms | Range and interface-template lifecycle/rollback tested; all 26 component forms and multi-parent atomic creation now live-tested |
| Bulk deletion | Native REST plus guarded companion deletion of DataFile/Job/ScriptModule | Native queue cancellation, source-file removal and data-file regeneration live-tested; cascade/constrained-permission expansion remains |
| Object child tabs, related objects, changelogs, journals | Native REST queries | Pinned route mapping covers each tab family; contacts, journals and relationship filters live-tested |
| Rack elevations, cable traces, available IP/prefix/VLAN/ASN | Native REST actions | Existing lifecycle evidence; verify remaining action variants |
| Virtual chassis membership and primary MAC selection | Native relationships plus atomic companion member swaps | Physical interface primary MAC and chassis swap/invalid/stale tests pass; VM primary MAC now live-tested; constrained permissions remain |
| Bulk disconnect | Atomic companion preview/apply | All eight native component types live-tested; permission/recovery expansion remains |
| Data-source and synchronized object actions | Native sync APIs | Worker completion, permission and failure fixtures; bulk behavior |
| Configuration rendering and exports | Native actions/export APIs | Template selection, export formats and rendering failures |
| Scripts/modules and jobs | Native REST and MCP job reconciliation | Existing worker execution; scheduling, source/results and special actions |
| Queue/worker/task administration | Native REST | Enqueue, requeue, stop, delete and worker lookup live-tested; status-list semantics |
| Configuration revisions | Companion native configuration API | Qualified deterministic lifecycle/concurrency/recovery plus GLM scenario |
| Personal dashboards | Companion validated dashboard API | Qualified deterministic lifecycle/concurrency/recovery plus GLM scenario |
| Personal preferences | Native merge plus validated companion preferences API | Partial updates, saved-table removal, ETag guards and isolation live-tested |
| Bookmarks, subscriptions and notifications | Native own-object permissions/API | Self-service lifecycles, read/dismiss/dismiss-unread equivalence |
| Profile, password and own tokens | Own profile/password companion plus native tokens | Native validation, token lifecycle, own-user isolation and password receipt redaction live-tested |
| Global search, markdown, system/plugin information, DB schema | Companion native APIs | Search scoping, malformed inputs, native rendering and superuser boundaries live-tested |
| Media and image attachments | Native upload plus companion bounded downloads | Image byte/chunk/hash/permission tests pass; both device-type image fields and DataFile binary content now live-tested |
| Browser login/logout/OAuth and presentation | Token identity and client presentation | Explicitly document identity/session boundary; own association disconnection, stale guards and last-login protection live-tested |
| Open-source third-party plugins | Dynamic discovery | Separate, plugin-specific qualification; not part of stock Community parity |
| Observability and GitHub feedback | Durable receipts, diagnostics and issue tooling | GLM run `9afd103efa` published issue #3, replayed without duplication and read the maintainer reply |

Release remains unqualified for full website parity until these remaining
workflows have action-level evidence and the consuming-agent scenarios pass.
