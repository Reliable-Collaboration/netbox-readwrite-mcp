# Contributing

Changes belong on feature branches with descriptive commits. Run the offline suite, lint/format checks, and relevant real-NetBox integration tests before proposing a change. Include the problem, resulting behavior, validation, and limitations in a pull request.

Any new writable field/model needs a documented recovery contract and tests for stale state, dependencies, no-ops, native validation, lost responses, crash phases, and correction conflicts. See docs/edit-contract.md. Never weaken a guard to make a happy-path demo pass.

Preserve append-only evidence and conservative uncertain outcomes. Do not add automatic mutation retries, a force-undo switch, or silent retention policies. Scope, schema, and journal migrations require explicit design and recovery tests.

Keep source, documentation, and dependencies compatible with an entirely open-source deployment. Contributions are under Apache-2.0; preserve third-party notices. Never commit tokens, private inventory, .lab data, or real recovery bundles.

No established production stability claim is made for 0.1. Before a release, record exact tested versions, build/install the wheel, scan tracked files for credentials, and publish validation limits alongside results.
