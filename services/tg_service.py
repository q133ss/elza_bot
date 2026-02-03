from __future__ import annotations

import json
import logging
from typing import Any

import requests


class TgService:
    def __init__(self, token: str, *, timeout: int = 20) -> None:
        self._token = token
        self._timeout = timeout
        self._base_url = f"https://api.telegram.org/bot{self._token}"

    def send_message(self, chat_id: int, text: str, keyboard: list[list[str]] | None = None) -> None:
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        if keyboard:
            data["reply_markup"] = json.dumps(
                {
                    "keyboard": keyboard,
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
                ensure_ascii=False,
            )

        self._post("sendMessage", data)

    def send_inline_keyboard(self, chat_id: int, text: str, buttons: list[list[dict[str, str]]]) -> None:
        inline = {"inline_keyboard": buttons}

        self._post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(inline, ensure_ascii=False),
            },
        )

    def get_updates(self, *, offset: int | None = None, timeout: int = 30, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset

        try:
            response = requests.get(
                f"{self._base_url}/getUpdates",
                params=params,
                timeout=timeout + 5,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                logging.warning("Telegram API error: %s", data)
                return []
            return data.get("result", [])
        except Exception as exc:
            logging.error("Telegram API error: %s", exc)
            return []

    def _post(self, method: str, data: dict[str, Any]) -> None:
        try:
            requests.post(
                f"{self._base_url}/{method}",
                data=data,
                timeout=self._timeout,
            )
        except Exception as exc:
            logging.error("Telegram API error: %s", exc, extra={"data": data})
