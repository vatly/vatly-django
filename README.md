# Vatly Django

**Alpha — under active development. Every alpha release may include breaking changes. Pin exact versions during alpha.**

Billing helpers for Django user and team models, built on [Vatly Fluent Python](https://github.com/vatly/vatly-fluent-python).
Vatly is the European Merchant of Record for AI, software and digital products.
Python 3.10+; Django 5.2 LTS, 6.0 and 6.1 (6.x requires Python 3.12+).

```python
INSTALLED_APPS = [*INSTALLED_APPS, "vatly_django"]
VATLY_SCOPE = "my-tenant/my-storefront"
VATLY_API_KEY = os.environ["VATLY_API_KEY"]
VATLY_WEBHOOK_SECRET = os.environ["VATLY_WEBHOOK_SECRET"]
VATLY_REDIRECT_URL_SUCCESS = "https://app.example.com/billing/success"
VATLY_REDIRECT_URL_CANCELED = "https://app.example.com/billing/canceled"
VATLY_CHECKOUTS = {"pro": {"products": [{"id": "subscription_plan_...", "quantity": 1}]}}
```

Install `vatly-django==0.1.0a2`, add
`path("billing/", include("vatly_django.urls"))`, run `python manage.py migrate`.
For development, clone and run `.agents/setup`; locked uv sources use versioned
SDK/Fluent wheels from `vendor/`.

```python
from uuid import uuid4
from vatly_django.billing import Billing

billing = Billing()
# user/team must already be authorized by your app. Save this key for retries.
url = billing.checkout(user, "pro", idempotency_key=uuid4())
# Bind an authorized existing Vatly customer to enable portal checkout identity.
billing.bind_customer(user, existing_customer_id)
portal_url = billing.portal(user)
```

Or inherit `BillableMixin` on your user/team model to get `checkout`,
`billing_portal`, `subscriptions`, `subscribed`, cancel/resume/swap helpers.
The mixin is abstract and adds no columns or auth-user coupling.

- Host-owned checkout records assign orders/subscriptions; **never customerId**.
- Signed webhooks atomically deduplicate, persist snapshots/links and enqueue outbox events.
- Read-only admin; CSRF-protected, login-required checkout/portal POST views.
- Raw SDK and async Fluent remain available for advanced integration.
- Initial `subscription_plan` lines cannot identify a subscription in this alpha.
  Revised core PR #2910 adds related-resource correlation; consuming it still needs
  a package update. `Billing.reconcile` reports legacy IDs instead of guessing access.

[Guides for vatly-docs sync](docs/README.md) cover configuration, ownership, transactions,
outbox delivery, testing and release. No tags/publication are performed by setup or CI.

```bash
.agents/setup
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python -m django makemigrations --check --dry-run --settings=tests.settings
uv build && uv run twine check dist/*
```
