# Changelog

## Unreleased

- Refresh European positioning, installation and published-package documentation.

## 0.1.0a2 — 2026-11-12

- Depend on `vatly-api-python` and `vatly-fluent-python`; imports are unchanged.
- Preserve access through cancellation grace periods using Fluent's shared expiry
  mapping in signed webhooks and explicit reconciliation.
- Refresh pinned SDK/Fluent 0.1.0a2 bootstrap wheels and regression coverage.

## 0.1.0a1 — Unpublished development snapshot

Alpha — under active development. Every alpha release may include breaking changes. Pin exact versions during alpha.

- Initial Cashier-style abstract billable model, ORM storage, migrations, checkout
  and portal POST views, signed transactional webhook processing, audit and outbox.
- Host-owned checkout/entity links with PR #2910-compatible explicit reconciliation.
- Read-only admin, Django 5.2/6.0/6.1 tests and PostgreSQL concurrency CI.
- Versioned dependency bootstrap, fast orb setup and prepared trusted publishing.
