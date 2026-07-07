from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import models


class ConnectionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DISCONNECTED = "disconnected", "Disconnected"
    REVOKED = "revoked", "Revoked"


class WhoopConnection(models.Model):
    """Per-user OAuth state for the WHOOP API.

    Health records persist through django-healthdatamodel; this model only
    holds the credentials needed to fetch them. WHOOP rotates the refresh
    token on every refresh (and invalidates the old access token), so both
    tokens are rewritten together.
    """

    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whoop_connection",
    )
    # WHOOP's numeric user id (int64), as carried by webhook payloads —
    # stored as text for parity with the sibling integrations.
    whoop_user_id = models.CharField(max_length=128, db_index=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_expires_at = models.DateTimeField()
    scopes = models.JSONField(default=list)
    status = models.CharField(
        max_length=32,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.ACTIVE,
    )
    connected_at = models.DateTimeField(auto_now_add=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "WHOOP connection"
        verbose_name_plural = "WHOOP connections"

    def __str__(self) -> str:
        return f"WhoopConnection(customer={self.customer_id}, status={self.status})"

    def is_token_expired(
        self, *, leeway_seconds: int = 60, now: datetime | None = None
    ) -> bool:
        """True if the access token is at or past ``token_expires_at - leeway``.

        The leeway buys time for an in-flight request to complete with the
        same token; WHOOP access tokens live about an hour.
        """
        anchor = now or datetime.now(timezone.utc)
        return anchor >= self.token_expires_at - timedelta(seconds=leeway_seconds)
