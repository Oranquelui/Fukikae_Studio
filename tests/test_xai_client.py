import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from fukikae_studio.ai.provider_guard import ProviderPolicyError
from fukikae_studio.ai.xai_client import XAIClient
from fukikae_studio.ai.xai_client import XAIClientError
from fukikae_studio.config import DEFAULT_XAI_BASE_URL, XAIConfig


def make_config():
    return XAIConfig(api_key="unit-test-api-key")


def test_client_initialization_runs_provider_guard():
    with pytest.raises(ProviderPolicyError):
        XAIClient(make_config(), provider="not-xai")


def test_build_json_request_uses_xai_base_url_auth_and_json_body():
    client = XAIClient(make_config(), transport=lambda request: (_ for _ in ()).throw(AssertionError("no live calls")))

    request = client.build_json_request("/responses", {"model": "grok-4.3", "input": []})

    assert isinstance(request, Request)
    assert request.full_url == f"{DEFAULT_XAI_BASE_URL}/responses"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "Bearer unit-test-api-key"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {"model": "grok-4.3", "input": []}


def test_post_json_uses_injected_transport_and_parses_response_without_live_call():
    captured = []

    def fake_transport(request):
        captured.append(request)
        return 200, b'{"ok": true}'

    client = XAIClient(make_config(), transport=fake_transport)

    assert client.post_json("/responses", {"input": "hello"}) == {"ok": True}
    assert len(captured) == 1
    assert captured[0].full_url == f"{DEFAULT_XAI_BASE_URL}/responses"


def test_post_json_redacts_secret_from_error_body():
    def fake_transport(request):
        return 400, b'{"error":"bad unit-test-api-key request"}'

    client = XAIClient(make_config(), transport=fake_transport)

    with pytest.raises(XAIClientError) as exc_info:
        client.post_json("/responses", {"input": "hello"})

    message = str(exc_info.value)
    assert "HTTP 400" in message
    assert "unit-test-api-key" not in message
    assert "<redacted>" in message


def test_urllib_transport_returns_http_error_body_for_safe_reporting():
    request = Request(f"{DEFAULT_XAI_BASE_URL}/responses")
    error = HTTPError(
        request.full_url,
        400,
        "Bad Request",
        hdrs={},
        fp=BytesIO(b'{"error":"bad request"}'),
    )

    def raise_error(_request, timeout=None):
        raise error

    status, body = XAIClient._urllib_transport(request, opener=raise_error)

    assert status == 400
    assert body == b'{"error":"bad request"}'


def test_urllib_transport_passes_timeout_to_urlopen():
    request = Request(f"{DEFAULT_XAI_BASE_URL}/responses")
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_opener(_request, timeout):
        captured["timeout"] = timeout
        return FakeResponse()

    status, body = XAIClient._urllib_transport(request, opener=fake_opener, timeout_seconds=42.0)

    assert captured["timeout"] == 42.0
    assert status == 200
    assert body == b'{"ok": true}'


def test_urllib_transport_retries_transient_url_errors():
    request = Request(f"{DEFAULT_XAI_BASE_URL}/tts")
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"audio-bytes"

    def flaky_opener(_request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise URLError(ConnectionResetError(54, "Connection reset by peer"))
        return FakeResponse()

    status, body = XAIClient._urllib_transport(request, opener=flaky_opener, timeout_seconds=42.0)

    assert calls == [42.0, 42.0]
    assert status == 200
    assert body == b"audio-bytes"


def test_build_multipart_request_keeps_auth_in_header_not_body():
    client = XAIClient(make_config(), transport=lambda request: (200, b"{}"))

    request = client.build_multipart_request(
        "/stt",
        fields={"language": "en", "format": "true"},
        files={"file": ("audio.mp3", b"fake-audio", "audio/mpeg")},
        boundary="unit-test-boundary",
    )
    body = request.data

    assert request.full_url == f"{DEFAULT_XAI_BASE_URL}/stt"
    assert request.headers["Authorization"] == "Bearer unit-test-api-key"
    assert "multipart/form-data" in request.headers["Content-type"]
    assert b'name="language"' in body
    assert b"en" in body
    assert b'name="file"; filename="audio.mp3"' in body
    assert b"fake-audio" in body
    assert b"unit-test-api-key" not in body
