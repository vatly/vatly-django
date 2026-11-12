import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import Client
from django.utils import timezone
from vatly import AsyncVatlyClient, VatlyConnectionError
from vatly.models import Subscription
from vatly.webhooks import compute_signature_v1
from vatly_fluent import CheckoutRecord, FluentError, LocalSubscription

from vatly_django.billing import Billing, entity_for
from vatly_django.mixins import BillableMixin
from vatly_django.models import (
    BillingResource,
    Checkout,
    CheckoutAttempt,
    Outbox,
    ResourceLink,
    WebhookCall,
)
from vatly_django.storage import ORMDriver

pytestmark = pytest.mark.django_db(transaction=True)
FIXTURES = json.loads((Path(__file__).parent / "fixtures/resources.json").read_text())


def resource(name, **fields):
    return {**deepcopy(FIXTURES[name]), "testmode": True, **fields}


def signed(name, obj, event_id=None, testmode=True):
    raw = json.dumps(
        {
            "id": event_id or "event_" + name,
            "resource": "webhook_event",
            "eventName": name,
            "reason": None,
            "entityType": obj.get("resource", "future"),
            "entityId": obj.get("id", "future_1"),
            "object": obj,
            "createdAt": "2026-01-01T00:00:00Z",
            "testmode": testmode,
        }
    ).encode()
    stamp = int(time.time())
    return raw, f"t={stamp},v1=" + compute_signature_v1(raw, "test-signing-secret", stamp)


@pytest.fixture
def mock_api(monkeypatch):
    calls, responses = [], []

    def respond(request):
        calls.append(request)
        if not responses:
            raise AssertionError("Unexpected remote request")
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    monkeypatch.setattr(
        "vatly_django.billing.AsyncVatlyClient",
        lambda key: AsyncVatlyClient(key, transport=httpx.MockTransport(respond), max_retries=0),
    )
    return calls, responses


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="owner", email="owner@example.test")


def deliver(client, name, obj, event_id=None, testmode=True):
    raw, sig = signed(name, obj, event_id, testmode)
    return client.post("/webhook/", raw, content_type="application/json", HTTP_VATLY_SIGNATURE=sig)


@pytest.mark.parametrize(
    "sequence", list(itertools.permutations(["checkout", "order", "subscription"]))
)
def test_signed_snapshots_link_from_own_checkout_in_every_order(client, user, mock_api, sequence):
    billing = Billing()
    async_to_sync(billing.driver.checkouts.record)(
        CheckoutRecord("checkout_owned", entity_for(user), True)
    )
    checkout = resource("Checkout", id="checkout_owned", orderId="order_owned")
    order = resource("Order", id="order_owned")
    order["lines"][0].update(productType="subscription", productId="subscription_owned", quantity=4)
    subscription = resource("Subscription", id="subscription_owned")
    events = {
        "checkout": ("checkout.paid", checkout),
        "order": ("order.paid", order),
        "subscription": ("subscription.started", subscription),
    }
    for kind in sequence:
        assert deliver(client, *events[kind]).status_code == 200
    assert billing.resources(user).count() == 2
    assert ResourceLink.objects.count() == 2
    assert Outbox.objects.count() == 5
    assert WebhookCall.objects.filter(processed_at__isnull=False).count() == 3
    assert deliver(client, *events[sequence[0]]).content == b"duplicate"
    assert Outbox.objects.count() == 5
    assert mock_api[0] == []  # Built-ins preserve signed snapshots; zero implicit GETs.


def test_customer_identity_never_assigns_ownership(client, user, mock_api):
    billing = Billing()
    billing.bind_customer(user, "customer_shared")
    assert (
        deliver(
            client, "subscription.started", resource("Subscription", customerId="customer_shared")
        ).status_code
        == 200
    )
    assert billing.resources(user).count() == 0
    assert BillingResource.objects.get().entity_id is None


def test_signatures_unknown_mode_and_method_boundaries(client, mock_api):
    raw, sig = signed("future.event", {"id": "future_1"})
    assert client.post("/webhook/", raw, content_type="application/json").status_code == 400
    assert (
        client.post(
            "/webhook/", raw + b" ", content_type="application/json", HTTP_VATLY_SIGNATURE=sig
        ).status_code
        == 400
    )
    assert WebhookCall.objects.count() == 0
    assert client.get("/webhook/").status_code == 405
    assert (
        client.post(
            "/webhook/", raw, content_type="application/json", HTTP_VATLY_SIGNATURE=sig
        ).status_code
        == 200
    )
    assert Outbox.objects.get().payload["object"] == {"id": "future_1"}
    with pytest.raises(FluentError, match="mode"):
        deliver(client, "future.event", {"id": "x"}, "event_live", testmode=False)
    assert WebhookCall.objects.count() == 1


def test_atomic_rollback_includes_audit_resource_and_outbox(client, mock_api, monkeypatch):
    original = ORMDriver.__dict__["dispatch"]

    async def fail(self, event):
        await original.__get__(self, ORMDriver)(event)
        raise RuntimeError("outbox failure")

    monkeypatch.setattr(ORMDriver, "dispatch", fail)
    obj = resource("Subscription")
    with pytest.raises(RuntimeError, match="outbox failure"):
        deliver(client, "subscription.started", obj)
    assert (
        WebhookCall.objects.count()
        == BillingResource.objects.count()
        == Outbox.objects.count()
        == 0
    )
    monkeypatch.setattr(ORMDriver, "dispatch", original)
    assert deliver(client, "subscription.started", obj).status_code == 200
    assert WebhookCall.objects.count() == 1
    assert Outbox.objects.count() == 2


def test_purchase_key_survives_network_failure_and_is_bound_to_payload(user, mock_api, settings):
    billing = Billing()
    key = uuid4()
    calls, responses = mock_api
    responses.append(httpx.ConnectError("offline"))
    with pytest.raises(VatlyConnectionError):
        billing.checkout(user, "book", idempotency_key=key)
    assert CheckoutAttempt.objects.get().key == key
    assert Checkout.objects.count() == 0
    responses.append(resource("Checkout", id="checkout_retried"))
    assert billing.checkout(user, "book", idempotency_key=key).startswith("https://")
    assert Checkout.objects.get().entity_id == str(user.pk)
    assert calls[0].headers["Idempotency-Key"] == calls[1].headers["Idempotency-Key"] == str(key)
    assert CheckoutAttempt.objects.get().checkout_id == "checkout_retried"
    settings.VATLY_CHECKOUTS = {"book": {"products": [{"id": "other", "quantity": 2}]}}
    with pytest.raises(FluentError, match="different purchase"):
        billing.checkout(user, "book", idempotency_key=key)
    assert len(calls) == 2


def test_views_authorize_csrf_and_ignore_user_product_overrides(client, user, mock_api):
    assert client.post("/checkout/book/").status_code == 302
    client.force_login(user)
    assert client.get("/checkout/book/").status_code == 405
    assert client.post("/checkout/book/", {"idempotency_key": "nope"}).status_code == 400
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(user)
    assert csrf.post("/checkout/book/", {"idempotency_key": uuid4()}).status_code == 403
    calls, responses = mock_api
    responses.append(resource("Checkout"))
    assert (
        client.post(
            "/checkout/book/",
            {"idempotency_key": uuid4(), "products": "malicious", "customerId": "victim"},
        ).status_code
        == 302
    )
    body = json.loads(calls[-1].content)
    assert body["products"] == [{"id": "one_off_product_test", "quantity": 1}]
    assert "customerId" not in body


def test_bindings_portal_and_cross_scope_ownership(user, mock_api, client):
    billing = Billing()
    billing.bind_customer(user, "customer_authorized")
    billing.bind_customer(user, "customer_authorized")
    with pytest.raises(FluentError):
        billing.bind_customer(user, "customer_other")
    other = Billing("other/storefront")
    other.bind_customer(user, "customer_other")
    calls, responses = mock_api
    responses.append({"url": "https://portal.test/one-use", "expiresAt": "2026-01-01T01:00:00Z"})
    assert billing.portal(user).startswith("https://")
    assert "/customer_authorized/" in str(calls[-1].url)
    assert json.loads(calls[-1].content) == {"returnUrl": "https://app.test/billing"}
    raw, sig = signed("subscription.started", resource("Subscription"))
    billing.webhook(raw, sig)
    with pytest.raises(PermissionDenied):
        billing.subscription_action(user, resource("Subscription")["id"], "resume")


def test_subscribed_checks_status_and_exact_grace_boundary(user, mock_api, client, monkeypatch):
    # Exercise mixin on a concrete model without a bespoke test schema.
    class BillableUser(BillableMixin, get_user_model()):
        class Meta:
            proxy = True
            app_label = "auth"

    billable = BillableUser.objects.get(pk=user.pk)
    billing = Billing()
    subscription = Subscription.model_validate(resource("Subscription", status="paused"))
    async_to_sync(billing.driver.subscriptions.store)(
        LocalSubscription(resource=subscription, entity=entity_for(billable))
    )
    assert not billable.subscribed()
    now = timezone.now()
    expiry = now + timedelta(days=30)
    grace = resource(
        "Subscription",
        status="on_grace_period",
        canceledAt=(now - timedelta(seconds=5)).isoformat(),
        endedAt=None,
        renewedUntil=None,
        nextRenewalAt=expiry.isoformat(),
    )
    assert deliver(client, "subscription.canceled_with_grace_period", grace).status_code == 200
    assert BillingResource.objects.get().ends_at == expiry
    assert billable.subscribed()
    monkeypatch.setattr(timezone, "now", lambda: expiry)
    assert not billable.subscribed()


def test_explicit_reconciliation_distinguishes_initial_ids_and_legacy_plans(user, mock_api):
    billing = Billing()
    async_to_sync(billing.driver.checkouts.record)(
        CheckoutRecord("checkout_owned", entity_for(user), True)
    )
    order = resource("Order", id="order_owned")
    legacy = deepcopy(order["lines"][0])
    legacy.update(productType="subscription_plan", productId="plan_legacy")
    order["lines"][0].update(productType="subscription", productId="subscription_new", quantity=3)
    order["lines"].append(legacy)
    expiry = timezone.now() + timedelta(days=30)
    subscription = resource(
        "Subscription",
        id="subscription_new",
        status="on_grace_period",
        canceledAt=(timezone.now() - timedelta(seconds=5)).isoformat(),
        endedAt=None,
        renewedUntil=expiry.isoformat(),
        nextRenewalAt=None,
    )
    calls, responses = mock_api
    responses.extend(
        [
            resource("Checkout", id="checkout_owned", orderId="order_owned"),
            order,
            subscription,
        ]
    )
    result = billing.reconcile(user, "checkout_owned")
    assert result.legacy_plan_ids == ("plan_legacy",)
    assert [sub.id for sub in result.subscriptions] == ["subscription_new"]
    assert billing.resources(user).count() == 2
    assert billing.resources(user, "subscription").get().ends_at == expiry
    assert len(calls) == 3
    outsider = get_user_model().objects.create(username="outsider")
    with pytest.raises(PermissionDenied):
        billing.reconcile(outsider, "checkout_owned")


def test_postgres_concurrent_duplicate_delivery_commits_once(mock_api):
    if connection.vendor != "postgresql":
        pytest.skip("Concurrent database worker contract runs in PostgreSQL CI job")
    Billing()  # Provision scope before concurrent transactions.
    raw, sig = signed("subscription.started", resource("Subscription"))

    def send(_):
        close_old_connections()
        try:
            return Billing().webhook(raw, sig)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(send, range(4))) == [False, False, False, True]
    assert WebhookCall.objects.count() == BillingResource.objects.count() == 1
    assert Outbox.objects.count() == 2


def test_subscription_mutations_wait_for_signed_cancel_and_resume_refreshes(user, client, mock_api):
    billing = Billing()
    sub = resource("Subscription", id="subscription_owned")
    async_to_sync(billing.driver.subscriptions.store)(
        LocalSubscription(resource=Subscription.model_validate(sub), entity=entity_for(user))
    )
    calls, responses = mock_api
    responses.append(httpx.Response(204))
    billing.subscription_action(user, sub["id"], "cancel", immediately=False)
    assert BillingResource.objects.get().ends_at is None
    assert (
        deliver(
            client,
            "subscription.canceled_with_grace_period",
            {
                **sub,
                "canceledAt": "2026-11-09T21:19:57Z",
                "nextRenewalAt": "2027-01-01T00:00:00Z",
                "status": "on_grace_period",
            },
        ).status_code
        == 200
    )
    assert BillingResource.objects.get().ends_at is not None
    responses.append(sub)
    billing.subscription_action(user, sub["id"], "resume")
    row = BillingResource.objects.get()
    assert row.ends_at is None
    assert row.snapshot["status"] == sub["status"]
    assert calls[0].method == "DELETE"
    assert calls[1].method == "POST"


def test_admin_is_registered_and_read_only(user, rf):
    from django.contrib import admin

    user.is_staff = user.is_superuser = True
    request = rf.get("/admin/")
    request.user = user
    model_admin = admin.site._registry[BillingResource]
    assert model_admin.has_view_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


def test_checkout_and_portal_report_upstream_errors_without_persisting_checkout(
    client, user, mock_api
):
    client.force_login(user)
    calls, responses = mock_api
    responses.append(httpx.Response(503, json={"message": "maintenance"}))
    response = client.post("/checkout/book/", {"idempotency_key": uuid4()})
    assert response.status_code == 502
    assert b"same purchase key" in response.content
    assert Checkout.objects.count() == 0
    assert client.post("/portal/").status_code == 400
    Billing().bind_customer(user, "customer_a")
    responses.append(httpx.Response(503, json={"message": "maintenance"}))
    assert client.post("/portal/").status_code == 502
    assert len(calls) == 2


def test_admin_cannot_modify_any_billing_table(user, rf):
    from django.apps import apps
    from django.contrib import admin

    user.is_staff = user.is_superuser = True
    request = rf.post("/admin/")
    request.user = user
    for model in apps.get_app_config("vatly_django").get_models():
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert not model_admin.has_add_permission(request)
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)


def test_migrations_rebuild_schema_from_zero():
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes("vatly_django")
    executor.migrate([("vatly_django", None)])
    assert "vatly_django_checkout" not in connection.introspection.table_names()
    executor = MigrationExecutor(connection)
    executor.migrate(leaves)
    assert "vatly_django_checkout" in connection.introspection.table_names()
    assert Checkout.objects.count() == 0


def test_orm_rejects_resource_identity_and_mode_changes(user):
    from vatly_fluent import EntityRef

    driver = Billing().driver
    record = LocalSubscription(
        resource=Subscription.model_validate(resource("Subscription", id="subscription_a")),
        entity=entity_for(user),
    )
    async_to_sync(driver.subscriptions.store)(record)
    for changes, message in [
        ({"entity": EntityRef("auth.user", "outsider")}, "ownership"),
        ({"resource": record.resource.model_copy(update={"id": "subscription_b"})}, "immutable"),
        ({"resource": record.resource.model_copy(update={"testmode": False})}, "mode"),
    ]:
        with pytest.raises(FluentError, match=message):
            async_to_sync(driver.subscriptions.update)(record.resource.id, changes)
    saved = async_to_sync(driver.subscriptions.find_by_vatly_id)(record.resource.id)
    assert saved == record
