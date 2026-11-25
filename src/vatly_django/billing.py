from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import Model, QuerySet
from vatly import AsyncVatlyClient, RequestOptions
from vatly_fluent import (
    CheckoutResolution,
    CustomerProfile,
    EntityRef,
    FluentError,
    LocalSubscription,
    Vatly,
    subscription_ends_at,
)

from .models import BillingResource, BillingScope, Checkout, CheckoutAttempt, CustomerBinding
from .storage import ORMDriver, locked_scope


def entity_for(billable: Model) -> EntityRef:
    if billable.pk is None:
        raise ValueError("Save the billable before using billing")
    return EntityRef(billable._meta.label_lower, str(billable.pk))


def host_key(entity: EntityRef) -> str:
    return json.dumps([entity.kind, entity.id], separators=(",", ":"))


class Billing:
    """Synchronous Django facade; each call owns and closes its async SDK client."""

    def __init__(self, scope: str | None = None) -> None:
        self.name = scope or getattr(settings, "VATLY_SCOPE", "")
        if not isinstance(self.name, str) or not self.name:
            raise ImproperlyConfigured("VATLY_SCOPE must identify the tenant and storefront")
        self.key: str = getattr(settings, "VATLY_API_KEY", None) or os.environ.get(
            "VATLY_API_KEY", ""
        )
        if not self.key.startswith(("test_", "live_")):
            raise ImproperlyConfigured("VATLY_API_KEY is required")
        self.scope, _ = BillingScope.objects.get_or_create(
            name=self.name, testmode=self.key.startswith("test_")
        )
        self.driver = ORMDriver(self.scope)

    @asynccontextmanager
    async def fluent(self) -> AsyncIterator[Vatly]:
        async with AsyncVatlyClient(self.key) as api:
            yield Vatly(
                self.driver.wiring(
                    api=api,
                    redirect_url_success=getattr(settings, "VATLY_REDIRECT_URL_SUCCESS", ""),
                    redirect_url_canceled=getattr(settings, "VATLY_REDIRECT_URL_CANCELED", ""),
                    webhook_secret=getattr(settings, "VATLY_WEBHOOK_SECRET", None),
                )
            )

    def resources(self, billable: Model, kind: str | None = None) -> QuerySet[BillingResource]:
        entity = entity_for(billable)
        query = BillingResource.objects.filter(
            scope=self.scope, entity_kind=entity.kind, entity_id=entity.id
        )
        return query.filter(resource_type=kind) if kind else query

    def bind_customer(self, billable: Model, customer_id: str) -> None:
        """Host must authorize this customer; no remote customer creation occurs."""
        async_to_sync(self.driver.bindings.bind)(customer_id, host_key(entity_for(billable)))

    def checkout(self, billable: Model, offer: str, *, idempotency_key: UUID | str) -> str:
        entity = entity_for(billable)
        key = UUID(str(idempotency_key))
        offers = getattr(settings, "VATLY_CHECKOUTS", {})
        if offer not in offers:
            raise ValueError("Unknown checkout offer")
        # Products, quantities, return URLs and metadata are server-owned, never POST overrides.
        payload = dict(offers[offer])
        if set(payload) - {"products", "locale", "metadata", "billingAddress"}:
            raise ImproperlyConfigured("Unsupported VATLY_CHECKOUTS field")
        payload["redirectUrlSuccess"] = getattr(settings, "VATLY_REDIRECT_URL_SUCCESS", "")
        payload["redirectUrlCanceled"] = getattr(settings, "VATLY_REDIRECT_URL_CANCELED", "")
        customer_id = (
            CustomerBinding.objects.filter(scope=self.scope, host_id=host_key(entity))
            .values_list("vatly_id", flat=True)
            .first()
        )
        if customer_id:
            payload["customerId"] = customer_id
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with locked_scope(self.scope):
            attempt, _ = CheckoutAttempt.objects.get_or_create(
                scope=self.scope,
                key=key,
                defaults={
                    "entity_kind": entity.kind,
                    "entity_id": entity.id,
                    "fingerprint": fingerprint,
                },
            )
            if (attempt.entity_kind, attempt.entity_id, attempt.fingerprint) != (
                entity.kind,
                entity.id,
                fingerprint,
            ):
                raise FluentError("Idempotency key belongs to a different purchase")

        # Commit the attempt BEFORE network I/O. A timeout or failed local write keeps
        # the stable API key available for a caller's retry.
        async def create() -> str:
            async with self.fluent() as vatly:
                checkout = (
                    await vatly.checkout_builder(CustomerProfile(vatly_id=customer_id))
                    .for_entity(entity)
                    .create(payload, options=RequestOptions(idempotency_key=str(key)))
                )
                await sync_to_async(CheckoutAttempt.objects.filter(pk=attempt.pk).update)(
                    checkout_id=checkout.id
                )
                return checkout.get_url()

        return async_to_sync(create)()

    def portal(self, billable: Model) -> str:
        customer_id = (
            CustomerBinding.objects.filter(scope=self.scope, host_id=host_key(entity_for(billable)))
            .values_list("vatly_id", flat=True)
            .first()
        )
        if not customer_id:
            raise FluentError("Billable has no authorized customer binding")

        async def create() -> str:
            async with self.fluent() as vatly:
                url = getattr(settings, "VATLY_PORTAL_REDIRECT_URL", None)
                return (
                    await vatly.customer(customer_id).portal_session(
                        {"returnUrl": url} if url else {}
                    )
                ).url

        return async_to_sync(create)()

    def subscription_action(self, billable: Model, id: str, action: str, **kwargs: Any) -> None:
        if action not in {
            "cancel",
            "resume",
            "sync",
            "swap",
            "swap_and_invoice",
            "swap_without_charge",
        }:
            raise ValueError("Unknown subscription action")
        row = self.resources(billable, "subscription").filter(vatly_id=id).first()
        if row is None:
            raise PermissionDenied("Subscription does not belong to this billable")
        local = LocalSubscription(
            resource=row.snapshot, entity=entity_for(billable), ends_at=row.ends_at
        )

        async def apply() -> None:
            async with self.fluent() as vatly:
                await getattr(vatly.subscription(local), action)(**kwargs)

        async_to_sync(apply)()

    def reconcile(self, billable: Model, checkout_id: str) -> CheckoutResolution:
        entity = entity_for(billable)
        if not Checkout.objects.filter(
            scope=self.scope, vatly_id=checkout_id, entity_kind=entity.kind, entity_id=entity.id
        ).exists():
            raise PermissionDenied("Checkout does not belong to this billable")

        async def reconcile() -> CheckoutResolution:
            async with self.fluent() as vatly:
                result = await vatly.reconcile_checkout(checkout_id)
                # Explicit reconciliation is allowed to fetch; built-in reactions aren't.
                if result.order:
                    from vatly_fluent import Stored

                    current = await self.driver.orders.find_by_vatly_id(result.order.id)
                    if current:
                        await self.driver.orders.update(
                            result.order.id, {"resource": result.order, "entity": entity}
                        )
                    else:
                        await self.driver.orders.store(Stored(resource=result.order, entity=entity))
                for subscription in result.subscriptions:
                    current_sub = await self.driver.subscriptions.find_by_vatly_id(subscription.id)
                    fields: dict[str, Any] = {
                        "resource": subscription,
                        "entity": entity,
                        "ends_at": subscription_ends_at(
                            subscription, current_sub.ends_at if current_sub else None
                        ),
                    }
                    if current_sub:
                        await self.driver.subscriptions.update(subscription.id, fields)
                    else:
                        await self.driver.subscriptions.store(LocalSubscription(**fields))
                return result

        # Serializes snapshots + links together; bounded GETs may hold this lock.
        with locked_scope(self.scope):
            return async_to_sync(reconcile)()

    def webhook(self, raw: bytes, signature: str | None) -> bool:
        async def handle() -> bool:
            async with self.fluent() as vatly:
                return await vatly.webhook_processor().handle(raw, signature)

        return async_to_sync(handle)()
