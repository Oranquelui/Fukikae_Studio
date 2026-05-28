import json
import uuid
from typing import Callable, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fukikae_studio.ai.provider_guard import ensure_xai_provider
from fukikae_studio.config import XAIConfig
from fukikae_studio.logging_redaction import redact_secrets

Transport = Callable[[Request], Tuple[int, bytes]]


class XAIClientError(RuntimeError):
    """Raised for xAI client boundary errors."""


class XAIClient:
    """Small stdlib-only HTTP boundary for approved xAI endpoints.

    Tests inject a transport so no live API call is required by default.
    """

    def __init__(
        self,
        config: XAIConfig,
        provider: str = "xai",
        transport: Optional[Transport] = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.config = config
        self.provider = ensure_xai_provider(provider)
        self.timeout_seconds = timeout_seconds
        self._transport = transport or (
            lambda request: self._urllib_transport(request, timeout_seconds=self.timeout_seconds)
        )

    def build_json_request(self, path: str, payload: Mapping[str, object]) -> Request:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return Request(
            self._url(path),
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    def post_json(self, path: str, payload: Mapping[str, object]) -> object:
        request = self.build_json_request(path, payload)
        status, body = self._transport(request)
        if status >= 400:
            raise XAIClientError(self._error_message(status, body))
        return json.loads(body.decode("utf-8"))

    def post_json_bytes(self, path: str, payload: Mapping[str, object]) -> bytes:
        request = self.build_json_request(path, payload)
        status, body = self._transport(request)
        if status >= 400:
            raise XAIClientError(self._error_message(status, body))
        return body

    def build_multipart_request(
        self,
        path: str,
        fields: Mapping[str, object],
        files: Mapping[str, Tuple[str, bytes, str]],
        boundary: Optional[str] = None,
    ) -> Request:
        boundary = boundary or f"fukikae-{uuid.uuid4().hex}"
        body = self._encode_multipart(fields=fields, files=files, boundary=boundary)
        return Request(
            self._url(path),
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

    def post_multipart(
        self,
        path: str,
        fields: Mapping[str, object],
        files: Mapping[str, Tuple[str, bytes, str]],
    ) -> object:
        request = self.build_multipart_request(path, fields=fields, files=files)
        status, body = self._transport(request)
        if status >= 400:
            raise XAIClientError(self._error_message(status, body))
        return json.loads(body.decode("utf-8"))

    def _url(self, path: str) -> str:
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{self.config.base_url}{suffix}"

    @staticmethod
    def _encode_multipart(
        fields: Mapping[str, object],
        files: Mapping[str, Tuple[str, bytes, str]],
        boundary: str,
    ) -> bytes:
        chunks = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, (filename, content, content_type) in files.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="{name}"; '
                        f'filename="{filename}"\r\n'
                    ).encode("utf-8"),
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                    content,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(chunks)

    def _error_message(self, status: int, body: bytes) -> str:
        detail = body.decode("utf-8", errors="replace").strip()
        if detail:
            return f"xAI request failed with HTTP {status}: {redact_secrets(detail, secrets=[self.config.api_key])}"
        return f"xAI request failed with HTTP {status}"

    @staticmethod
    def _urllib_transport(
        request: Request,
        opener=urlopen,
        timeout_seconds: float = 120.0,
        max_attempts: int = 3,
    ) -> Tuple[int, bytes]:
        attempts = max(1, int(max_attempts))
        last_error: Optional[URLError] = None
        for _attempt in range(attempts):
            try:
                response_context = opener(request, timeout=timeout_seconds)
            except HTTPError as exc:
                return exc.code, exc.read()
            except URLError as exc:
                last_error = exc
                continue
            with response_context as response:
                return response.status, response.read()
        if last_error is not None:
            raise last_error
        raise XAIClientError("xAI request failed before receiving a response")
