# Changelog

## 0.1.0a4 — 2026-11-25

- Require `vatly-fluent-python==0.1.0a4` and `vatly-api-python==0.1.0a4`.
- Stored refund snapshots include `metadata`, the metadata sent when the refund was
  created, or null.
- `Billing.checkout` checks the configured `VATLY_CHECKOUTS` offer against the API
  schema and raises `ImproperlyConfigured` before recording a purchase attempt or
  calling Vatly. Metadata values must be strings (at most 50 keys, keys up to 40 and
  values up to 500 characters); `trialDays` must be at least 1.
- Behaviour change from the SDK: subscription action keyword arguments are validated
  before sending, so invalid input raises Pydantic's `ValidationError` instead of
  `VatlyValidationError`; fields the API schema does not define are dropped.

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
