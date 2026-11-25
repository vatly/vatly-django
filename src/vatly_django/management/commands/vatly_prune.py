"""Delete old webhook calls and delivered outbox rows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from vatly_django.models import Outbox, WebhookCall
from vatly_django.storage import envelope_ids

DEFAULT_RETENTION_DAYS = 30


class Command(BaseCommand):
    help = (
        "Delete webhook calls processed and outbox rows delivered more than "
        "VATLY_RETENTION_DAYS (default 30) days ago, and reduce the envelopes of "
        "remaining webhook calls to their event ids."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--days", type=int, default=None)

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]
        if days is None:
            days = int(getattr(settings, "VATLY_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
        if days < 1:
            self.stdout.write("Retention is off; nothing deleted.")
            return
        cutoff = timezone.now() - timedelta(days=days)
        calls, _ = WebhookCall.objects.filter(processed_at__lt=cutoff).delete()
        outbox, _ = Outbox.objects.filter(delivered_at__lt=cutoff).delete()
        redacted = 0
        for call in WebhookCall.objects.filter(envelope__has_key="object").iterator():
            call.envelope = envelope_ids(call.envelope)
            call.save(update_fields=["envelope"])
            redacted += 1
        self.stdout.write(
            f"Deleted {calls} webhook calls and {outbox} delivered outbox rows; "
            f"reduced {redacted} envelopes to event ids."
        )
