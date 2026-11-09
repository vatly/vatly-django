"""Thread-sensitive adapters keep Fluent's async work in the ORM transaction thread."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any, Generic, TypeVar

from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone
from vatly.models import Chargeback, Order, Refund
from vatly.webhooks import VatlyWebhookEvent
from vatly_fluent import (
    CheckoutRecord,
    DomainEvent,
    EntityRef,
    FluentError,
    LocalEvent,
    LocalSubscription,
    Stored,
    Wiring,
)

from .models import (
    BillingResource,
    BillingScope,
    Checkout,
    CustomerBinding,
    Outbox,
    ResourceLink,
    WebhookCall,
)

T = TypeVar("T", bound=Stored[Any])


@contextmanager
def locked_scope(scope: BillingScope) -> Iterator[None]:
    with transaction.atomic():
        # UPDATE acquires the database write lock even on SQLite (no FOR UPDATE).
        # PostgreSQL holds this row lock until the outermost transaction commits.
        BillingScope.objects.filter(pk=scope.pk).update(revision=F("revision") + 1)
        yield


class ORMRepository(Generic[T]):
    def __init__(self, scope: BillingScope, kind: str, model: type[T]) -> None:
        self.scope, self.kind, self.model = scope, kind, model

    def _query(self) -> QuerySet[BillingResource]:
        return BillingResource.objects.filter(scope=self.scope, resource_type=self.kind)

    def _decode(self, row: BillingResource) -> T:
        return self.model.model_validate(
            {
                "resource": row.snapshot,
                "entity": EntityRef(row.entity_kind, row.entity_id)
                if row.entity_kind is not None and row.entity_id is not None
                else None,
                **({"ends_at": row.ends_at} if self.kind == "subscription" else {}),
            }
        )

    def _fields(self, data: T) -> dict[str, Any]:
        if data.resource.testmode != self.scope.testmode:
            raise FluentError("Resource mode mismatch")
        return {
            "snapshot": data.resource.model_dump(mode="json", by_alias=True),
            "entity_kind": data.entity.kind if data.entity else None,
            "entity_id": data.entity.id if data.entity else None,
            "ends_at": data.ends_at if isinstance(data, LocalSubscription) else None,
        }

    @sync_to_async
    def find_by_vatly_id(self, id: str) -> T | None:
        row = self._query().filter(vatly_id=id).first()
        return self._decode(row) if row else None

    @sync_to_async
    def store(self, data: T) -> T:
        with locked_scope(self.scope):
            BillingResource.objects.create(
                scope=self.scope,
                resource_type=self.kind,
                vatly_id=data.resource.id,
                **self._fields(data),
            )
        return data

    @sync_to_async
    def update(self, id: str, data: dict[str, Any]) -> T:
        with locked_scope(self.scope):
            row = self._query().get(vatly_id=id)
            current = self._decode(row)
            merged = self.model.model_validate({**current.model_dump(), **data})
            if current.entity and merged.entity != current.entity:
                raise FluentError("Refusing to reassign resource ownership")
            if merged.resource.id != id:
                raise FluentError("Resource ID is immutable")
            for name, value in self._fields(merged).items():
                setattr(row, name, value)
            row.save()
            return merged

    @sync_to_async
    def list_for_order(self, id: str) -> list[T]:
        return [self._decode(row) for row in self._query().filter(snapshot__originalOrderId=id)]

    @sync_to_async
    def list_for_customer(self, id: str) -> list[T]:
        return [self._decode(row) for row in self._query().filter(snapshot__customerId=id)]


class ORMCheckouts:
    def __init__(self, scope: BillingScope) -> None:
        self.scope = scope

    def _record(self, row: Checkout) -> CheckoutRecord:
        return CheckoutRecord(
            row.vatly_id, EntityRef(row.entity_kind, row.entity_id), self.scope.testmode
        )

    @sync_to_async
    def record(self, data: CheckoutRecord) -> None:
        if data.testmode != self.scope.testmode:
            raise FluentError("Checkout mode mismatch")
        with locked_scope(self.scope):
            row, _ = Checkout.objects.get_or_create(
                scope=self.scope,
                vatly_id=data.checkout_id,
                defaults={"entity_kind": data.entity.kind, "entity_id": data.entity.id},
            )
            if self._record(row) != data:
                raise FluentError("Refusing to reassign checkout ownership")

    @sync_to_async
    def find(self, checkout_id: str) -> CheckoutRecord | None:
        row = Checkout.objects.filter(scope=self.scope, vatly_id=checkout_id).first()
        return self._record(row) if row else None

    @sync_to_async
    def link(self, checkout_id: str, resource_type: str, resource_id: str) -> None:
        with locked_scope(self.scope):
            checkout = Checkout.objects.get(scope=self.scope, vatly_id=checkout_id)
            link, _ = ResourceLink.objects.get_or_create(
                scope=self.scope,
                resource_type=resource_type,
                vatly_id=resource_id,
                defaults={"checkout": checkout},
            )
            if link.checkout_id != checkout.pk:
                raise FluentError("Resource is already linked to another checkout")

    @sync_to_async
    def find_for_resource(self, resource_type: str, resource_id: str) -> CheckoutRecord | None:
        row = (
            ResourceLink.objects.select_related("checkout")
            .filter(scope=self.scope, resource_type=resource_type, vatly_id=resource_id)
            .first()
        )
        return self._record(row.checkout) if row else None


class ORMBindings:
    def __init__(self, scope: BillingScope) -> None:
        self.scope = scope

    @sync_to_async
    def record(self, vatly_id: str) -> None:
        with locked_scope(self.scope):
            CustomerBinding.objects.get_or_create(scope=self.scope, vatly_id=vatly_id)

    @sync_to_async
    def bind(self, vatly_id: str, host_id: str) -> None:
        with locked_scope(self.scope):
            row, _ = CustomerBinding.objects.get_or_create(scope=self.scope, vatly_id=vatly_id)
            if row.host_id not in (None, host_id):
                raise FluentError("Customer is already bound")
            if (
                CustomerBinding.objects.filter(scope=self.scope, host_id=host_id)
                .exclude(pk=row.pk)
                .exists()
            ):
                raise FluentError("Host is already bound")
            row.host_id = host_id
            row.save(update_fields=["host_id"])

    @sync_to_async
    def vatly_customer_id_for(self, host_id: str) -> str | None:
        return (
            CustomerBinding.objects.filter(scope=self.scope, host_id=host_id)
            .values_list("vatly_id", flat=True)
            .first()
        )

    @sync_to_async
    def host_customer_id_for(self, vatly_id: str) -> str | None:
        return (
            CustomerBinding.objects.filter(scope=self.scope, vatly_id=vatly_id)
            .values_list("host_id", flat=True)
            .first()
        )


class ORMDriver:
    def __init__(self, scope: BillingScope) -> None:
        self.scope = scope
        self.checkouts = ORMCheckouts(scope)
        self.bindings = ORMBindings(scope)
        self.orders = ORMRepository(scope, "order", Stored[Order])
        self.subscriptions = ORMRepository(scope, "subscription", LocalSubscription)
        self.refunds = ORMRepository(scope, "refund", Stored[Refund])
        self.chargebacks = ORMRepository(scope, "chargeback", Stored[Chargeback])

    @sync_to_async
    def process(self, event: VatlyWebhookEvent, work: Callable[[], Awaitable[None]]) -> bool:
        if event.testmode != self.scope.testmode:
            raise FluentError("Webhook mode mismatch")
        with locked_scope(self.scope):
            if WebhookCall.objects.filter(scope=self.scope, event_id=event.id).exists():
                return False
            row = WebhookCall.objects.create(
                scope=self.scope,
                event_id=event.id,
                event_name=event.event_name,
                envelope=event.model_dump(mode="json", by_alias=True),
            )
            async_to_sync(work)()
            row.processed_at = timezone.now()
            row.save(update_fields=["processed_at"])
            return True

    @sync_to_async
    def dispatch(self, event: DomainEvent) -> None:
        payload = (
            {
                "eventName": event.event_name,
                "object": event.object.model_dump(mode="json", by_alias=True),
            }
            if isinstance(event, LocalEvent)
            else event.model_dump(mode="json", by_alias=True)
        )
        Outbox.objects.create(scope=self.scope, event_name=event.event_name, payload=payload)

    def wiring(self, **kwargs: Any) -> Wiring:
        return Wiring(
            **kwargs,
            checkouts=self.checkouts,
            bindings=self.bindings,
            orders=self.orders,
            subscriptions=self.subscriptions,
            refunds=self.refunds,
            chargebacks=self.chargebacks,
            webhook_calls=self,
            events=self,
        )
