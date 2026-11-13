# Changelog

## 0.1.0a3 — 2026-11-13

- Require `vatly-fluent-python==0.1.0a3` and `vatly-api-python==0.1.0a3` from PyPI;
  drop the vendored bootstrap wheels.
- Initial orders now link to their subscriptions through
  `lines[].relatedResources.subscriptionId` in signed `order.paid`/`checkout.paid`
  webhooks and `Billing.reconcile`.
- `Billing.reconcile` returns `unresolved_line_ids` for signup lines whose
  `subscriptionId` is still null; reconcile again later (it may never resolve).
- Behaviour change: `legacy_plan_ids` now lists only plan lines without
  `relatedResources` (historical orders), no longer every plan line.
- Refresh European positioning, installation and published-package documentation.

## 0.1.0a2 — 2026-11-12

- Depend on `vatly-api-python` and `vatly-fluent-python`; imports are unchanged.
- Preserve access through cancellation grace periods using Fluent's shared expiry
  mapping in signed webhooks and explicit reconciliation.
- Refresh pinned SDK/Fluent 0.1.0a2 bootstrap wheels and regression coverage.

## 0.1.0a1 — Unpublished development snapshot

Alpha — under active development. Every alpha release may include breaking changes. Pin exact versions during alpha.

- Initial abstract model with billing helpers, ORM storage, migrations, checkout
  and portal POST views, signed transactional webhook processing, audit and outbox.
- Host-owned checkout/entity links with PR #2910-compatible explicit reconciliation.
- Read-only admin, Django 5.2/6.0/6.1 tests and PostgreSQL concurrency CI.
- Versioned dependency bootstrap, fast orb setup and prepared trusted publishing.
