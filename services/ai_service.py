from __future__ import annotations

import logging
from typing import Any

import requests


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

    def get_answer(self, message: str, system_message: str | None = None) -> str:
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
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise RuntimeError("Empty response from OpenAI") from exc

    def chat_with_context(self, messages: list[dict[str, str]]) -> str:
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

            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logging.warning("OpenAI API error: %s", exc)
            return "Сейчас мне сложно поддержать диалог, попробуй чуть позже."
