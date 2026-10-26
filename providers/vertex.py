"""Vertex Gemini adapter using the current Google Gen AI SDK.

Verified against official Google documentation on 2026-10-26: explicit Vertex
client, API v1, configurable model, and local image bytes via Part.from_bytes.
Live model availability/authentication remains unverified until a request runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import suppress
from typing import Protocol, Sequence

from config import Config


class ProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ImagePayload:
    data: bytes
    media_type: str
    role: str
    image_id: str


class VisionTextProvider(Protocol):
    def generate(self, *, system_instruction: str, prompt: str,
                 images: Sequence[ImagePayload] = ()) -> str: ...


class VertexGeminiProvider:
    def __init__(self, config: Config, client=None):
        self.config = config
        self._client = client
        self.last_usage = None

    def _new_client(self, genai, types):
        return genai.Client(vertexai=True, project=self.config.google_project,
            location=self.config.google_location,
            http_options=types.HttpOptions(api_version="v1", timeout=self.config.worker_timeout_seconds * 1000,
                                          retry_options=types.HttpRetryOptions(attempts=1)))

    def availability_issues(self) -> list[str]:
        issues = []
        if not self.config.google_project:
            issues.append("GOOGLE_CLOUD_PROJECT is not configured")
        if not self.config.google_location:
            issues.append("GOOGLE_CLOUD_LOCATION is not configured")
        if not self.config.gemini_model_id:
            issues.append("GEMINI_MODEL_ID is not configured")
        return issues

    def _contents(self, prompt: str, images: Sequence[ImagePayload]):
        try:
            from google.genai import types
        except ImportError as error:
            raise ProviderUnavailable("google-genai is not installed") from error
        parts = [types.Part.from_text(text=prompt)]
        for image in images:
            if image.media_type not in ("image/png", "image/jpeg", "image/webp") or not image.data:
                raise ValueError("Images require nonempty PNG, JPEG, or WebP bytes")
            parts.append(types.Part.from_text(text=f"Image {image.image_id} role: {image.role}"))
            parts.append(types.Part.from_bytes(data=image.data, mime_type=image.media_type))
        return parts

    def generate(self, *, system_instruction: str, prompt: str,
                 images: Sequence[ImagePayload] = ()) -> str:
        issues = self.availability_issues()
        if issues:
            raise ProviderUnavailable("; ".join(issues))
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise ProviderUnavailable("google-genai is not installed") from error
        client = self._client
        try:
            self.last_usage = None
            client = self._client or self._new_client(genai, types)
            response = client.models.generate_content(
                model=self.config.gemini_model_id,
                contents=self._contents(prompt, images),
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction, temperature=0.2,
                    response_mime_type="application/json"),
            )
        except Exception:
            # SDK exceptions may include request URLs/headers, credentials or input.
            # Do not chain, persist, or display those exceptions.
            raise ProviderUnavailable("Gemini request failed; check local credentials, model access and quota. No automatic retry was made.") from None
        finally:
            if self._client is None and client is not None:
                with suppress(Exception):
                    client.close()
        usage = getattr(response, "usage_metadata", None)
        self.last_usage = {name: getattr(usage, name, None) for name in (
            "prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count")}
        if not response.text:
            raise ProviderUnavailable("Gemini returned no text")
        return response.text
