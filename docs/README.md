# Vatly Django guides

**Alpha — under active development. Every alpha release may include breaking changes. Pin exact versions during alpha.**

Pushes to `main` affecting `docs/**` notify `vatly/vatly-docs`, which imports
these guides automatically. The notifier requires the Actions secret
`VATLY_DOCS_DISPATCH_TOKEN` with Contents: write access to `vatly/vatly-docs`.

- [Configuration](Configuration.md): settings, installation and authorized billables
- [Billing](Billing.md): mixin, checkout, portal, subscription lifecycle
- [Storage and webhooks](Webhooks.md): transactions, signed snapshots, outbox and recovery
- [Testing and release](Development.md): supported versions, offline tests, boot and publishing
