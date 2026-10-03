# Upstream feature inventory and implementation mapping

Sources checked 2026-09-30:
[official community MCP](https://github.com/netboxlabs/netbox-mcp-server),
[managed Platform MCP](https://netboxlabs.com/docs/platform-mcp/), and registered
routes from the real NetBox 4.7.2 lab in [the route inventory](netbox-4.7-surface.json).
The managed feature list is a discovery input, not a dependency or parity promise.
The product scope is fully open-source NetBox Community capabilities. Branching,
commercial change management, and other commercial NetBox Labs products are
explicitly excluded. No Branching dependency, integration or lab is included.
The table maps capabilities, not identical tool signatures.

| Capability | Local interface | Qualification |
| --- | --- | --- |
| Object queries, filters and field selection | get_objects, get_object_by_id | Real core reads, pagination and greenfield discovery |
| Changelogs | get_changelogs, get_device_history | Native history plus durable local evidence |
| Core/plugin model discovery | discover_models, get_schema(refresh via discover_models) | Stock roots and schema; plugin behavior requires that plugin's lab |
| Native dynamic filter definitions | Optional Apache-2.0 companion filter-schema API | Real custom-field changes, target permissions, discovery and cold OpenAPI generation; unknown filters rejected before inventory queries |
| Configuration revisions | Companion configuration API through `query` / `execute_action` | Live lifecycle, native cache activation, permissions, concurrency, conditional deletion and response-loss tests; no native changelog/automatic undo; GLM create/reset/cleanup qualification; privileged restore tested deterministically |
| Personal dashboards | Companion self/dashboard and dashboard-widgets APIs | All five native widgets, per-widget changes, first use/reset, exact preservation, user isolation, token permissions, concurrency, stale guards and response loss live-tested; no native history/automatic undo |
| Personal preferences | Native users/config plus companion self/preferences | Native merge plus validated partial updates, table clearing, ETag guards and isolation |
| GraphQL | graphql | Real query; no GraphQL mutation bypass |
| Single CRUD | create_object, update_object, delete_object | Real lifecycle fixtures across inventory domains |
| Native bulk requests | execute_action | List creation and protected bulk deletion; records correlated native rows and rollback |
| Native imports/bulk forms/patterns | Companion imports, bulk-rename, bulk-edit, pattern-create | Nested templates, scoped permissions, atomic batches, all component forms and stale guards |
| Export and file download | Companion exports and media | Native CSV/table/YAML/template output, image/DataFile chunks and hash guards |
| Account and personal state | Companion self APIs plus native own-object REST | Password/preferences/notifications, tokens/bookmarks/subscriptions, association disconnection and isolation |
| Operational administration | Native jobs/queues plus companion system/queue/script metadata | Worker-backed lifecycle, scheduling, registry state, native permissions |
| Chassis, disconnection and synchronized data | Native relationships and guarded companion batch APIs | Atomic swaps, all disconnect types, native sync hooks, source hashes and rollback |
| Resumable bulk workflow | bulk | Ordered per-step keys, partial failures and replay |
| Code mode | run_workflow | Bounded interpreted Python syntax, not full Python; control flow, aggregation and API helpers |
| IPs, prefixes, VLANs, ASNs | query, execute_action on native availability endpoints | Live allocation scenarios; schemas expose required inputs |
| Cable tracing and rack elevations | query | Native REST paths |
| Configuration rendering | execute_action | Native rendering endpoint |
| Script upload/execution and jobs | execute_action, query, reconcile | Real multipart upload, worker execution, acceptance/completion distinction |
| Open-source plugin/custom models | discovered resource/action paths | Native discovery; each installed open-source plugin needs its own qualification |
| Branching and commercial products | Excluded | Explicitly outside product scope; no dependencies or dedicated endpoints |
| Experimental HTML fallback | web_read, web_submit | Native session/CSRF forms; representative tests only, no JavaScript, conditional writes or automatic undo |
| Read-only connections | read_only configuration | Enforced across mutation paths |
| stdio and Streamable HTTP | CLI transports | Official SDK interoperability; HTTP bearer auth and origin checks |
| Issue feedback | diagnostic_report, optional feedback MCP or scripts/issues.py | Inventory-free structured reports; GLM publish/replay/read-maintainer-reply proof |
| Task progress and audit lookup | get_task, get_operation, observability | Compact paginated task receipts with whole-task state counts; full evidence retained for lookup and recovery |

A transport capable of submitting an action does not prove every model, GUI view,
plugin or action's semantics. The stock route inventory is the denominator for
coverage review; collection GET/OPTIONS sweeps are explicitly separate from
successful lifecycle tests. Full GUI parity and universal recovery must not be
claimed from representative tests.

The completion direction is [API-first](api-completion.md): existing endpoints,
then composed workflows, then typed plugin endpoints for confirmed gaps.
