"""Pydantic models for WHOOP OAuth request/response payloads."""

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, field_validator


class OAuthFlowState(BaseModel):
    """Per-request state stashed in the Django session between ``connect`` and
    ``callback``. ``state`` defends against CSRF (WHOOP requires it, minimum
    eight characters); the requested ``scopes`` ride along so the callback can
    persist what was actually asked for.
    """

    state: str
    scopes: list[str]


class WhoopTokens(BaseModel):
    """Token-endpoint response from ``api.prod.whoop.com/oauth/oauth2/token``.

    Mirrors the JSON WHOOP returns for both ``authorization_code`` and
    ``refresh_token`` grants. ``refresh_token`` is only present when the
    ``offline`` scope was granted; on refresh, WHOOP rotates it and
    invalidates the previous access token.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    access_token: str
    expires_in: int
    token_type: str = "bearer"
    scope: str = ""
    refresh_token: str | None = None

    @field_validator("scope", mode="before")
    @classmethod
    def _coerce_scope(cls, value: object) -> str:
        # WHOOP returns a space-separated string (e.g. "read:sleep offline");
        # accept a pre-parsed list too.
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        return str(value)

    @property
    def scopes(self) -> list[str]:
        return self.scope.split() if self.scope else []

    def expires_at(self, *, now: datetime | None = None) -> datetime:
        anchor = now or datetime.now(timezone.utc)
        return anchor + timedelta(seconds=self.expires_in)
