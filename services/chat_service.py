from __future__ import annotations

from datetime import datetime, timedelta
import calendar
import logging
import re

from storage import Storage, TgSession, User
from .ai_service import AIService
from .tg_service import TgService


class ChatService:
    def __init__(self, tg: TgService, ai: AIService, storage: Storage) -> None:
        self.tg = tg
        self.ai = ai
        self.storage = storage

    def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        session = self.storage.get_or_create_session(chat_id)
        user = self.storage.get_or_create_user(chat_id)

        match session.state:
            case "start":
                self.show_welcome(chat_id)
                session.state = "ask_consent"

            case "ask_consent":
                if self.is_positive(text):
                    self.tg.send_message(
                        chat_id,
                        "Спасибо ❤️\nПожалуйста, укажи своё имя (Напиши имя, чтобы я могла к тебе обращаться):",
                    )
                    session.state = "ask_name"
                else:
                    self.tg.send_message(
                        chat_id,
                        "Нажми «Старт», когда будешь готова начать.",
                        [["Старт"]],
                    )

            case "ask_name":
                if not text:
                    self.tg.send_message(chat_id, "Пожалуйста, напиши имя (например: Анна).")
                else:
                    user.name = text[:100]
                    self.tg.send_message(
                        chat_id,
                        f"Приятно познакомиться, {user.name}! Теперь, пожалуйста, введи дату рождения в формате ДД.MM.ГГГГ",
                    )
                    session.state = "ask_birth_date"

            case "ask_birth_date":
                if not self.validate_date(text):
                    self.tg.send_message(
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

            case "numerology_ask_surname":
                if not text:
                    self.tg.send_message(chat_id, "Пожалуйста, напиши фамилию.")
                else:
                    user.surname = text[:100]
                    self.render_numerology_menu(chat_id, user)
                    session.state = "numerology_menu"

            case "numerology_menu":
                self.route_numerology_menu(session, user, chat_id, text)

            case "horoscope_ask_surname":
                if not text:
                    self.tg.send_message(chat_id, "Пожалуйста, напиши фамилию.")
                else:
                    user.surname = text[:100]

                    if not user.birth_time:
                        self.tg.send_message(
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
                    self.tg.send_message(
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
        self.tg.send_message(chat_id, text, [["Старт"]])

    def show_main_menu(self, chat_id: int, user: User) -> None:
        name = user.name if user.name else "Подруга"
        text = (
            f"{name}, теперь давай выберем, с чего начнём 💫\n"
            "Я рядом, чтобы помочь — просто выбери раздел, который тебе сейчас ближе."
        )
        keyboard = [
            ["🃏 Расклад Таро", "🔢 Нумерология"],
            ["♒ Гороскоп", "💬 Подружка"],
            ["💎 Подписка", "ℹ️ Помощь"],
        ]
        self.tg.send_message(chat_id, text, keyboard)

    def route_main_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        match text:
            case "🃏 Расклад Таро":
                self.tg.send_message(
                    chat_id,
                    "Выбери тип расклада:",
                    [
                        ["Таро на день", "Таро на любовь"],
                        ["Другой вопрос", "Назад в меню"],
                    ],
                )
                session.state = "taro_menu"

            case "🔢 Нумерология":
                if not user.surname:
                    self.tg.send_message(chat_id, "Пожалуйста, укажи свою фамилию:")
                    session.state = "numerology_ask_surname"
                else:
                    self.render_numerology_menu(chat_id, user)
                    session.state = "numerology_menu"

            case "♒ Гороскоп":
                if not user.surname:
                    self.tg.send_message(chat_id, "Пожалуйста, укажи свою фамилию:")
                    session.state = "horoscope_ask_surname"
                elif not user.birth_time:
                    self.tg.send_message(
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
                    self.tg.send_message(
                        chat_id,
                        "Бесплатный совет уже получен. Чтобы продолжить беседу без ограничений, оформи подписку 💗",
                        [["Получить доступ", "Назад в меню"]],
                    )
                    return

                self.tg.send_message(
                    chat_id,
                    "Привет, я твоя Подружка. Можешь рассказать мне всё, что у тебя на душе. Я рядом, выслушаю, пойму",
                    [["Закончить разговор"]],
                )

                session.state = "podruzhka_chat" if user.subscription == "paid" else "podruzhka_free"

            case "💎 Подписка" | "Получить доступ":
                self.show_subscription_menu(chat_id)
                session.state = "subscription_menu"

            case "ℹ️ Помощь":
                self.tg.send_message(
                    chat_id,
                    "Я помогу:\n• Сформулировать вопрос к Таро\n• Сделать базовый расклад (3 карты бесплатно) или глубокий расклад (7 карт для подписчиков)\n\n"
                    "Просто выбери «🃏 Расклад Таро» и следуй подсказкам.",
                )

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
            "Напиши свой вопрос или нажми «Другой вопрос» для свободного ввода."
        )
        self.tg.send_message(
            chat_id,
            suggest,
            [["Задать вопрос"], ["Назад в меню"]],
        )

        session.state = "taro_ask_question"

    def handle_taro_question(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Назад в меню":
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        cards = 7 if user.subscription == "paid" else 3

        if user.subscription != "paid":
            free_count = self.storage.count_taro_readings(chat_id=user.chat_id, cards_count=3)
            if free_count >= 1:
                self.tg.send_message(
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
                self.tg.send_message(
                    chat_id,
                    "Ты использовала все 10 платных раскладов на сегодня 🌸\n\n"
                    "Завтра сможешь продолжить или обратись к поддержке, если нужна расширенная сессия.",
                    [["Назад в меню"]],
                )
                session.state = "main_menu"
                return

        type_value = session.data.get("taro_type", "Расклад")
        prompt = self.build_taro_prompt(user.name or "Подруга", type_value, text, cards)

        self.tg.send_message(
            chat_id,
            "Сейчас я посоветуюсь с картами и соберу расклад — это займёт пару секунд ✨",
        )

        result = self.ask_ai(prompt)
        if not result:
            result = "К сожалению, сейчас я не могу подготовить расклад. Но не переживай — мы вернёмся к этому чуть позже."

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            f"Спасибо, {user.name}, что поделилась своим вопросом 🌸\n\n"
            f"<b>Вопрос:</b> {text}\n\n"
            f"<b>Расклад ({cards} карты):</b>\n"
            f"{result}\n\n"
            "Спасибо, что открываешься — если хочешь ещё углубиться, рассмотрим платную версию (7 карт и персональные рекомендации)."
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
            },
        )

        if user.subscription == "paid":
            self.tg.send_message(chat_id, final, [["Задать ещё вопрос", "Назад в меню"]])
            session.state = "taro_menu"
        else:
            final += "\n\nСпасибо, что доверилась. Если хочешь получать больше раскладов и персональные рекомендации — подключи подписку 💎"
            self.tg.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]])
            self.schedule_retention(user)
            session.state = "main_menu"

    def render_numerology_menu(self, chat_id: int, user: User) -> None:
        text = "Выбери формат нумерологического разбора:"
        keyboard = [["Бесплатно", "Полный анализ"], ["Назад в меню"]]
        self.tg.send_message(chat_id, text, keyboard)

    def show_horoscope_menu(self, chat_id: int, user: User) -> None:
        text = "Выбери формат гороскопа:"
        keyboard = [["Бесплатно", "Полный гороскоп"], ["Назад в меню"]]
        self.tg.send_message(chat_id, text, keyboard)

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
            self.tg.send_message(
                chat_id,
                "Спасибо, что доверилась мне. Помни: ты ценная и важная. Я всегда рядом, когда захочешь поговорить.",
            )
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if self.is_distress_message(text):
            self.tg.send_message(
                chat_id,
                "Если тебе очень тяжело, пожалуйста, обратись к специалисту. Я рядом, но живой человек — лучшее решение в таких ситуациях.",
                [["Закончить разговор"]],
            )
            return

        reply = self.ask_ai(text, self.build_podruzhka_system_prompt())
        if not reply:
            self.tg.send_message(
                chat_id,
                "Сейчас не получается ответить. Попробуй ещё раз чуть позже.",
                [["Назад в меню"]],
            )
            session.state = "main_menu"
            return

        if len(reply) > 300:
            reply = reply[:300] + "..."

        final = (
            reply
            + "\n\nСпасибо, что написала. Я рядом, даже когда трудно. 💗\n"
            + "Если хочешь продолжать беседу без ограничений и получать упражнения и поддержку в любой момент — подключи подписку."
        )

        self.tg.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]])
        user.podruzhka_free_used_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.schedule_retention(user)
        session.state = "main_menu"

    def handle_podruzhka_chat(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        if text == "Закончить разговор":
            self.tg.send_message(
                chat_id,
                "Спасибо, что доверилась мне. Помни: ты ценная и важная. Я всегда рядом, когда захочешь поговорить.",
            )
            self.show_main_menu(chat_id, user)
            session.state = "main_menu"
            return

        if self.is_distress_message(text):
            self.tg.send_message(
                chat_id,
                "Если тебе очень тяжело, пожалуйста, обратись к специалисту. Я рядом, но живой человек — лучшее решение в таких ситуациях.",
                [["Закончить разговор"]],
            )
            return

        reply = self.ask_ai(text, self.build_podruzhka_system_prompt())
        if not reply:
            self.tg.send_message(
                chat_id,
                "Сейчас не получается ответить. Давай попробуем позже.",
                [["Закончить разговор"]],
            )
            session.state = "podruzhka_chat"
            return

        if len(reply) > 4000:
            reply = reply[:4000] + "..."

        self.tg.send_message(chat_id, reply, [["Закончить разговор"]])
        session.state = "podruzhka_chat"

    def handle_numerology_free(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            used = self.storage.numerology_exists(chat_id=user.chat_id, type_value="money_code")
            if used:
                self.tg.send_message(
                    chat_id,
                    "Бесплатный расчёт уже доступен только один раз. Чтобы получить полный разбор, оформи подписку.",
                    [["Получить доступ", "Назад в меню"]],
                )
                session.state = "main_menu"
                return

        prompt = self.build_money_code_prompt(user.name or "", user.birth_date)
        self.tg.send_message(chat_id, "Считаю твой денежный код, подожди пару секунд ✨")
        result = self.ask_ai(prompt)

        if not result:
            result = "Сейчас не получается рассчитать код. Попробуй ещё раз позже."

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            result
            + "\n\nЭто твой денежный код. Он помогает понять, как ты взаимодействуешь с финансовыми потоками. 💸\n"
            + "Спасибо, что попробовала! Если хочешь узнать свои сильные стороны, кармические задачи и код активации изобилия, подключи подписку и получи расширенный нумерологический портрет. ✨"
        )

        self.tg.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]])
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
            },
        )
        session.state = "main_menu"

    def handle_numerology_paid(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            self.tg.send_message(
                chat_id,
                "Подробный нумерологический анализ доступен по подписке.",
                [["Получить доступ", "Назад в меню"]],
            )
            session.state = "numerology_menu"
            return

        birth = (
            datetime.strptime(user.birth_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            if user.birth_date
            else ""
        )
        prompt = self.build_numerology_prompt(user.name or "", user.surname or "", birth)
        self.tg.send_message(
            chat_id,
            "Собираю твою нумерологическую карту, подожди чуть-чуть ✨",
        )
        result = self.ask_ai(prompt)

        if not result:
            result = "Сейчас не получается подготовить анализ. Попробуй позже."

        if len(result) > 4000:
            result = result[:4000] + "..."

        self.tg.send_message(chat_id, result, [["Задать вопрос", "Назад в меню"]])

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
            },
        )

        session.state = "numerology_menu"

    def handle_horoscope_free(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            used = self.storage.horoscope_exists(chat_id=user.chat_id, type_value="daily")
            if used:
                self.tg.send_message(
                    chat_id,
                    "Ты уже получила краткий гороскоп. Чтобы узнать больше и получить полный прогноз, подключи подписку 🌌",
                    [["Получить доступ", "Назад в меню"]],
                )
                session.state = "main_menu"
                return

        sign = self.get_zodiac_sign(user.birth_date)
        prompt = self.build_horoscope_free_prompt(sign)
        self.tg.send_message(chat_id, "Смотрю твою астрологическую волну, подожди пару секунд ✨")
        result = self.ask_ai(prompt)

        if not result:
            result = "Сейчас не получается построить гороскоп. Попробуй позже."

        if len(result) > 4000:
            result = result[:4000] + "..."

        final = (
            f"Твой знак — {sign}.\n"
            f"{result}\n\n"
            "Это краткий взгляд на твою текущую астрологическую волну.\n"
            "Спасибо, что заглянула! Полный гороскоп по всем сферам жизни доступен по подписке: любовь, деньги, самореализация. 🌌"
        )

        self.tg.send_message(chat_id, final, [["Получить доступ", "Назад в меню"]])
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
            },
        )

        session.state = "main_menu"

    def handle_horoscope_paid(self, session: TgSession, user: User, chat_id: int) -> None:
        if user.subscription != "paid":
            self.tg.send_message(
                chat_id,
                "Полный гороскоп доступен по подписке.",
                [["Получить доступ", "Назад в меню"]],
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
        self.tg.send_message(
            chat_id,
            "Готовлю твой подробный гороскоп, подожди немного ✨",
        )
        result = self.ask_ai(prompt)

        if not result:
            result = "Сейчас не получается подготовить гороскоп. Попробуй позже."

        if len(result) > 4000:
            result = result[:4000] + "..."

        self.tg.send_message(chat_id, result, [["Назад в меню"]])

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
            "тепло, но всегда с уважением. Избегай клише и сухих фраз."
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

    def shorten(self, text: str, limit: int = 200) -> str:
        return text if len(text) <= limit else f"{text[:limit]}..."

    def show_subscription_menu(self, chat_id: int) -> None:
        text = "Выбери тариф подписки:"
        keyboard = [["1 месяц", "6 месяцев (-10%)"], ["12 месяцев (-10%)", "Назад в меню"]]
        self.tg.send_message(chat_id, text, keyboard)

    def route_subscription_menu(self, session: TgSession, user: User, chat_id: int, text: str) -> None:
        now = datetime.now()
        match text:
            case "1 месяц":
                user.subscription = "paid"
                user.subscription_expires_at = self._add_months(now, 1).strftime("%Y-%m-%d %H:%M:%S")
                self.tg.send_message(chat_id, "Подписка активирована на 1 месяц 💎")
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case "6 месяцев (-10%)":
                user.subscription = "paid"
                user.subscription_expires_at = self._add_months(now, 6).strftime("%Y-%m-%d %H:%M:%S")
                self.tg.send_message(chat_id, "Подписка активирована на 6 месяцев 💎")
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case "12 месяцев (-10%)":
                user.subscription = "paid"
                user.subscription_expires_at = self._add_months(now, 12).strftime("%Y-%m-%d %H:%M:%S")
                self.tg.send_message(chat_id, "Подписка активирована на 12 месяцев 💎")
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case "Назад в меню":
                self.show_main_menu(chat_id, user)
                session.state = "main_menu"
            case _:
                self.show_subscription_menu(chat_id)
                session.state = "subscription_menu"

    def schedule_retention(self, user: User) -> None:
        if self.storage.reminder_exists(user.chat_id):
            return

        messages = [
            (
                datetime.now() + timedelta(hours=6),
                "Спасибо, что провела день со мной. Если ты хочешь, чтобы я была рядом всегда — подключи подписку 💌",
            ),
            (
                datetime.now() + timedelta(hours=12),
                "Спасибо, что провела день со мной. Если ты хочешь, чтобы я была рядом всегда — подключи подписку 💌",
            ),
            (
                datetime.now() + timedelta(days=3),
                "Я всё ещё помню твой вопрос… Давай продолжим? Подписка активирует все разделы.",
            ),
        ]

        for send_at, message in messages:
            self.storage.create_reminder(user.chat_id, message, send_at)

    def ask_ai(self, prompt: str, system: str | None = None) -> str | None:
        try:
            return self.ai.get_answer(prompt, system)
        except Exception as exc:
            logging.warning("AI error: %s", exc)
            return None

    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)
