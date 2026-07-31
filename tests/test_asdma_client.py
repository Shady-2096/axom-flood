import logging
from datetime import date

import httpx
import pytest

from axom_flood.asdma.client import BulletinNotFound, BulletinSourceError, fetch_bulletin


def test_fetch_bulletin_uses_session_form_and_returns_pdf() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                text='<input type="hidden" name="_token" value="csrf-value">',
                headers={"set-cookie": "session=abc"},
            )
        assert request.content == b"_token=csrf-value&type=flood&date=2026-07-25"
        return httpx.Response(
            200,
            content=b"%PDF-fixture",
            headers={"content-type": "application/pdf"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_bulletin(date(2026, 7, 25), client=client)

    assert result.content == b"%PDF-fixture"
    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[0].extensions["timeout"]["read"] == 180.0
    assert requests[1].extensions["timeout"]["read"] == 180.0


def test_fetch_bulletin_distinguishes_unpublished_date() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, text='<input type="hidden" name="_token" value="csrf-value">'
            )
        return httpx.Response(200, text="<script>PDF Not Found</script>")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(BulletinNotFound),
    ):
        fetch_bulletin(date(2026, 7, 26), client=client)


def test_fetch_bulletin_retries_the_full_flow_after_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        if request.method == "GET":
            return httpx.Response(
                200, text='<input type="hidden" name="_token" value="fresh-token">'
            )
        assert request.content == b"_token=fresh-token&type=flood&date=2026-07-25"
        return httpx.Response(200, content=b"%PDF-after-retry")

    caplog.set_level(logging.INFO, logger="axom_flood.asdma.client")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_bulletin(
            date(2026, 7, 25),
            client=client,
            max_attempts=2,
            retry_backoff_seconds=0,
        )

    assert result.content == b"%PDF-after-retry"
    assert [request.method for request in requests] == ["GET", "GET", "POST"]
    assert "form GET failed with ReadTimeout; retrying full flow" in caplog.text
    assert "PDF POST completed with HTTP 200" in caplog.text


def test_fetch_bulletin_retries_transient_http_status() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(503, text="busy")
        if request.method == "GET":
            return httpx.Response(
                200, text='<input type="hidden" name="_token" value="csrf-value">'
            )
        return httpx.Response(200, content=b"%PDF-fixture")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_bulletin(
            date(2026, 7, 25),
            client=client,
            max_attempts=2,
            retry_backoff_seconds=0,
        )

    assert result.content == b"%PDF-fixture"
    assert request_count == 3


def test_fetch_bulletin_does_not_retry_contract_failure() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, text="<html>unexpected form</html>")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(BulletinSourceError, match="did not contain a CSRF token"),
    ):
        fetch_bulletin(
            date(2026, 7, 25),
            client=client,
            max_attempts=3,
            retry_backoff_seconds=0,
        )

    assert request_count == 1
