# Operations

The runtime accepts stable NetBox 4.7.x and later. NetBox 4.7.2 is the tested
release; later versions are accepted without claiming equivalent qualification.
Check discovery, affected workflows and recovery behavior against a test instance
before upgrading an existing deployment. The CI lab remains pinned to 4.7.2.

## Identities and credentials

Provision a dedicated non-superuser NetBox actor. Give it the native view/add/
change/delete permissions required for inventory and action permissions such as
run or render only where needed. Provide full view access to core.objectchange.
Do not grant audit-history deletion merely to manage inventory. Permissions on
configuration, scripts and users require separate deliberate operator choices.

The API token and optional website password belong to the same actor. Keep both
in mode-600 files under a protected directory. Website authentication uses native
sessions and CSRF; deployments enforcing SSO/MFA need a separately qualified
login mechanism. The password-based adapter does not bypass those controls.

The optional read_only connection policy blocks all exposed mutation paths.
For HTTP use a separate MCP bearer token, at least 32 random characters, and a
trusted TLS reverse proxy for remote use. Direct binding is loopback only. HTTP sessions expire after one hour without
a request; clients receiving 404 for an expired session must initialize again.
Durable tasks and receipts remain in the journal across session expiry.

## Evidence and retention

Set CHANGELOG_RETENTION=0 in effective NetBox configuration and disable purge
jobs. History and receipts can contain sensitive inventory. The journal uses
local SQLite WAL, synchronous FULL, append-only events, hash/projection checks,
and POSIX locks. All active processes for a deployment must share one local
journal. Do not use NFS or independent restored active copies.

Reconciliation is explicit and runs around writes; there is no background polling
while idle. Monitor observability for unresolved outcomes, archive failures,
correlation problems, tool errors and storage capacity. Tool events record name,
duration, outcome and operation ID. Hashes detect corruption; a privileged
administrator can rewrite them. Preserve independently stored backups.

```sh
netbox-readwrite-mcp --config config.json --backup /protected/new-backup.sqlite
netbox-readwrite-mcp --config config.json --export /protected/new-export.json
```

Existing destinations are refused. Back up NetBox's database too, retaining
capture times and instance lineage. A stale journal backup can miss later
operations. Never assume restoring it reconstructs missing intent.

## Existing journal migration

Existing events are preserved. The general-operation projection is an additive
table; opening a journal does not rewrite historical events. URL, lineage, actor
and scope remain bound to that journal. A restricted device journal does not
become general-purpose just because allowed_device_ids is removed from config.

For an established deployment, stop writers, back up both evidence stores,
reconcile all pending work, and review the scope transition before provisioning
a new broad-scope lineage/journal. Retain the previous journal for correction of
its existing operations. Do not create a new journal to evade unresolved work.
A new greenfield deployment starts directly with the broad configuration.

## Recovery and upgrades

On a storage or history failure stop mutation and restore observability first.
For uncertain operations preserve original keys and use reconciliation. Absence
of a matching change does not establish non-commit. Async job failures can have
partial effects. There is no force-resolution command.

preview_undo returns ready only for a verified correction contract. General
PATCH compensation detects same-field ABA and preserves unrelated fields.
Graph operations, creates/deletes, bulk changes, scripts and website actions may
require guided recovery. Exact original-ID graph restoration still requires the
proposed NetBox-side recovery extension; native REST recreation changes IDs.
Do not represent guided recovery as automatically completed undo.

Before a NetBox upgrade, test paired copies of the database and journal. Native
history may change under migrations; archived-row mismatches remain blocking.
Never rewrite archived evidence or start a new journal to suppress them.

The target deployment is a small home lab (roughly 1000 or fewer assets).
Full history scans favor a simple implementation. High availability, distributed
storage and large-estate throughput are not current qualification targets.

## Native history serialization

History synchronization requests immutable audit fields explicitly: IDs, time,
actor name, request ID, action, object type/ID, stored representation/message and
before/after snapshots. It omits live expanded object/user references. NetBox
4.7.2 can return HTTP 500 while expanding a live port-mapping change record; its
immutable fields remain readable. These are the same fields already retained in
the journal, so this transport change does not alter archived record hashes or
require resetting history. The client still fails closed if audit reads fail.

## Release upgrades

Keep the configuration directory, token and journal when updating the MCP
application. Replace the downloaded application at the same path (or upgrade the
wheel in its existing environment), reconnect the client and run `doctor`.
Do not run a new setup wizard or generate a new instance ID for a package upgrade.

For a container-bundle upgrade, retain the old extracted directory before
unpacking the new release into a clean `netbox-agent-api` directory. Recreate web
and worker with the updated mount. Do not overlay different wheel versions in
one plugin directory: stale files or duplicate distribution metadata could remain.
Traditional installs upgrade the wheel in each NetBox environment and restart
both processes. Keep the prior package/bundle for rollback. Native NetBox upgrades
remain managed by your existing deployment procedure, independently of our assets.


## Download snapshots

The companion reuses native export output and media bytes across chunk requests.
Continue with `next_offset`, passing the first response's `sha256` as
`expected_sha256`. Access is checked on every request, including cached reads.
Object revisions, selected visibility, file metadata and export-template permissions
are checked before reuse.
Export membership/revision queries still run per chunk; rendering and full byte
reads do not. Snapshots freeze the generated bytes, including related-object values,
until a detected revision change, replacement, eviction or expiration.

The native Django cache holds fixed 64 KiB blocks, with one media slot and one
export slot per user and a five-minute TTL. Switching downloads can replace a
slot; concurrent replacement or missing blocks returns 412 rather than mixed
content. Cache loss can regenerate output, subject to the original SHA guard.
Use the usual shared NetBox cache across web workers. Cache contents are private
inventory and belong within the same trusted boundary as NetBox itself.

The default maximum is 16 MiB per snapshot, advertised as `snapshot_limits` in
the media catalog and model-specific export schema. Oversized snapshots return
413. Operators can raise the bound in their existing NetBox configuration:

```python
PLUGINS_CONFIG.setdefault("netbox_agent_api", {})["download_snapshot_max_bytes"] = 64 * 1024 * 1024
```

Restart web and worker processes after changing it. Raising the bound increases
cache storage and initial rendering memory; native non-streaming renderers can
materialize output before the bound is checked.

## Credential-bearing intent fingerprints

New general-operation, workflow-source and workflow-step fingerprints use random
salts and scrypt instead of fast deterministic SHA-256. Known password fields in
nested intent payloads are redacted while the original payload is dispatched.
The journal remains private: slow salted hashes increase offline guessing cost,
but do not make weak passwords or arbitrary secret-bearing payloads safe to expose.

Existing immutable evidence is not rewritten. Old SHA-256 fingerprints remain
readable for exact replay and retain their historical exposure. If an old journal
containing password operations was exposed, rotate those credentials; upgrading
does not remove copies of the old evidence. No additional key file or migration
is required for new fingerprints.
