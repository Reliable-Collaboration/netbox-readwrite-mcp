# NetBox Read/Write MCP

An Apache-2.0 MCP server for agent edits to NetBox, with retained previous values,
visible outcomes, and optimistic undo that refuses to overwrite newer work.

Development is taking place on `feat/auditable-write-recovery`. Version 0.1
will support a deliberately bounded device-update contract; it is not a universal
NetBox CRUD or graph-restore engine.

Based on [preliminary research and hands-on spikes](https://github.com/reliable-collaboration/netbox-write-research).
See [JOURNAL.md](JOURNAL.md) for development decisions and validation.
