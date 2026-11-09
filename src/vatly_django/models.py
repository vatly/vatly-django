from django.db import models


class BillingScope(models.Model):
    """Tenant + storefront + mode boundary; also serializes local billing writes."""

    name = models.CharField(max_length=200)
    testmode = models.BooleanField()
    revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "testmode"], name="vatly_scope")]


class ScopedModel(models.Model):
    scope = models.ForeignKey(BillingScope, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class CustomerBinding(ScopedModel):
    vatly_id = models.CharField(max_length=200)
    host_id = models.CharField(max_length=300, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "vatly_id"], name="vatly_customer"),
            models.UniqueConstraint(fields=["scope", "host_id"], name="vatly_host"),
        ]


class Checkout(ScopedModel):
    vatly_id = models.CharField(max_length=200)
    entity_kind = models.CharField(max_length=200)
    entity_id = models.CharField(max_length=200)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "vatly_id"], name="vatly_checkout")]


class ResourceLink(ScopedModel):
    checkout = models.ForeignKey(Checkout, on_delete=models.PROTECT)
    resource_type = models.CharField(max_length=30)
    vatly_id = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "resource_type", "vatly_id"], name="vatly_resource_link"
            )
        ]


class BillingResource(ScopedModel):
    """Complete signed SDK snapshots; host ownership is separate from customerId."""

    resource_type = models.CharField(max_length=30)
    vatly_id = models.CharField(max_length=200)
    entity_kind = models.CharField(max_length=200, null=True, blank=True)
    entity_id = models.CharField(max_length=200, null=True, blank=True)
    snapshot = models.JSONField()
    ends_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "resource_type", "vatly_id"], name="vatly_billing_resource"
            )
        ]
        indexes = [models.Index(fields=["scope", "entity_kind", "entity_id"])]


class WebhookCall(ScopedModel):
    event_id = models.CharField(max_length=200)
    event_name = models.CharField(max_length=200)
    envelope = models.JSONField()
    processed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "event_id"], name="vatly_event")]


class Outbox(ScopedModel):
    event_name = models.CharField(max_length=200)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)


class CheckoutAttempt(ScopedModel):
    """Durable purchase identity; retry with the same key after ambiguous failure."""

    key = models.UUIDField()
    entity_kind = models.CharField(max_length=200)
    entity_id = models.CharField(max_length=200)
    fingerprint = models.CharField(max_length=64)
    checkout_id = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["scope", "key"], name="vatly_purchase_key")]
