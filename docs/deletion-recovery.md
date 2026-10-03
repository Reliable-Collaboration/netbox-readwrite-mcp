# Deletion recovery: investigation outcome

The deeper [research report](https://github.com/Reliable-Collaboration/netbox-write-research/blob/research/agentic-write-spikes/research/deletion-recovery.md)
and [reproducible spike](https://github.com/Reliable-Collaboration/netbox-write-research/tree/research/agentic-write-spikes/spikes/deletion-recovery)
change the architectural recommendation: **prefer a focused NetBox recovery plugin
that restores original IDs and the affected object graph.** Ordinary REST POST
assigns new IDs, but NetBox 4.7.1 already has an internal deserialization helper
accepting an original primary key. The plugin can reuse Apache-licensed core
machinery without adopting the restricted Branching plugin or replacing PostgreSQL.

Fourteen tests passed against real 4.7.1 models, serializers, middleware, signals
and PostgreSQL via Django's test client. They demonstrated same-ID restoration of
sites, tags, interfaces/IP assignments, cable terminations, and a hierarchical
region. They also demonstrated why a generic deserialize-and-save endpoint is
insufficient: occupied IDs can be overwritten, missing tags can be silently lost,
and restoration of a parent alone can leave dependent state missing. Surviving
objects changed by the original deletion need separate conflict-aware correction.

A user who accidentally deletes an object today can inspect all native changes
for the request, recreate a simple object through UI/REST, or enlist an administrator
for tested original-ID recovery. If historical evidence is incomplete, restore a
backup into an isolated instance to recover the missing graph. Stock 4.7.1 has no
general undelete REST endpoint or recycle bin. Recreating an object is not the same
as restoring its identity and relationships.

The proposed plugin should capture raw/versioned recovery evidence, plan the
whole affected graph, enforce permissions and conflicts, perform insert-only
restoration in a database transaction, and retain idempotent recovery receipts
alongside new native change history. Future capture should cover human UI/API
operations too. Existing history can support retrospective recovery where complete;
it cannot recover pruned data or missing file contents.

The experiments roll back each test's writes and do not qualify concurrent
restoration, constrained-user permissions, crash durability, arbitrary plugins,
or every NetBox model. No recovery plugin was implemented in this research step. Subsequent 0.3.0
work adds broad CRUD execution and field compensation; original-ID graph
restoration still requires the extension described here. The next implementation needs the full model/action coverage matrix.
