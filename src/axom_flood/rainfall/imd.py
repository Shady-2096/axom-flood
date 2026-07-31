"""Disabled-by-default IMD rainfall access with explicit 401 handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .provenance import SourceRevision, require_aware

IMD_STATE_RAINFALL_URL = "https://mausam.imd.gov.in/api/statewise_rainfall_api.php"
IMD_API_DOCUMENTATION_URL = "https://mausam.imd.gov.in/imd_latest/contents/api.pdf"


class SourceDisabledError(RuntimeError):
    """A live source has not been enabled with owner-provided access."""


class ImdAccessRestrictedError(RuntimeError):
    """IMD rejected the host because its source IP is not authorised."""

    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code
        self.reason = "ip_whitelist_required"
        super().__init__(
            "IMD rainfall API returned HTTP 401; operator IP whitelisting is required"
        )


@dataclass(frozen=True, slots=True)
class ImdDownload:
    content: bytes
    revision: SourceRevision


class ImdClient:
    """Narrow client that cannot make a live request unless explicitly enabled."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        timeout: float = 30,
        transport: httpx.BaseTransport | None = None,
        base_url: str = IMD_STATE_RAINFALL_URL,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def __enter__(self) -> ImdClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch_state_rainfall(
        self,
        *,
        state_id: str,
        fetched_at: datetime,
    ) -> ImdDownload:
        require_aware(fetched_at, "fetched_at")
        if not self.enabled:
            raise SourceDisabledError(
                "IMD live access is disabled until the operator confirms API permission"
            )
        response = self._client.get(self.base_url, params={"id": state_id})
        if response.status_code == 401:
            raise ImdAccessRestrictedError(status_code=401)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type not in {"application/json", "text/json"}:
            raise ValueError(
                f"IMD rainfall API returned {content_type or 'unknown content type'}, "
                "expected JSON"
            )
        return ImdDownload(
            content=response.content,
            revision=SourceRevision.capture(
                response.content,
                source_id="imd-statewise-rainfall",
                source_url=str(response.url),
                fetched_at=fetched_at,
                media_type=content_type,
            ),
        )

    def access_state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "access_mode": "ip_whitelist_required",
            "documentation_url": IMD_API_DOCUMENTATION_URL,
            "endpoint": self.base_url,
        }
