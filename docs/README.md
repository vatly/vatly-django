# Vatly Django

Add hosted checkout, customer billing and signed webhook persistence to Django.
Vatly is the European merchant of record for AI, software and digital products.
This package builds on Fluent Python and the Python SDK.

**Alpha — under active development. Every alpha release may include breaking changes. Pin exact versions during alpha.**

## Start here

```bash
python -m pip install vatly-django==0.1.0a2
```

Follow [Installation](Installation.md) to add the app, URLs and database tables,
then configure a server-owned product offer and add a checkout form. You do not
need a custom user model: the `Billing` facade accepts any saved Django model.

| Guide | Task |
| --- | --- |
| [Installation](Installation.md) | Install, connect URLs and run migrations |
| [Configuration](Configuration.md) | Set credentials, offers and tenant scope |
| [Billable models](BillableModels.md) | Add billing helpers to your user or team model |
| [Checkout](Checkout.md) | Start a purchase with a durable retry key |
| [Customer portal](CustomerPortal.md) | Open hosted billing for an authorized customer |
| [Subscriptions](Billing.md) | Inspect, cancel, resume and reconcile owned subscriptions |
| [Webhooks](Webhooks.md) | Verify, deduplicate and persist deliveries atomically |
| [Admin](Admin.md) | Inspect billing records without editing them |
| [Testing](Testing.md) | Exercise checkout and signed webhooks offline |
| [Development](Development.md) | Run contributor checks and understand release tooling |

Python 3.10+; Django 5.2 LTS, 6.0 and 6.1 within their supported Python ranges.
Code samples are executed with the published `0.1.0a2` packages and local fixtures.
See the [API reference](https://docs.vatly.com/api-reference) for Vatly's fields.
