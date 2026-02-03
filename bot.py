from __future__ import annotations

from datetime import datetime
import logging
import time
from pathlib import Path

from services import AIService, ChatService, TgService
from settings import load_settings
from storage import Storage


def _load_offset(path: str | None) -> int:
    if not path:
        return 0
    file_path = Path(path)
    if not file_path.exists():
        return 0
    try:
        return int(file_path.read_text(encoding="utf-8").strip() or 0)
    except (ValueError, OSError):
        return 0


def _save_offset(path: str | None, offset: int) -> None:
    if not path:
        return
    Path(path).write_text(str(offset), encoding="utf-8")


def _send_due_reminders(storage: Storage, tg: TgService) -> None:
    now = datetime.now()
    for reminder in storage.get_due_reminders(now):
        tg.send_message(reminder.chat_id, reminder.message)
        storage.mark_reminder_sent(reminder.id)


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")

    storage = Storage(settings.db_path)
    ai = AIService(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        max_tokens=settings.openai_max_tokens,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout,
    )
    tg = TgService(settings.telegram_token, timeout=settings.telegram_timeout)
    chat = ChatService(tg=tg, ai=ai, storage=storage)

    offset = _load_offset(settings.offset_file)

    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=settings.polling_timeout)
            for update in updates:
                offset = update.get("update_id", offset) + 1
                chat.handle_update(update)
            _save_offset(settings.offset_file, offset)
            _send_due_reminders(storage, tg)
        except Exception as exc:
            logging.exception("Polling error: %s", exc)
            time.sleep(2)

        time.sleep(settings.polling_sleep)


if __name__ == "__main__":
    main()
