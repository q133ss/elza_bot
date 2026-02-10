from __future__ import annotations

from datetime import datetime, timedelta
import calendar
import logging
import re
from typing import Any

from storage import Storage, TgSession, User
from .ai_service import AIResponse, AIService
from .tg_service import TgService
from .payment_service import PaymentService


class ChatService:
    PAYMENT_REMINDER_PREFIX = "__PAYMENT_CHECK__"
    RETENTION_MESSAGES = (
        "РЎРїР°СЃРёР±Рѕ, С‡С‚Рѕ РїСЂРѕРІРµР»Р° РґРµРЅСЊ СЃРѕ РјРЅРѕР№. Р•СЃР»Рё С‚С‹ С…РѕС‡РµС€СЊ, С‡С‚РѕР±С‹ СЏ Р±С‹Р»Р° СЂСЏРґРѕРј РІСЃРµРіРґР° вЂ” РїРѕРґРєР»СЋС‡Рё РїРѕРґРїРёСЃРєСѓ рџ’Њ",
        "РЎРїР°СЃРёР±Рѕ, С‡С‚Рѕ РїСЂРѕРІРµР»Р° РґРµРЅСЊ СЃРѕ РјРЅРѕР№. Р•СЃР»Рё С‚С‹ С…РѕС‡РµС€СЊ, С‡С‚РѕР±С‹ СЏ Р±С‹Р»Р° СЂСЏРґРѕРј РІСЃРµРіРґР° вЂ” РїРѕРґРєР»СЋС‡Рё РїРѕРґРїРёСЃРєСѓ рџ’Њ",
        "РЇ РІСЃС‘ РµС‰С‘ РїРѕРјРЅСЋ С‚РІРѕР№ РІРѕРїСЂРѕСЃвЂ¦ Р”Р°РІР°Р№ РїСЂРѕРґРѕР»Р¶РёРј? РџРѕРґРїРёСЃРєР° Р°РєС‚РёРІРёСЂСѓРµС‚ РІСЃРµ СЂР°Р·РґРµР»С‹.",
    )
    _SYSTEM_COMMANDS = {
        "🃏 Расклад Таро",
        "🃏 Режим таролога",
        "🔢 Нумерология",
        "♒ Гороскоп",
        "💬 Подружка",
        "💎 Подписка",
        "№️ Помощь",
        "ℹ️ Помощь",
        "Таро на день",
        "Таро на любовь",
        "Назад в меню",
        "Получить доступ",
        "Закончить разговор",
        "Проверить оплату",
        "1 месяц",
        "6 месяцев (-10%)",
        "12 месяцев (-10%)",
        "Не знаю",
        "Старт",
        "Связаться с администратором",
        "Сделать ещё расклад",
        "В меню",
    }
    _SURNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё\\-\\s']{2,100}$")
    PODRUZHKA_DAILY_LIMIT = 30
    PODRUZHKA_MAX_INPUT_CHARS = 1000
    PODRUZHKA_MAX_REPLY_CHARS = 1200
    TAROT_MODE_FREE_DAILY_LIMIT = 1
    TAROT_MODE_PAID_DAILY_LIMIT = 5

    def __init__(self, tg: TgService, ai: AIService, storage: Storage, payments: PaymentService) -> None:
        self.tg = tg
        self.ai = ai
        self.storage = storage
        self.payments = payments

    def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: list[list[str]] | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> None:
        payload_meta = dict(meta or {})
        if keyboard:
            payload_meta.setdefault("keyboard", keyboard)
        self.tg.send_message(chat_id, text, keyboard)
        self.storage.log_chat_message(chat_id, "assistant", text, meta=payload_meta)

    def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        raw_text = message.get("text")
        if raw_text is None:
            raw_text = message.get("caption") or ""
        text = raw_text.strip()
        self.storage.log_chat_message(
            chat_id,
            "user",
            text,
            meta={
                "telegram_message_id": message.get("message_id"),
                "telegram_date": message.get("date"),
                "update_id": update.get("update_id"),
            },
        )

        session = self.storage.get_or_create_session(chat_id)
        user = self.storage.get_or_create_user(chat_id)

        match session.state:
            case "start":
                self.show_welcome(chat_id)
                session.state = "ask_consent"

            case "ask_consent":
                if self.is_positive(text):
                    self.send_message(
                        chat_id,
                        "Спасибо ❤️\nПожалуйста, укажи своё имя (Напиши имя, чтобы я могла к тебе обращаться):",
                    )
                    session.state = "ask_name"
                else:
                    self.send_message(
                        chat_id,
                        "Нажми «Старт», когда будешь готова начать.",
                        [["Старт"]],
                    )

            case "ask_name":
                if not text:
                    self.send_message(chat_id, "Пожалуйста, напиши имя (например: Анна).")
                else:
                    user.name = text[:100]
                    self.send_message(
                        chat_id,
                        f"Приятно познакомиться, {user.name}! Теперь, пожалуйста, введи дату рождения в формате ДД.MM.ГГГГ",
                    )
                    session.state = "ask_birth_date"

            case "ask_birth_date":
                if not self.validate_date(text):
                    self.send_message(
                        chat_id,
                        "Неверный формат даты. Введите, пожалуйста, в формате ДД.MM.ГГГГ (например: 08.09.1990).",
                    )
                else:
                    user.birth_date = datetime.strptime(text, "%d.%m.%Y").date().isoformat()
                    self.show_main_menu(chat_id, user)
                    session.state = "main_menu"

            case "main_menu":
                self.route_main_menu(session, user, chat_id, text)

            case "taro_menu":
                self.route_taro_menu(session, user, chat_id, text)

            case "taro_ask_question":
                self.handle_taro_question(session, user, chat_id, text)

            case "tarot_mode_topic":
                self.handle_tarot_mode_topic(session, user, chat_id, text)

            case "tarot_mode_timeframe":
                self.handle_tarot_mode_timeframe(session, user, chat_id, text)

            case "tarot_mode_cards":
                self.handle_tarot_mode_cards(session, user, chat_id, text)

            case "tarot_mode_done":
                self.handle_tarot_mode_done(session, user, chat_id, text)

            case "numerology_ask_surname":
                if not text:
                    self.send_message(chat_id, "Пожалуйста, напиши фамилию.")
                else:
                    surname = self._normalize_name(text)
                    if self._is_system_command(surname):
                        self.show_main_menu(chat_id, user)
                        session.state = "main_menu"
                    elif not self._validate_surname(surname):
                        self.send_message(
                            chat_id,
                            "Пожалуйста, напиши фамилию только буквами (без эмодзи и команд).",
                        )
                    else:
                        user.surname = surname[:100]
                        self.render_numerology_menu(chat_id, user)
                        session.state = "numerology_menu"

            case "numerology_menu":
                self.route_numerology_menu(session, user, chat_id, text)

            case "horoscope_ask_surname":
                if not text:
                    self.send_message(chat_id, "Пожалуйста, напиши фамилию.")
                else:
                    surname = self._normalize_name(text)
                    if self._is_system_command(surname):
                        self.show_main_menu(chat_id, user)
                        session.state = "main_menu"
                    elif not self._validate_surname(surname):
                        self.send_message(
                            chat_id,
                            "Пожалуйста, напиши фамилию только буквами (без эмодзи и команд).",
                        )
                    else:
                        user.surname = surname[:100]

                        if not user.birth_time:
                            self.send_message(
                                chat_id,
                                "Укажи время рождения в формате ЧЧ:ММ. Если не знаешь, нажми «Не знаю».",
                                [["Не знаю"]],
                            )
                            session.state = "horoscope_ask_birth_time"
                        else:
                            self.show_horoscope_menu(chat_id, user)
                            session.state = "horoscope_menu"

            case "horoscope_ask_birth_time":
                if text == "Не знаю":
                    user.birth_time = None
                    self.show_horoscope_menu(chat_id, user)
                    session.state = "horoscope_menu"
                elif not self.validate_time(text):
                    self.send_message(
                        chat_id,
                        "Пожалуйста, введи время в формате ЧЧ:ММ (например: 08:30) или нажми «Не знаю».",
                        [["Не знаю"]],
                    )
                else:
                    user.birth_time = f"{text}:00"
                    self.show_horoscope_menu(chat_id, user)
                    session.state = "horoscope_menu"

            case "horoscope_menu":
                self.route_horoscope_menu(session, user, chat_id, text)

            case "podruzhka_free":
                self.handle_podruzhka_free(session, user, chat_id, text)

            case "podruzhka_chat":
                self.handle_podruzhka_chat(session, user, chat_id, text)

            case "subscription_menu":
                self.route_subscription_menu(session, user, chat_id, text)

            case "await_payment":
                self.handle_payment_status(session, user, chat_id, text)

            case "support_ask":
                if text == "Назад в меню":
                    self.show_main_menu(chat_id, user)
                    session.state = "main_menu"
                elif not text:
                    self.send_message(chat_id, "Опиши проблему одним сообщением.")
                else:
                    self.storage.log_chat_message(
                        chat_id,
                        "system",
                        f"SUPPORT_REQUEST: {text}",
                        meta={"source": "support_request"},
                    )
                    self.send_message(
                        chat_id,
                        "Спасибо! Я передала сообщение администратору. Мы ответим как можно скорее.",
                        [["Назад в меню"]],
                    )
                    session.state = "main_menu"

            case _:
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"

        self.storage.save_user(user)
        self.storage.save_session(session)

    def show_welcome(self, chat_id: int) -> None:
        text = (
            "Привет, я Эльза — твоя подружка 🌸\n"
            "Рада, что ты заглянула ко мне. Здесь можно быть настоящей — я рядом, чтобы слушать, поддерживать и помогать.\n"
            "Без осуждений, без масок — только тёплый диалог.\n"
            "Хочешь познакомиться поближе? Жми «Старт» 💌\n\n"
            "Перед тем как продолжить, нужно согласие на обработку персональных данных (Имя, дата рождения)."
        )
        self.send_message(chat_id, text, [["Старт"]])

    def show_main_menu(self, chat_id: int, user: User) -> None:
        name = user.name if user.name else "Подруга"
        text = (
            f"{name}, теперь давай выберем, с чего начнём 💫\n"
            "Я рядом, чтобы помочь — просто выбери раздел, который тебе сейчас ближе."
        )
        keyboard = [
            ["🃏 Расклад Таро", "🃏 Режим таролога"],
            ["🔢 Нумерология", "♒ Гороскоп"],
            ["💬 Подружка", "💎 Подписка"],
            ["ℹ️ Помощь"],
        ]
        self.send_message(chat_id, text, keyboard)

    def route_main_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        match text:
            case "🃏 Расклад Таро":
                self.send_message(
                    chat_id,
                    "Выбери тип расклада:",
                    [
                        ["Таро на день", "Таро на любовь"],
                        ["Назад в меню"],
                    ],
                )
                session.state = "taro_menu"

            case "🃏 Режим таролога":
                self.start_tarot_mode(session, user, chat_id)

            case "🔢 Нумерология":
                if not user.surname:
                    self.send_message(chat_id, "Пожалуйста, укажи свою фамилию:")
                    session.state = "numerology_ask_surname"
                else:
                    self.render_numerology_menu(chat_id, user)
                    session.state = "numerology_menu"

            case "♒ Гороскоп":
                if not user.surname:
                    self.send_message(chat_id, "Пожалуйста, укажи свою фамилию:")
                    session.state = "horoscope_ask_surname"
                elif not user.birth_time:
                    self.send_message(
                        chat_id,
                        "Укажи время рождения в формате ЧЧ:ММ. Если не знаешь, нажми «Не знаю».",
                        [["Не знаю"]],
                    )
                    session.state = "horoscope_ask_birth_time"
                else:
                    self.show_horoscope_menu(chat_id, user)
                    session.state = "horoscope_menu"

            case "💬 Подружка":
                if user.subscription != "paid" and user.podruzhka_free_used_at:
                    self.send_message(
                        chat_id,
                        "Бесплатный совет уже получен. Чтобы продолжить беседу без ограничений, оформи подписку 💗",
                        [["Получить доступ", "Назад в меню"]],
                    )
                    return

                self.send_message(
                    chat_id,
                    "Привет, я твоя Подружка. Можешь рассказать мне всё, что у тебя на душе. Я рядом, выслушаю, пойму",
                    [["Закончить разговор"]],
                )

                session.state = "podruzhka_chat" if user.subscription == "paid" else "podruzhka_free"

            case "💎 Подписка" | "Получить доступ":
                self.show_subscription_menu(chat_id)
                session.state = "subscription_menu"

            case "ℹ️ Помощь":
                self.send_message(
                    chat_id,
                    "Я помогу:\n• Сформулировать вопрос к Таро\n• Сделать базовый расклад (3 карты бесплатно) или глубокий расклад (7 карт для подписчиков)\n\n"
                    f"{self._subscription_benefits_text()}\n\n"
                    "Просто выбери «🃏 Расклад Таро» и следуй подсказкам.",
                    [["Связаться с администратором"], ["Назад в меню"]],
                )
            case "Связаться с администратором":
                self.send_message(
                    chat_id,
                    "Опиши проблему одним сообщением — я передам администратору.",
                    [["Назад в меню"]],
                )
                session.state = "support_ask"

            case _:
                self.show_main_menu(chat_id, user)

    def route_taro_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Назад в меню":
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        session.data = session.data or {}
        session.data["taro_type"] = text

        suggest = (
            f"Отлично — мы выбрали: <b>{text}</b>.\n\n"
            "Чтобы получить точный ответ, сформулируй конкретный вопрос. Примеры:\n"
            "✅ «Какие чувства у Никиты ко мне?»\n"
            "✅ «Будем ли мы вместе с Никитой?»\n"
            "❌ Не: «Что меня ждет с ним?» — слишком общее.\n\n"
            "Напиши свой вопрос одним сообщением."
        )
        self.send_message(
            chat_id,
            suggest,
            [["Назад в меню"]],
        )

        session.state = "taro_ask_question"

    def handle_taro_question(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Назад в меню":
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return
        if text == "Задать вопрос":
            self.send_message(chat_id, "Пожалуйста, напиши свой вопрос одним сообщением.", [["Назад в меню"]])
            session.state = "taro_ask_question"
            return

        cards = 7 if user.subscription == "paid" else 3

        if user.subscription != "paid":
            free_count = self.storage.count_taro_readings(chat_id=user.chat_id, cards_count=3)
            if free_count >= 1:
                self.send_message(
                    chat_id,
                    "Бесплатный расклад уже был использован. 🌸\n\n"
                    "Чтобы делать больше раскладов и получать рекомендации, подключи подписку.",
                    [["Получить доступ", "Назад в меню"]],
                )
                session.state = "main_menu"
                return

        if user.subscription == "paid":
            today = datetime.now().strftime("%Y-%m-%d")
            paid_used_today = self.storage.count_taro_readings_for_date(
                chat_id=user.chat_id,
                cards_count=3,
                date_value=today,
            )
            if paid_used_today >= 10:
                self.send_message(
                    chat_id,
                    "Ты использовала все 10 платных раскладов на сегодня 🌸\n\n"
                    "Завтра сможешь продолжить или обратись к поддержке, если нужна расширенная сессия.",
                    [["Назад в меню"]],
                )
                session.state = "main_menu"
                return

        type_value = session.data.get("taro_type", "Расклад")
        prompt = self.build_taro_prompt(user.name or "Подруга", type_value, text, cards)

        self.send_message(
            chat_id,
            "Сейчас я посоветуюсь с картами и соберу расклад — это займёт пару секунд ✨",
        )

        ai_response = self.ask_ai(prompt)
        ai_meta = self._ai_meta(ai_response)
        if not ai_response:
            result = "К сожалению, сейчас я не могу подготовить расклад. Но не переживай — мы вернёмся к этому чуть позже."
        else:
            result = ai_response.content

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            f"Спасибо, {user.name}, что поделилась своим вопросом 🌸\n\n"
            f"<b>Вопрос:</b> {text}\n\n"
            f"<b>Расклад ({cards} карты):</b>\n"
            f"{result}\n\n"
            "Спасибо, что открываешься — если хочешь ещё углубиться, рассмотрим платную версию (7 карт и персональные рекомендации).\n\n"
            f"{self._subscription_benefits_text()}"
        )

        self.storage.create_taro_reading(
            chat_id=user.chat_id,
            user_name=user.name,
            birth_date=user.birth_date,
            type_value=type_value,
            question=text,
            cards_count=cards,
            result=result,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )

        if user.subscription == "paid":
            self.send_message(chat_id, final, [["Задать ещё вопрос", "Назад в меню"]], meta=ai_meta)
            session.state = "taro_menu"
        else:
            final += "\n\nСпасибо, что доверилась. Если хочешь получать больше раскладов и персональные рекомендации — подключи подписку 💎"
            self.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]], meta=ai_meta)
            self.schedule_retention(user)
            session.state = "main_menu"

    def start_tarot_mode(self, session: TgSession, user: User, chat_id: int) -> None:
        if not self._check_tarot_mode_limit(session, user, chat_id):
            return
        self._reset_tarot_mode_session(session)
        text = (
            "У тебя есть карты, но ты не уверена в трактовке? Я помогу 💜\n"
            "На какую сферу гадаем?\n"
            "Выбери или напиши: отношения / работа / деньги / выбор"
        )
        keyboard = [["отношения", "работа", "деньги"], ["выбор", "другое"], ["В меню"]]
        self.send_message(chat_id, text, keyboard)
        session.state = "tarot_mode_topic"

    def handle_tarot_mode_topic(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text in {"В меню", "Назад в меню"}:
            self._reset_tarot_mode_session(session)
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if text.lower() == "другое":
            self.send_message(chat_id, "Напиши тему одним-двумя словами.")
            session.state = "tarot_mode_topic"
            return

        session.data = session.data or {}
        session.data["tarot_mode_topic"] = text.strip()
        self.send_message(
            chat_id,
            "На какой срок смотрим?\nсейчас / неделя / месяц / три месяца / пол года / год",
            [["сейчас", "неделя", "месяц"], ["три месяца", "пол года", "год"], ["В меню"]],
        )
        session.state = "tarot_mode_timeframe"

    def handle_tarot_mode_timeframe(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text in {"В меню", "Назад в меню"}:
            self._reset_tarot_mode_session(session)
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        session.data = session.data or {}
        session.data["tarot_mode_timeframe"] = text.strip()

        topic = session.data.get("tarot_mode_topic", "")
        timeframe = session.data.get("tarot_mode_timeframe", "")
        prompt = self.build_tarot_mode_spread_prompt(topic, timeframe)
        system = "Ты опытный таролог и методолог раскладов. Отвечай по-русски."

        ai_response = self.ask_ai(prompt, system)
        ai_meta = self._ai_meta(ai_response)
        if not ai_response:
            spread_text = self.build_tarot_mode_spread_fallback(topic, timeframe)
        else:
            spread_text = ai_response.content.strip()

        cards_required = self._extract_tarot_spread_cards_count(spread_text)
        session.data["tarot_mode_spread_text"] = spread_text
        session.data["tarot_mode_cards_required"] = cards_required
        session.data["tarot_mode_ai_meta"] = ai_meta

        self.send_message(chat_id, spread_text, meta=ai_meta)
        self.send_message(
            chat_id,
            "Пришли мне выпавшие карты списком и обязательно укажи прямые/перевёрнутые.\n"
            "Пример:\n"
            "1) 3 жезлов (прямая)\n"
            "2) Король мечей (перевёрнутая)\n"
            "...",
            [["? ????"]],
        )
        session.state = "tarot_mode_cards"

    def handle_tarot_mode_cards(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text in {"В меню", "Назад в меню"}:
            self._reset_tarot_mode_session(session)
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        parsed = self._parse_tarot_cards(text)
        if parsed is None:
            self.send_message(
                chat_id,
                "Не вижу список карт в нужном формате. Повтори, пожалуйста, по примеру:\n"
                "1) 3 жезлов (прямая)\n"
                "2) Король мечей (перевёрнутая)\n"
                "...",
            )
            session.state = "tarot_mode_cards"
            return

        cards = parsed
        cards_required = session.data.get("tarot_mode_cards_required")
        if isinstance(cards_required, int):
            if len(cards) != cards_required:
                self.send_message(
                    chat_id,
                    f"В раскладе {cards_required} карт. Пришли, пожалуйста, ровно {cards_required} карт по примеру.",
                )
                session.state = "tarot_mode_cards"
                return
        elif len(cards) < 3:
            self.send_message(
                chat_id,
                "Нужно минимум 3 карты. Повтори, пожалуйста, по примеру.",
            )
            session.state = "tarot_mode_cards"
            return

        if not self._check_tarot_mode_limit(session, user, chat_id):
            return

        topic = session.data.get("tarot_mode_topic", "")
        timeframe = session.data.get("tarot_mode_timeframe", "")
        spread_text = session.data.get("tarot_mode_spread_text", "")
        question = session.data.get("tarot_mode_question", "")

        cards_text = "\n".join(
            f"{idx}) {card['name']} ({card['orientation']})" for idx, card in enumerate(cards, start=1)
        )
        prompt = self.build_tarot_mode_interpret_prompt(
            topic=topic,
            timeframe=timeframe,
            question=question,
            spread_text=spread_text,
            cards_text=cards_text,
        )
        system = "Ты опытный таролог. Интерпретируй карты бережно и практично."

        self.send_message(chat_id, "Готовлю расшифровку, минутку.")
        ai_response = self.ask_ai(prompt, system)
        ai_meta = self._ai_meta(ai_response)
        if not ai_response:
            self.send_message(chat_id, "Сейчас не могу расшифровать расклад. Попробуй чуть позже.")
            self._reset_tarot_mode_session(session)
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        self.storage.create_tarot_mode_log(
            chat_id=user.chat_id,
            topic=topic,
            timeframe=timeframe,
            spread=spread_text,
            cards=cards_text,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )

        self.send_message(
            chat_id,
            ai_response.content.strip(),
            [["Сделать ещё расклад", "В меню"]],
            meta=ai_meta,
        )
        self._reset_tarot_mode_session(session)
        session.state = "tarot_mode_done"

    def handle_tarot_mode_done(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Сделать ещё расклад":
            self.start_tarot_mode(session, user, chat_id)
            return
        if text == "В меню":
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return
        self.send_message(chat_id, "Выбери действие:", [["Сделать ещё расклад", "В меню"]])
        session.state = "tarot_mode_done"

    def render_numerology_menu(self, chat_id: int, user: User) -> None:
        text = "Выбери формат нумерологического разбора:"
        keyboard = [["Бесплатно", "Полный анализ"], ["Назад в меню"]]
        self.send_message(chat_id, text, keyboard)

    def show_horoscope_menu(self, chat_id: int, user: User) -> None:
        text = "Выбери формат гороскопа:"
        keyboard = [["Бесплатно", "Полный гороскоп"], ["Назад в меню"]]
        self.send_message(chat_id, text, keyboard)

    def route_numerology_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        match text:
            case "Бесплатно":
                self.handle_numerology_free(session, user, chat_id)
            case "Полный анализ":
                self.handle_numerology_paid(session, user, chat_id)
            case "Назад в меню":
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case _:
                self.render_numerology_menu(chat_id, user)

    def route_horoscope_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        match text:
            case "Бесплатно":
                self.handle_horoscope_free(session, user, chat_id)
            case "Полный гороскоп":
                self.handle_horoscope_paid(session, user, chat_id)
            case "Назад в меню":
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case _:
                self.show_horoscope_menu(chat_id, user)

    def handle_podruzhka_free(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Закончить разговор":
            self.send_message(
                chat_id,
                "Спасибо, что доверилась мне. Помни: ты ценная и важная. Я всегда рядом, когда захочешь поговорить.",
            )
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if self.is_distress_message(text):
            self.send_message(
                chat_id,
                "Если тебе очень тяжело, пожалуйста, обратись к специалисту. Я рядом, но живой человек — лучшее решение в таких ситуациях.",
                [["Закончить разговор"]],
            )
            return

        safe_text = text[: self.PODRUZHKA_MAX_INPUT_CHARS]
        ai_response = self.ask_ai(safe_text, self.build_podruzhka_system_prompt())
        ai_meta = self._ai_meta(ai_response)
        if not ai_response:
            self.send_message(
                chat_id,
                "Сейчас не получается ответить. Попробуй ещё раз чуть позже.",
                [["Назад в меню"]],
            )
            session.state = "main_menu"
            return

        reply = ai_response.content
        if len(reply) > 300:
            reply = reply[:300] + "..."

        final = (
            reply
            + "\n\nСпасибо, что написала. Я рядом, даже когда трудно. 💗\n"
            + "Если хочешь продолжать беседу без ограничений и получать упражнения и поддержку в любой момент — подключи подписку.\n\n"
            + f"{self._subscription_benefits_text()}"
        )

        self.send_message(
            chat_id,
            final,
            [["Получить доступ", "Назад в меню"]],
            meta=self._podruzhka_meta(ai_meta),
        )
        user.podruzhka_free_used_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.schedule_retention(user)
        session.state = "main_menu"

    def handle_podruzhka_chat(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Закончить разговор":
            self.send_message(
                chat_id,
                "Спасибо, что доверилась мне. Помни: ты ценная и важная. Я всегда рядом, когда захочешь поговорить.",
            )
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if self.is_distress_message(text):
            self.send_message(
                chat_id,
                "Если тебе очень тяжело, пожалуйста, обратись к специалисту. Я рядом, но живой человек — лучшее решение в таких ситуациях.",
                [["Закончить разговор"]],
            )
            return

        today = datetime.now().strftime("%Y-%m-%d")
        used_today = self.storage.count_podruzhka_replies_for_date(
            chat_id=user.chat_id,
            date_value=today,
        )
        if used_today >= self.PODRUZHKA_DAILY_LIMIT:
            self.send_message(
                chat_id,
                "На сегодня лимит сообщений в Подружке исчерпан. Давай продолжим завтра.",
                [["Назад в меню"]],
            )
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        safe_text = text[: self.PODRUZHKA_MAX_INPUT_CHARS]
        ai_response = self.ask_ai(safe_text, self.build_podruzhka_system_prompt())
        ai_meta = self._ai_meta(ai_response)
        if not ai_response:
            self.send_message(
                chat_id,
                "Сейчас не получается ответить. Давай попробуем позже.",
                [["Закончить разговор"]],
            )
            session.state = "podruzhka_chat"
            return

        reply = ai_response.content
        if len(reply) > self.PODRUZHKA_MAX_REPLY_CHARS:
            reply = reply[: self.PODRUZHKA_MAX_REPLY_CHARS] + "..."

        self.send_message(
            chat_id,
            reply,
            [["Закончить разговор"]],
            meta=self._podruzhka_meta(ai_meta),
        )
        session.state = "podruzhka_chat"

    def handle_numerology_free(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            used = self.storage.numerology_exists(chat_id=user.chat_id, type_value="money_code")
            if used:
                self.send_message(
                    chat_id,
                    "Бесплатный расчёт уже доступен только один раз. Чтобы получить полный разбор, оформи подписку.",
                    [["Получить доступ", "Назад в меню"]],
                )
                session.state = "main_menu"
                return
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            paid_used_today = self.storage.count_numerology_readings_for_date(
                chat_id=user.chat_id,
                date_value=today,
            )
            if paid_used_today >= 10:
                self.send_message(
                    chat_id,
                    "Ты использовала все 10 нумерологических разборов на сегодня. Попробуй завтра.",
                    [["Назад в меню"]],
                )
                session.state = "main_menu"
                return

        prompt = self.build_money_code_prompt(user.name or "", user.birth_date)
        self.send_message(chat_id, "Считаю твой денежный код, подожди пару секунд ✨")
        ai_response = self.ask_ai(prompt)
        ai_meta = self._ai_meta(ai_response)

        if not ai_response:
            result = "Сейчас не получается рассчитать код. Попробуй ещё раз позже."
        else:
            result = ai_response.content

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            result
            + "\n\nЭто твой денежный код. Он помогает понять, как ты взаимодействуешь с финансовыми потоками. 💸\n"
            + "Спасибо, что попробовала! Если хочешь узнать свои сильные стороны, кармические задачи и код активации изобилия, подключи подписку и получи расширенный нумерологический портрет. ✨\n\n"
            + f"{self._subscription_benefits_text()}"
        )

        self.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]], meta=ai_meta)
        self.schedule_retention(user)

        self.storage.create_numerology_reading(
            chat_id=user.chat_id,
            user_name=user.name,
            surname=user.surname,
            birth_date=user.birth_date,
            type_value="money_code",
            result=result,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )
        session.state = "main_menu"

    def handle_numerology_paid(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            self.send_message(
                chat_id,
                "Подробный нумерологический анализ доступен по подписке.",
                [["Получить доступ", "Назад в меню"]],
            )
            session.state = "numerology_menu"
            return

        today = datetime.now().strftime("%Y-%m-%d")
        paid_used_today = self.storage.count_numerology_readings_for_date(
            chat_id=user.chat_id,
            date_value=today,
        )
        if paid_used_today >= 10:
            self.send_message(
                chat_id,
                "Ты использовала все 10 нумерологических разборов на сегодня. Попробуй завтра.",
                [["Назад в меню"]],
            )
            session.state = "numerology_menu"
            return

        birth = (
            datetime.strptime(user.birth_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            if user.birth_date
            else ""
        )
        prompt = self.build_numerology_prompt(user.name or "", user.surname or "", birth)
        self.send_message(
            chat_id,
            "Собираю твою нумерологическую карту, подожди чуть-чуть ✨",
        )
        ai_response = self.ask_ai(prompt)
        ai_meta = self._ai_meta(ai_response)

        if not ai_response:
            result = "Сейчас не получается подготовить анализ. Попробуй позже."
        else:
            result = ai_response.content

        if len(result) > 4000:
            result = result[:4000] + "..."

        self.send_message(chat_id, result, [["Назад в меню"]], meta=ai_meta)

        self.storage.create_numerology_reading(
            chat_id=user.chat_id,
            user_name=user.name,
            surname=user.surname,
            birth_date=user.birth_date,
            type_value="full",
            result=result,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )

        session.state = "numerology_menu"

    def handle_horoscope_free(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            used = self.storage.horoscope_exists(chat_id=user.chat_id, type_value="daily")
            if used:
                self.send_message(
                    chat_id,
                    "Ты уже получила краткий гороскоп. Чтобы узнать больше и получить полный прогноз, подключи подписку 🌌",
                    [["Получить доступ", "Назад в меню"]],
                )
                session.state = "main_menu"
                return
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            paid_used_today = self.storage.count_horoscope_readings_for_date(
                chat_id=user.chat_id,
                date_value=today,
            )
            if paid_used_today >= 10:
                self.send_message(
                    chat_id,
                    "Ты использовала все 10 гороскопов на сегодня. Попробуй завтра.",
                    [["Назад в меню"]],
                )
                session.state = "main_menu"
                return

        sign = self.get_zodiac_sign(user.birth_date)
        prompt = self.build_horoscope_free_prompt(sign)
        self.send_message(chat_id, "Смотрю твою астрологическую волну, подожди пару секунд ✨")
        ai_response = self.ask_ai(prompt)
        ai_meta = self._ai_meta(ai_response)

        if not ai_response:
            result = "Сейчас не получается построить гороскоп. Попробуй позже."
        else:
            result = ai_response.content

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            f"Твой знак — {sign}.\n"
            f"{result}\n\n"
            "Это краткий взгляд на твою текущую астрологическую волну.\n"
            "Спасибо, что заглянула! Полный гороскоп по всем сферам жизни доступен по подписке: любовь, деньги, самореализация. 🌌\n\n"
            f"{self._subscription_benefits_text()}"
        )

        self.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]], meta=ai_meta)
        self.schedule_retention(user)

        self.storage.create_horoscope_reading(
            chat_id=user.chat_id,
            user_name=user.name,
            surname=user.surname,
            birth_date=user.birth_date,
            birth_time=user.birth_time,
            sign=sign,
            type_value="daily",
            result=result,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )

        session.state = "main_menu"

    def handle_horoscope_paid(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            self.send_message(
                chat_id,
                "Полный гороскоп доступен по подписке.",
                [["Получить доступ", "Назад в меню"]],
            )
            session.state = "horoscope_menu"
            return

        today = datetime.now().strftime("%Y-%m-%d")
        paid_used_today = self.storage.count_horoscope_readings_for_date(
            chat_id=user.chat_id,
            date_value=today,
        )
        if paid_used_today >= 10:
            self.send_message(
                chat_id,
                "Ты использовала все 10 гороскопов на сегодня. Попробуй завтра.",
                [["Назад в меню"]],
            )
            session.state = "horoscope_menu"
            return

        birth = (
            datetime.strptime(user.birth_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            if user.birth_date
            else ""
        )
        time_value = (
            datetime.strptime(user.birth_time, "%H:%M:%S").strftime("%H:%M")
            if user.birth_time
            else "неизвестно"
        )
        prompt = self.build_horoscope_prompt(user.name or "", user.surname or "", birth, time_value)
        self.send_message(
            chat_id,
            "Готовлю твой подробный гороскоп, подожди немного ✨",
        )
        ai_response = self.ask_ai(prompt)
        ai_meta = self._ai_meta(ai_response)

        if not ai_response:
            result = "Сейчас не получается подготовить гороскоп. Попробуй позже."
        else:
            result = ai_response.content

        if len(result) > 4000:
            result = result[:4000] + "..."

        self.send_message(chat_id, result, [["Назад в меню"]], meta=ai_meta)

        self.storage.create_horoscope_reading(
            chat_id=user.chat_id,
            user_name=user.name,
            surname=user.surname,
            birth_date=user.birth_date,
            birth_time=user.birth_time,
            sign=self.get_zodiac_sign(user.birth_date),
            type_value="full",
            result=result,
            meta={
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": self.shorten(prompt, 800),
                **ai_meta,
            },
        )

        session.state = "horoscope_menu"

    def is_positive(self, text: str) -> bool:
        t = text.lower()
        return t in {"старт", "да", "ok", "okey", "начать", "start", "давай", "готово"}

    def validate_date(self, text: str) -> bool:
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", text):
            return False
        try:
            datetime.strptime(text, "%d.%m.%Y")
            return True
        except ValueError:
            return False

    def validate_time(self, text: str) -> bool:
        if not re.fullmatch(r"\d{2}:\d{2}", text):
            return False
        h, m = text.split(":")
        return 0 <= int(h) < 24 and 0 <= int(m) < 60

    def build_podruzhka_system_prompt(self) -> str:
        return (
            "Ты — добрая, понимающая, внимательная подруга. Твоя задача — поддерживать, выслушивать, "
            "помогать словами и мягко направлять, если нужно. Никакой оценки. Ты можешь говорить с юмором, "
            "тепло, но всегда с уважением. Избегай клише и сухих фраз. Отвечай коротко: 3-6 предложений, "
            "до 900 символов."
        )

    def is_distress_message(self, text: str) -> bool:
        t = text.lower()
        for word in ["суиц", "самоуб", "убью", "смерть", "умереть"]:
            if word in t:
                return True
        return False

    def build_money_code_prompt(self, name: str, birth_date: str | None) -> str:
        birth = (
            datetime.strptime(birth_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            if birth_date
            else ""
        )
        return (
            f"На основе имени {name} и даты рождения {birth} вычисли денежный (финансовый) код. "
            "Верни одну цифру и краткое пояснение (1-2 предложения). Отвечай по-русски."
        )

    def build_numerology_prompt(self, name: str, surname: str, birth_date: str) -> str:
        system = "Ты — дружелюбный и заботливый нумеролог. Отвечай по-русски."
        instruction = (
            f"Рассчитай и расшифруй ключевые числа нумерологии по имени {name}, фамилии {surname} и дате рождения {birth_date}. "
            "Укажи число жизненного пути, число судьбы, число души, число личности, кармические долги и задачи, матрицу Пифагора. "
            "Сформируй структурированный отчёт: основные числа с кратким описанием и влиянием, текстовый прогноз 700-1500 символов по сферам "
            "(личность и потенциал, карьера и деньги, отношения и семья, сильные и слабые стороны, подсказки для настоящего периода жизни)."
        )
        return f"{system}\n\n{instruction}"

    def build_horoscope_free_prompt(self, sign: str) -> str:
        return (
            f"Сгенерируй краткий дневной гороскоп (2 предложения) для знака {sign} на сегодня. "
            "Стиль: мягкий, дружелюбный, например: 'Твоя энергия сейчас склонна к интроверсии, важно беречь себя. "
            "Подумай, что ты хочешь чувствовать, и начни с малого.'"
        )

    def build_horoscope_prompt(self, name: str, surname: str, birth_date: str, birth_time: str) -> str:
        system = "Ты — заботливый астролог. Отвечай по-русски."
        instruction = (
            f"На основе данных: имя {name}, фамилия {surname}, дата рождения {birth_date}, время рождения {birth_time} сформируй полный гороскоп на текущий месяц. "
            "Включи разделы: отношения, деньги, здоровье, духовность, а также эмоциональные рекомендации. Стиль дружелюбный, поддерживающий."
        )
        return f"{system}\n\n{instruction}"

    def get_zodiac_sign(self, birth_date: str | None) -> str:
        if not birth_date:
            return ""
        date_value = datetime.strptime(birth_date, "%Y-%m-%d")
        day = date_value.day
        month = date_value.month

        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "Овен"
        if (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "Телец"
        if (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "Близнецы"
        if (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "Рак"
        if (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "Лев"
        if (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "Дева"
        if (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "Весы"
        if (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "Скорпион"
        if (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "Стрелец"
        if (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return "Козерог"
        if (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "Водолей"
        return "Рыбы"

    def build_taro_prompt(self, name: str, type_value: str, question: str, cards: int) -> str:
        system = "Ты — нежный и заботливый таролог, говоришь мягко и поддерживающе. Отвечай по-русски."
        instruction = (
            f"Для пользователя {name} сделай расклад \"{type_value}\" на {cards} карт(ы). "
            "Дай название каждой карты (если возможно), краткую интерпретацию до 400 символов для каждой карты и общий вывод по раскладу (до 400 символов). "
            "Стиль: мягкий, поддерживающий, без категоричных предсказаний. В конце предложи 2-3 уточняющих вопроса, которые пользователь может задать для более точного ответа. "
            f"Вопрос пользователя: «{question}»."
        )
        return f"{system}\n\n{instruction}"

    def build_tarot_mode_spread_prompt(self, topic: str, timeframe: str) -> str:
        return (
            f"Сформируй инструкцию расклада для новичка.\n"
            f"Сфера: {topic}\n"
            f"Срок: {timeframe}\n\n"
            "Выбери один подходящий шаблон и адаптируй:\n"
            "• отношения/мысли-чувства-намерения (3–5)\n"
            "• перспектива/совет (4–5)\n"
            "• выбор A/B (6)\n"
            "• работа/деньги (5)\n\n"
            "Количество карт: от 3 до 7, предпочтительно 5.\n\n"
            "Строгий формат ответа (никаких других блоков):\n"
            "Расклад “<название>” (<N> карт)\n"
            "1) ...\n"
            "2) ...\n"
            "...\n"
            "Позиции:\n"
            "1 — ...\n"
            "2 — ...\n\n"
            "Требования:\n"
            "- Шаги строго 1..N, короткие и конкретные.\n"
            "- В шагах попроси держать/проговаривать вопрос во время тасовки.\n"
            "- Фразу «Если карта перевёрнутая — отметь это» включи как отдельное предложение в одном из шагов (не отдельной строкой вне шагов).\n"
            "- Не добавляй предисловий, предупреждений, лирики, эмодзи, текста “от себя”.\n"
            "- Не проси прислать карты и не давай формат ввода карт.\n"
            "- Ответ должен содержать только 3 блока: заголовок, шаги, позиции."
        )

    @staticmethod
    def build_tarot_mode_spread_fallback(topic: str, timeframe: str) -> str:
        return (
            f"Расклад “Фокус и перспектива” (5 карт)\n"
            "1) Сконцентрируйся на теме и сроке, держи/проговори вопрос во время тасовки.\n"
            "2) Выложи 1 карту.\n"
            "3) Выложи 2 карту.\n"
            "4) Выложи 3 карту.\n"
            "5) Выложи 4 и 5 карты. Если карта перевёрнутая — отметь это.\n"
            "Позиции:\n"
            "1 — Суть ситуации в сфере.\n"
            "2 — Что сейчас влияет на развитие.\n"
            "3 — Внутренний ресурс или препятствие.\n"
            "4 — Ближайшая перспектива.\n"
            "5 — Совет на срок."
        )

    @staticmethod
    def build_tarot_mode_interpret_prompt(
        *,
        topic: str,
        timeframe: str,
        question: str,
        spread_text: str,
        cards_text: str,
    ) -> str:
        question_value = question if question else "не задан"
        return (
            "Контекст расклада:\n"
            f"Сфера: {topic}\n"
            f"Срок: {timeframe}\n"
            f"Вопрос пользователя: {question_value}\n\n"
            "Расклад/позиции:\n"
            f"{spread_text}\n\n"
            "Выпавшие карты:\n"
            f"{cards_text}\n\n"
            "Ответ дай структурой:\n"
            "а) краткий вывод (2–4 предложения),\n"
            "б) трактовка по позициям,\n"
            "в) совет/рекомендации,\n"
            "г) предупреждение: «это не замена психологу/врачу» (коротко, без морали)."
        )

    @staticmethod
    def _extract_tarot_spread_cards_count(spread_text: str) -> int:
        match = re.search(r"\((\d+)\s*карт", spread_text, re.IGNORECASE)
        if not match:
            return 5
        try:
            value = int(match.group(1))
        except ValueError:
            return 5
        return value if 3 <= value <= 7 else 5

    @staticmethod
    def _parse_tarot_cards(text: str) -> list[dict[str, str]] | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        cards: list[dict[str, str]] = []
        placeholders = {
            "пустая",
            "пусто",
            "пустая карта",
            "пропуск",
            "пропуск карты",
            "нет карты",
            "нет",
            "-",
        }
        pattern_paren = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$", re.IGNORECASE)
        pattern_dash = re.compile(r"^(.+?)\s*[-–—]\s*(.+)$", re.IGNORECASE)
        orientation_re = re.compile(
            r"\b(" + "прям" + r"\w*|"
            + "перев" + r"\w*|"
            + "обрат" + r"\w*|revers\w*)\b",
            re.IGNORECASE,
        )

        for line in lines:
            if line in {"...", "…"}:
                continue
            cleaned = " ".join(line.split()).strip()
            cleaned = re.sub(r"^\d+[\).\-\s]*", "", cleaned).strip()
            if not cleaned:
                continue
            if cleaned.lower() in placeholders:
                cards.append({"name": "пустая карта", "orientation": "прямая"})
                continue

            name: str | None = None
            orientation_raw: str | None = None

            match = pattern_paren.match(cleaned)
            if match:
                name = match.group(1).strip()
                orientation_raw = match.group(2).strip()
            else:
                match = pattern_dash.match(cleaned)
                if match:
                    name = match.group(1).strip()
                    orientation_raw = match.group(2).strip()
                else:
                    match = orientation_re.search(cleaned)
                    if match:
                        orientation_raw = match.group(1).strip()
                        name = (cleaned[: match.start()] + cleaned[match.end() :]).strip(" -")

            if not name or not orientation_raw:
                return None
            if name.lower() in placeholders:
                continue

            orientation_raw = orientation_raw.lower()
            if "\u043f\u0440\u044f\u043c" in orientation_raw:
                orientation = "\u043f\u0440\u044f\u043c\u0430\u044f"
            elif (
                "\u043f\u0435\u0440\u0435\u0432" in orientation_raw
                or "\u043e\u0431\u0440\u0430\u0442" in orientation_raw
                or "revers" in orientation_raw
            ):
                orientation = "\u043f\u0435\u0440\u0435\u0432\u0451\u0440\u043d\u0443\u0442\u0430\u044f"
            else:
                return None
            cards.append({"name": name, "orientation": orientation})

        return cards or None

    def _check_tarot_mode_limit(self, session: TgSession, user: User, chat_id: int) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        used_today = self.storage.count_tarot_mode_for_date(user.chat_id, today)
        limit = self.TAROT_MODE_PAID_DAILY_LIMIT if user.subscription == "paid" else self.TAROT_MODE_FREE_DAILY_LIMIT
        if used_today < limit:
            return True

        if user.subscription == "paid":
            message = "На сегодня лимит режима таролога — 5 раскладов. Попробуй завтра."
        else:
            message = "На сегодня лимит режима таролога — 1 расклад. Попробуй завтра."

        self.send_message(chat_id, message, [["В меню"]])
        self._reset_tarot_mode_session(session)
        session.state = "main_menu"
        return False

    @staticmethod
    def _reset_tarot_mode_session(session: TgSession) -> None:
        session.data = session.data or {}
        keys = [key for key in session.data.keys() if key.startswith("tarot_mode_")]
        for key in keys:
            session.data.pop(key, None)

    def shorten(self, text: str, limit: int = 200) -> str:
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _normalize_name(text: str) -> str:
        return " ".join(text.split()).strip()

    def _is_system_command(self, text: str) -> bool:
        return text in self._SYSTEM_COMMANDS

    def _validate_surname(self, text: str) -> bool:
        if not text or self._is_system_command(text):
            return False
        return bool(self._SURNAME_RE.fullmatch(text))

    @staticmethod
    def _format_rub(amount: int) -> str:
        return f"{amount} ₽"

    @staticmethod
    def _subscription_benefits_text() -> str:
        return (
            "Преимущества подписки:\n"
            "• Таро: 7 карт и до 10 раскладов в день\n"
            "• Нумерология: полный анализ и до 10 разборов в день\n"
            "• Гороскоп: полный прогноз и до 10 гороскопов в день\n"
            "• Подружка: расширенный диалог, до 30 сообщений в день"
        )

    @staticmethod
    def _podruzhka_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(meta or {})
        payload["feature"] = "podruzhka"
        return payload

    def _subscription_amounts(self) -> dict[int, int]:
        base = self.storage.get_subscription_price_rub()
        amounts = {1: base}
        amounts[6] = int(round(base * 6 * 0.9))
        amounts[12] = int(round(base * 12 * 0.9))
        return amounts

    def show_subscription_menu(self, chat_id: int) -> None:
        amounts = self._subscription_amounts()
        text = (
            "Выбери тариф подписки:\n"
            f"• 1 месяц — {self._format_rub(amounts[1])}\n"
            f"• 6 месяцев — {self._format_rub(amounts[6])} (-10%)\n"
            f"• 12 месяцев — {self._format_rub(amounts[12])} (-10%)\n\n"
            f"{self._subscription_benefits_text()}"
        )
        keyboard = [["1 месяц", "6 месяцев (-10%)"], ["12 месяцев (-10%)", "Назад в меню"]]
        self.send_message(chat_id, text, keyboard)

    def route_subscription_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        amounts = self._subscription_amounts()
        match text:
            case "1 месяц":
                self._start_payment(session, chat_id, months=1, amount_rub=amounts[1])
            case "6 месяцев (-10%)":
                self._start_payment(session, chat_id, months=6, amount_rub=amounts[6])
            case "12 месяцев (-10%)":
                self._start_payment(session, chat_id, months=12, amount_rub=amounts[12])
            case "Назад в меню":
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case _:
                self.show_subscription_menu(chat_id)
                session.state = "subscription_menu"

    def _start_payment(self, session: TgSession, chat_id: int, *, months: int, amount_rub: int) -> None:
        description = f"Подписка на {months} мес."
        metadata = {"chat_id": chat_id, "months": months}
        try:
            created = self.payments.create_payment(
                amount_rub=amount_rub,
                description=description,
                metadata=metadata,
            )
        except Exception:
            self.send_message(
                chat_id,
                "Не удалось создать оплату. Попробуй позже или напиши в поддержку.",
                [["Назад в меню"]],
            )
            session.state = "main_menu"
            return

        self.storage.create_payment_record(
            chat_id=chat_id,
            yookassa_payment_id=created.payment_id,
            status=created.status,
            amount_rub=created.amount_rub,
            months=months,
            confirmation_url=created.confirmation_url,
        )
        self._schedule_payment_checks(chat_id, created.payment_id)
        session.data = session.data or {}
        session.data["payment_id"] = created.payment_id
        session.data["payment_months"] = months

        if created.confirmation_url:
            text = (
                "Для оплаты перейди по ссылке:\n"
                f"{created.confirmation_url}\n\n"
                "После оплаты нажми «Проверить оплату»."
            )
        else:
            text = "Оплата создана. После оплаты нажми «Проверить оплату»."

        self.send_message(chat_id, text, [["Проверить оплату"], ["Назад в меню"]])
        session.state = "await_payment"

    def handle_payment_status(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Назад в меню":
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if text not in {"Проверить оплату", "1 месяц", "6 месяцев (-10%)", "12 месяцев (-10%)"}:
            self.send_message(chat_id, "Нажми «Проверить оплату», чтобы подтвердить платёж.")
            return

        if text in {"1 месяц", "6 месяцев (-10%)", "12 месяцев (-10%)"}:
            self.route_subscription_menu(session, user, chat_id, text)
            return

        payment_id = (session.data or {}).get("payment_id")
        if not payment_id:
            last_payment = self.storage.get_last_pending_payment(chat_id)
            payment_id = last_payment.yookassa_payment_id if last_payment else None

        if not payment_id:
            self.send_message(
                chat_id,
                "Не нашла активный платёж. Выбери тариф ещё раз.",
                [["1 месяц", "6 месяцев (-10%)"], ["12 месяцев (-10%)", "Назад в меню"]],
            )
            session.state = "subscription_menu"
            return

        self._process_payment_status(
            session=session,
            user=user,
            chat_id=chat_id,
            payment_id=payment_id,
            notify_pending=True,
            notify_errors=True,
        )

    def handle_scheduled_payment_check(self, chat_id: int, payment_id: str) -> None:
        session = self.storage.get_or_create_session(chat_id)
        user = self.storage.get_or_create_user(chat_id)
        self._process_payment_status(
            session=session,
            user=user,
            chat_id=chat_id,
            payment_id=payment_id,
            notify_pending=False,
            notify_errors=False,
        )
        self.storage.save_user(user)
        self.storage.save_session(session)

    def _activate_subscription(self, user: User, months: int) -> None:
        now = datetime.now()
        user.subscription = "paid"
        user.subscription_expires_at = self._add_months(now, months).strftime("%Y-%m-%d %H:%M:%S")

    def _schedule_payment_checks(self, chat_id: int, payment_id: str) -> None:
        now = datetime.now()
        for minutes in (5, 10):
            payload = f"{self.PAYMENT_REMINDER_PREFIX}|{payment_id}|{minutes}"
            self.storage.create_reminder(chat_id, payload, now + timedelta(minutes=minutes))

    def _process_payment_status(
        self,
        *,
        session: TgSession,
        user: User,
        chat_id: int,
        payment_id: str,
        notify_pending: bool,
        notify_errors: bool,
    ) -> None:
        payment = self.storage.get_payment_by_id(payment_id)
        if payment and payment.status == "succeeded":
            return

        try:
            status = self.payments.get_payment_status(payment_id)
        except Exception:
            if notify_errors:
                self.send_message(chat_id, "Не удалось проверить оплату. Попробуй ещё раз через минуту.")
            return

        if status == "succeeded":
            months = payment.months if payment else (session.data or {}).get("payment_months", 1)
            self._activate_subscription(user, months)
            self.storage.update_payment_status(payment_id, status, self._now_str())
            self.send_message(chat_id, f"Оплата прошла! Подписка активирована на {months} мес. 💎")
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if status == "canceled":
            self.storage.update_payment_status(payment_id, status, None)
            self.send_message(
                chat_id,
                "Платёж отменён. Если нужно, оформи подписку ещё раз.",
                [["1 месяц", "6 месяцев (-10%)"], ["12 месяцев (-10%)", "Назад в меню"]],
            )
            session.state = "subscription_menu"
            return

        self.storage.update_payment_status(payment_id, status, None)
        if notify_pending:
            self.send_message(
                chat_id,
                "Платёж ещё не завершён. Попробуй проверить чуть позже.",
                [["Проверить оплату"], ["Назад в меню"]],
            )
        session.state = "await_payment"

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def schedule_retention(self, user: User) -> None:
        if user.subscription == "paid":
            return
        if user.retention_message_sent_at:
            return
        if self.storage.reminder_exists(user.chat_id):
            return

        send_at = datetime.now() + timedelta(hours=6)
        self.storage.create_reminder(user.chat_id, self.RETENTION_MESSAGES[0], send_at)

    def ask_ai(self, prompt: str, system: str | None = None) -> AIResponse | None:
        try:
            return self.ai.get_answer(prompt, system)
        except Exception as exc:
            logging.warning("AI error: %s", exc)
            return None

    @staticmethod
    def _ai_meta(response: AIResponse | None) -> dict[str, Any]:
        if not response:
            return {}
        meta: dict[str, Any] = {}
        if response.usage:
            meta["usage"] = response.usage
        if response.model:
            meta["model"] = response.model
        if meta:
            meta.setdefault("source", "openai")
        return meta

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)
