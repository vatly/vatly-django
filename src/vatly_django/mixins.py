from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import models
from django.db.models import QuerySet

from .billing import Billing
from .models import BillingResource


class BillableMixin(models.Model):
    """Abstract, schema-free mixin for a user, team, organization, etc."""

    class Meta:
        abstract = True

    def billing(self, *, scope: str | None = None) -> Billing:
        return Billing(scope)

    def checkout(self, offer: str, *, idempotency_key: UUID | str) -> str:
        return self.billing().checkout(self, offer, idempotency_key=idempotency_key)

    def billing_portal(self) -> str:
        return self.billing().portal(self)

    def subscriptions(self) -> QuerySet[BillingResource]:
        return self.billing().resources(self, "subscription")

    def subscribed(self) -> bool:
        from django.db.models import Q
        from django.utils import timezone

        return (
            self.subscriptions()
            .filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()),
                snapshot__status__in=["active", "trial", "on_grace_period"],
            )
            .exists()
        )

    def cancel_subscription(self, id: str, *, immediately: bool = False) -> None:
        self.billing().subscription_action(self, id, "cancel", immediately=immediately)

    def resume_subscription(self, id: str) -> None:
        self.billing().subscription_action(self, id, "resume")

    def swap_subscription(self, id: str, plan_id: str, **kwargs: Any) -> None:
        self.billing().subscription_action(self, id, "swap", plan_id=plan_id, **kwargs)
