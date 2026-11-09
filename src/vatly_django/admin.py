from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    BillingResource,
    BillingScope,
    Checkout,
    CheckoutAttempt,
    CustomerBinding,
    Outbox,
    ResourceLink,
    WebhookCall,
)


class BillingReadOnlyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_filter = ["scope"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(BillingResource)
class ResourceAdmin(BillingReadOnlyAdmin):
    list_display = ["vatly_id", "resource_type", "entity_kind", "entity_id", "scope", "updated_at"]
    search_fields = ["vatly_id", "entity_id"]
    list_filter = ["scope", "resource_type"]


@admin.register(WebhookCall)
class WebhookAdmin(BillingReadOnlyAdmin):
    list_display = ["event_id", "event_name", "scope", "processed_at"]
    search_fields = ["event_id"]


@admin.register(Outbox)
class OutboxAdmin(BillingReadOnlyAdmin):
    list_display = ["id", "event_name", "scope", "created_at", "delivered_at"]


for model in (Checkout, CheckoutAttempt, CustomerBinding, ResourceLink):
    admin.site.register(model, BillingReadOnlyAdmin)


@admin.register(BillingScope)
class ScopeAdmin(BillingReadOnlyAdmin):
    list_display = ["name", "testmode"]
    list_filter = ["testmode"]
