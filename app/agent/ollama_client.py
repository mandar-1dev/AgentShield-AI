"""Minimal Ollama HTTP client. Model output is untrusted."""

from __future__ import annotations

from typing import Optional

import httpx


class OllamaError(Exception):
    """Base exception for Ollama errors."""


class OllamaUnavailable(OllamaError):
    """Ollama is unavailable or rejects the request."""


class OllamaBadResponse(OllamaError):
    """Ollama returns an invalid response."""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.model = model
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )

    def health(self) -> dict:
        try:
            response = self._http.get("/api/tags")
            response.raise_for_status()

            models = response.json().get("models", [])

            names = [
                item.get("name", "")
                for item in models
                if isinstance(item, dict)
            ]

            available = any(
                name == self.model
                or name.split(":")[0] == self.model
                for name in names
            )

            return {
                "reachable": True,
                "model": self.model,
                "model_available": available,
                "error": None,
            }

        except Exception as exc:
            return {
                "reachable": False,
                "model": self.model,
                "model_available": False,
                "error": type(exc).__name__,
            }

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            response = self._http.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "stream": False,
                },
            )

        except httpx.HTTPError as exc:
            raise OllamaUnavailable(
                f"Cannot reach Ollama ({type(exc).__name__})"
            ) from exc

        if response.status_code == 404:
            raise OllamaUnavailable(
                f"Model '{self.model}' not found. "
                f"Run: ollama pull {self.model}"
            )

        if response.status_code != 200:
            detail = response.text.strip().replace("\r", " ").replace("\n", " ")

            raise OllamaUnavailable(
                f"Ollama returned HTTP {response.status_code}: "
                f"{detail[:300]}"
            )

        try:
            data = response.json()
            message = data.get("message")

        except Exception as exc:
            raise OllamaBadResponse(
                "Ollama returned invalid JSON"
            ) from exc

        if not isinstance(message, dict):
            raise OllamaBadResponse(
                "Ollama response has no 'message' object"
            )

        return message