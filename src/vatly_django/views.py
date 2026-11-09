from __future__ import annotations

from typing import cast

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Model
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.utils.module_loading import import_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from vatly import VatlyError, VatlyInvalidSignatureError
from vatly_fluent import FluentError

from .billing import Billing


def billable_for(request: HttpRequest) -> Model:
    resolver = getattr(settings, "VATLY_BILLABLE_RESOLVER", None)
    # Custom resolvers MUST enforce membership/permission for team billing.
    return cast(Model, import_string(resolver)(request) if resolver else request.user)


def billing_for(request: HttpRequest) -> Billing:
    resolver = getattr(settings, "VATLY_SCOPE_RESOLVER", None)
    return Billing(import_string(resolver)(request) if resolver else None)


@login_required
@require_POST
def checkout(request: HttpRequest, offer: str) -> HttpResponse:
    try:
        url = billing_for(request).checkout(
            billable_for(request), offer, idempotency_key=request.POST.get("idempotency_key", "")
        )
    except (ValueError, FluentError):
        return HttpResponseBadRequest("Invalid offer or purchase key")
    except VatlyError:
        return HttpResponse(
            "Billing service unavailable; retry with the same purchase key", status=502
        )
    return HttpResponseRedirect(url)


@login_required
@require_POST
def portal(request: HttpRequest) -> HttpResponse:
    try:
        url = billing_for(request).portal(billable_for(request))
    except FluentError:
        return HttpResponseBadRequest("No customer binding")
    except VatlyError:
        return HttpResponse("Billing service unavailable", status=502)
    return HttpResponseRedirect(url)


@csrf_exempt
@require_POST
def webhook(request: HttpRequest) -> HttpResponse:
    try:
        processed = billing_for(request).webhook(
            request.body, request.headers.get("Vatly-Signature")
        )
    except (VatlyInvalidSignatureError, ValueError):
        return HttpResponseBadRequest("Invalid webhook")
    # Unexpected driver/reaction failures propagate as 500: rollback and let Vatly retry.
    return HttpResponse("processed" if processed else "duplicate")
