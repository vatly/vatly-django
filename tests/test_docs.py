"""Run Python snippets and render/submit the documented Django forms."""

import inspect
import re
import types
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from asgiref.sync import async_to_sync
from django.template import RequestContext, Template
from django.test import Client
from django.urls import include, path, resolve
from vatly.models import Subscription
from vatly_fluent import CheckoutRecord, LocalSubscription

from tests.test_billing import resource, signed
from vatly_django.billing import Billing, entity_for
from vatly_django.models import Checkout, WebhookCall

pytestmark = pytest.mark.django_db(transaction=True)
DOCS = Path(__file__).parents[1] / "docs"
CASES = [
    pytest.param(page, index, language, code, id=f"{page.stem}-{index}")
    for page in sorted(DOCS.glob("*.md"))
    for index, (language, code) in enumerate(
        re.findall(r"```(python|html)\n(.*?)```", page.read_text(), re.S)
    )
]


@pytest.mark.parametrize("page,index,language,code", CASES)
def test_documented_examples(
    page, index, language, code, monkeypatch, settings, django_user_model, rf
):
    billable = django_user_model.objects.create_user(username="docs", email="buyer@example.com")
    urlconf = types.ModuleType("docs_urls")
    urlconf.urlpatterns = [path("billing/", include("vatly_django.urls"))]
    settings.ROOT_URLCONF = urlconf
    monkeypatch.setenv("VATLY_API_KEY", "test_" + "x" * 20)
    monkeypatch.setenv("VATLY_WEBHOOK_SECRET", "test-signing-secret")
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.host == "api.vatly.com"
        parts = request.url.path.removeprefix("/v1/").split("/")
        if parts[-1] == "portal-sessions":
            return httpx.Response(
                200,
                json={
                    "url": "https://portal.example.com/session",
                    "expiresAt": "2027-01-01T00:00:00Z",
                },
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        name = {"checkouts": "Checkout", "orders": "Order", "subscriptions": "Subscription"}[
            parts[0]
        ]
        value = resource(
            name,
            id={
                "Checkout": "checkout_example",
                "Order": "order_example",
                "Subscription": "subscription_example",
            }[name],
        )
        if name == "Checkout":
            value["orderId"] = "order_example"
        if name == "Order":
            value["lines"][0].update(productType="subscription", productId="subscription_example")
        return httpx.Response(200, json=value)

    original = httpx.AsyncClient.__init__

    def initialize(self, *args, **kwargs):
        kwargs["transport"] = kwargs.get("transport") or httpx.MockTransport(respond)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", initialize)
    billing = Billing()
    async_to_sync(billing.driver.checkouts.record)(
        CheckoutRecord("checkout_example", entity_for(billable), True)
    )
    async_to_sync(billing.driver.subscriptions.store)(
        LocalSubscription(
            resource=Subscription.model_validate(
                resource("Subscription", id="subscription_example")
            ),
            entity=entity_for(billable),
        )
    )
    raw, signature = signed("future.event", {"id": "future_1"}, event_id="event_adapter_docs")
    request = rf.get("/billing/")
    request.user = billable
    purchase_key = str(uuid4())
    if language == "html":
        billing.bind_customer(billable, "customer_example")
        rendered = Template(code).render(RequestContext(request, {"purchase_key": purchase_key}))
        assert 'name="csrfmiddlewaretoken"' in rendered
        action = re.search(r'action="([^"]+)"', rendered)[1]
        client = Client()
        client.force_login(billable)
        response = client.post(action, {"idempotency_key": purchase_key})
        assert response.status_code == 302
        assert response.url.startswith("https://")
        assert calls
        return
    namespace = {"__name__": "docs_example", "INSTALLED_APPS": []}
    exec(compile(code, f"{page}:{index}", "exec"), namespace)
    if "example" in namespace:
        function = namespace["example"]
        available = {
            "billable": billable,
            "purchase_key": purchase_key,
            "request": request,
            "raw_body": raw,
            "signature": signature,
        }
        result = function(
            **{name: available[name] for name in inspect.signature(function).parameters}
        )
        if page.stem == "Checkout" and index == 2:
            assert result.startswith("https://")
            assert Checkout.objects.get(vatly_id="checkout_example").entity_id == str(billable.pk)
        if page.stem == "Testing" and index == 1:
            assert WebhookCall.objects.filter(event_id="event_docs").count() == 1
    elif "urlpatterns" in namespace:
        module = types.ModuleType("example_urls")
        module.urlpatterns = namespace["urlpatterns"]
        target = "/admin/" if page.stem == "Admin" else "/billing/webhook/"
        assert resolve(target, urlconf=module).func
    elif "Team" in namespace:
        assert namespace["Team"]._meta.get_field("name").max_length == 200
        assert hasattr(namespace["Team"], "checkout")
    elif page.stem == "Installation":
        assert namespace["INSTALLED_APPS"] == ["vatly_django"]
    else:
        assert namespace["VATLY_CHECKOUTS"]["book"]["products"][0]["quantity"] == 1


def test_overview_links_every_flat_page():
    overview = (DOCS / "README.md").read_text()
    assert not any(path.is_dir() for path in DOCS.iterdir())
    for page in DOCS.glob("*.md"):
        if page.name != "README.md":
            assert f"]({page.name})" in overview
