from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import requests


@dataclass(frozen=True)
class AIResponse:
    content: str
    usage: dict[str, int] | None
    model: str | None


class AIService:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1200,
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def get_answer(self, message: str, system_message: str | None = None) -> AIResponse:
        messages: list[dict[str, Any]] = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": message})

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )

            if response.status_code >= 400:
                logging.warning(
                    "OpenAI API failed",
                    extra={"status": response.status_code, "body": response.text},
                )
                raise RuntimeError("OpenAI API request failed")

            data = response.json()
        except Exception as exc:
            logging.warning("OpenAI API error: %s", exc)
            raise

        logging.info("OpenAI response: %s", data)

        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise RuntimeError("Empty response from OpenAI") from exc

        return AIResponse(
            content=content,
            usage=self._extract_usage(data),
            model=data.get("model") or self._model,
        )

    def chat_with_context(self, messages: list[dict[str, str]]) -> AIResponse:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )

            data = response.json()

            logging.info("OpenAI response: %s", data)

            content = data["choices"][0]["message"]["content"].strip()
            return AIResponse(
                content=content,
                usage=self._extract_usage(data),
                model=data.get("model") or self._model,
            )
        except Exception as exc:
            logging.warning("OpenAI API error: %s", exc)
            return AIResponse(
                content="Сейчас мне сложно поддержать диалог, попробуй чуть позже.",
                usage=None,
                model=self._model,
            )

    @staticmethod
    def _extract_usage(data: dict[str, Any]) -> dict[str, int] | None:
        usage_raw = data.get("usage")
        if not isinstance(usage_raw, dict):
            return None
        usage: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage_raw.get(key)
            if isinstance(value, (int, float)):
                usage[key] = int(value)
        return usage or None
