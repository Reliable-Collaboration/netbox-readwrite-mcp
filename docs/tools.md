# Tool reference

Compatibility is exactly NetBox 4.7.2. Both stdio and authenticated loopback
Streamable HTTP expose the same tools. Tool schemas are returned by tools/list;
unknown arguments and incorrect types are refused. Native NetBox validation
remains authoritative for payload fields and action-specific requirements.

| Tools | Purpose |
| --- | --- |
| capabilities | Actual connection scope, exact version, read-only policy and recovery limits |
| discover_models(refresh=false) | Discover core and installed plugin API roots, collections and actions |
| get_schema(object_type, full?, action?) | Native OPTIONS/OpenAPI schemas, required fields, choices and actions |
| get_objects(object_type, filters?, fields?, limit?, offset?) | Filtered, paginated collection reads; resource path or unambiguous name |
| get_object_by_id(object_type, object_id, fields?) | Object data and ETag |
| get_changelogs(filters?, limit?, offset?) | Native audit history |
| query(path, filters?) | GET for any relative API path, including specialized actions |
| graphql(query, variables?) | Query-only GraphQL |
| begin_task(purpose) | Durable task ID |
| create_object(task_id, operation_key, object_type, data) | Native create with durable intent |
| update_object(task_id, operation_key, object_type, object_id, expected_etag, data) | Conditional PATCH |
| delete_object(task_id, operation_key, object_type, object_id, expected_etag) | Conditional DELETE with retained pre-image/cascade evidence |
| execute_action(task_id, operation_key, method, path, data?, expected_etag?, files?) | Native POST/PUT/PATCH/DELETE, list payloads and multipart uploads |
| bulk(task_id, operation_key, operations) | Ordered CRUD/action steps, derived keys, stops on failure/uncertainty |
| run_workflow(task_id, operation_key, code) | Bounded Python-syntax interpreter with controlled tool calls |
| web_read(path) | Experimental native forms/links/text or base64 download |
| web_submit(task_id, operation_key, path, data, files?) | Native form submission with CSRF and journal evidence |
| find_operation(operation_key), get_operation(operation_id), get_task(task_id, full=false, limit=25, offset=0) | Durable outcome lookup; task results default to paginated compact receipts and whole-task state counts. Full details remain available by operation ID or an expanded task page. |
| preview_undo(operation_id), undo_operation(operation_id, operation_key), undo_task(task_id) | Conflict-aware compensation or explicit guided-recovery result |
| reconcile | Refresh history, resolve provable unknown outcomes and track recognized asynchronous jobs |
| observability | Integrity, freshness, event/state counts and unresolved operations |
| recovery_bundle(operation_id) | Private retained evidence; never publish to GitHub |
| diagnostic_report(operation_id?) | Inventory-free diagnostic issue attachment |
| read_device, update_device, get_device_history | Existing narrow device workflow retained for established journals and regression tests |

Operation keys are 8–160 ASCII letters, digits, periods, underscores, colons or
hyphens (workflow keys: at most 120). Bulk child keys append `.index`; leave room
for that suffix. List reads default to 100 and accept up to 1000 records per page.

Relative API paths end in `/` and exclude queries, traversal and origins. Pass
filters separately for reads. `files` is a list of `{field, filename, base64,
content_type?}`. No tool reads arbitrary agent-supplied local file paths.

## Outcomes

| State | Meaning |
| --- | --- |
| prepared / dispatched | Durable intent / possible dispatch; inspect before acting |
| uncertain | Response unavailable or ambiguous; never blindly retry |
| applied | Correlated native change evidence retained; inspect all affected objects |
| completed | HTTP exchange completed, without verified mutation evidence; inspect its semantic result |
| accepted | Recognized async job accepted; reconcile tracks its status |
| job_completed / job_failed | Native job terminal status; inspect output and possible partial effects |
| failed | Definite rejection or abandoned before dispatch |
| no_change | Existing guarded device path found no effective change |
| applied_unverified | Existing device path has HTTP success but lacks verified native evidence |

Undo assessments include ready, conflicted, guided_recovery, blocked,
already_undone, correction_pending and incomplete_restore. A normal tool result
can contain a conflict or failure: inspect structured state, not only isError.

Native validation/permission errors remain durable failed receipts, including
field errors. Transport/tool errors carry a stable code, recovery guidance,
automatic_retry_allowed=false and receipt lookup when available. An exception
never proves a remote write did not commit.

Schema discovery defaults to compact collection POST schemas and filter names.
Use `action="available-ips"` to inspect a single action's inputs.
Use `full=true` for complete OPTIONS, action definitions, response schemas
and descriptions; full responses can exceed an agent client's output limit.
HTML submissions lack ETag/concurrent-edit protection and automatic undo.
