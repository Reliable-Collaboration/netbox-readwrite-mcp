# Security policy and trust boundary

This is an actively developed release. There is no paid service, SLA, or security certification.

For a suspected vulnerability, use GitHub's private vulnerability reporting for this repository if enabled. Otherwise open an issue requesting a private contact without publishing credentials, exploit details, or private inventory.

The trusted boundary includes the MCP host, server OS account, token file, local filesystem, NetBox/proxy deployment, native history access, and operator backups. Agents must not receive the raw token or unrestricted access to the journal. The transports are stdio and authenticated loopback HTTP. This is not a multi-tenant service.

A prompt-injected description remains data, but a model can still choose an allowed harmful edit. Least privilege, explicit object scope, deterministic validation, direct receipt display, and recoverability reduce consequences; they do not prove an agent's decisions correct.

Redirects are not followed. HTTPS is required outside loopback. Mutations are never automatically retried. The token is not intentionally stored in the journal, but user-supplied fields and server receipts are retained and can contain sensitive data. Do not put secrets in edit purposes or inventory fields.

Append-only triggers and hashes are integrity checks, not protection against a privileged filesystem or database administrator. Complete evidence deletion or rewriting remains possible for trusted administrators. Independent retention and access controls are operational requirements.
