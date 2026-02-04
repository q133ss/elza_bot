from __future__ import annotations

from datetime import datetime
import logging
import time
from pathlib import Path

from services import AIService, ChatService, TgService, PaymentService
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


def _send_due_reminders(storage: Storage, tg: TgService, chat: ChatService) -> None:
    now = datetime.now()
    for reminder in storage.get_due_reminders(now):
        if reminder.message.startswith(ChatService.PAYMENT_REMINDER_PREFIX):
            parts = reminder.message.split("|", 2)
            if len(parts) >= 2:
                payment_id = parts[1]
                if payment_id:
                    chat.handle_scheduled_payment_check(reminder.chat_id, payment_id)
            storage.mark_reminder_sent(reminder.id)
            continue

        if reminder.message in ChatService.RETENTION_MESSAGES:
            user = storage.get_or_create_user(reminder.chat_id)
            if user.subscription == "paid" or user.retention_message_sent_at:
                storage.mark_reminder_sent(reminder.id)
                continue

        tg.send_message(reminder.chat_id, reminder.message)
        storage.log_chat_message(
            reminder.chat_id,
            "assistant",
            reminder.message,
            meta={"source": "reminder", "reminder_id": reminder.id},
        )
        if reminder.message in ChatService.RETENTION_MESSAGES:
            user = storage.get_or_create_user(reminder.chat_id)
            user.retention_message_sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            storage.save_user(user)
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
    payments = PaymentService(
        shop_id=settings.yookassa_shop_id,
        secret_key=settings.yookassa_secret_key,
        return_url=settings.yookassa_return_url,
    )
    chat = ChatService(tg=tg, ai=ai, storage=storage, payments=payments)

    offset = _load_offset(settings.offset_file)

    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=settings.polling_timeout)
            for update in updates:
                offset = update.get("update_id", offset) + 1
                chat.handle_update(update)
            _save_offset(settings.offset_file, offset)
            _send_due_reminders(storage, tg, chat)
        except Exception as exc:
            logging.exception("Polling error: %s", exc)
            time.sleep(2)

        time.sleep(settings.polling_sleep)


if __name__ == "__main__":
    main()
