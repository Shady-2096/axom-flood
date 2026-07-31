"""HTTP client for the public ASDMA DRIMS flood-report form."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

DOWNLOAD_URL = "https://sdrf.assam.gov.in/dfr/download"
SOURCE_PAGE_URL = f"{DOWNLOAD_URL}?type=flood"
USER_AGENT = "AxomFloodData/0.1 (+public-interest flood data pipeline)"
_TOKEN_RE = re.compile(r'name="_token"\s+value="([^"]+)"')
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


class BulletinNotFound(LookupError):
    """The source is healthy, but no bulletin exists for the requested date."""


class BulletinSourceError(RuntimeError):
    """The source response is unavailable or violates the expected contract."""


@dataclass(frozen=True)
class DownloadedBulletin:
    requested_date: date
    fetched_at: datetime
    source_url: str
    content: bytes
    content_type: str


def fetch_bulletin(
    report_date: date,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = 180.0,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> DownloadedBulletin:
    """Download one public flood bulletin using the DRIMS session and CSRF flow.

    Each retry repeats both the form GET and PDF POST so a fresh CSRF token is
    used. Only transport failures and explicitly transient HTTP statuses are
    retried; an unpublished date or a source-contract violation fails
    immediately.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if retry_backoff_seconds < 0:
        raise ValueError("retry_backoff_seconds cannot be negative")

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": USER_AGENT},
        )

    try:
        for attempt in range(1, max_attempts + 1):
            stage = "form GET"
            try:
                logger.info(
                    "ASDMA attempt %d/%d: %s started (timeout %.0fs)",
                    attempt,
                    max_attempts,
                    stage,
                    timeout_seconds,
                )
                stage_started = time.monotonic()
                form_response = client.get(SOURCE_PAGE_URL, timeout=timeout_seconds)
                logger.info(
                    "ASDMA attempt %d/%d: %s completed with HTTP %d in %.2fs",
                    attempt,
                    max_attempts,
                    stage,
                    form_response.status_code,
                    time.monotonic() - stage_started,
                )
                form_response.raise_for_status()
                token_match = _TOKEN_RE.search(form_response.text)
                if token_match is None:
                    raise BulletinSourceError(
                        "ASDMA download form did not contain a CSRF token"
                    )

                stage = "PDF POST"
                logger.info(
                    "ASDMA attempt %d/%d: %s started for %s (timeout %.0fs)",
                    attempt,
                    max_attempts,
                    stage,
                    report_date.isoformat(),
                    timeout_seconds,
                )
                stage_started = time.monotonic()
                response = client.post(
                    DOWNLOAD_URL,
                    data={
                        "_token": token_match.group(1),
                        "type": "flood",
                        "date": report_date.isoformat(),
                    },
                    timeout=timeout_seconds,
                )
                logger.info(
                    "ASDMA attempt %d/%d: %s completed with HTTP %d and %d bytes in %.2fs",
                    attempt,
                    max_attempts,
                    stage,
                    response.status_code,
                    len(response.content),
                    time.monotonic() - stage_started,
                )
                response.raise_for_status()
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].lower()
                )

                if response.content.startswith(b"%PDF"):
                    return DownloadedBulletin(
                        requested_date=report_date,
                        fetched_at=datetime.now(ZoneInfo("Asia/Kolkata")),
                        source_url=str(response.url),
                        content=response.content,
                        content_type=content_type or "application/pdf",
                    )

                if "PDF Not Found" in response.text:
                    raise BulletinNotFound(
                        f"no ASDMA flood bulletin for {report_date.isoformat()}"
                    )

                raise BulletinSourceError(
                    f"ASDMA returned non-PDF content ({content_type or 'unknown content type'})"
                )
            except BulletinNotFound:
                raise
            except BulletinSourceError:
                raise
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code in _RETRYABLE_STATUS_CODES
                if not retryable or attempt == max_attempts:
                    raise BulletinSourceError(
                        f"ASDMA {stage} failed after {attempt} attempt(s): {exc}"
                    ) from exc
                _log_retry(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    stage=stage,
                    exc=exc,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
            except httpx.RequestError as exc:
                if attempt == max_attempts:
                    raise BulletinSourceError(
                        f"ASDMA {stage} failed after {attempt} attempt(s): {exc}"
                    ) from exc
                _log_retry(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    stage=stage,
                    exc=exc,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
        raise AssertionError("ASDMA retry loop exited unexpectedly")
    finally:
        if owns_client:
            client.close()


def _log_retry(
    *,
    attempt: int,
    max_attempts: int,
    stage: str,
    exc: httpx.HTTPError,
    retry_backoff_seconds: float,
) -> None:
    delay = retry_backoff_seconds * (2 ** (attempt - 1))
    logger.warning(
        "ASDMA attempt %d/%d: %s failed with %s; retrying full flow in %.1fs",
        attempt,
        max_attempts,
        stage,
        type(exc).__name__,
        delay,
    )
    if delay:
        time.sleep(delay)
