# TaroBot
[English](#en)

## RU

**Описание**
Telegram-бот для эзотерики и самопознания с freemium-механикой, платной подпиской и админ-панелью. Сервис интегрируется с Telegram Bot API, OpenAI и YooKassa, хранит данные в SQLite и выполняет напоминания/проверки статусов оплат.

**Возможности**
- Таро-расклады и режим "таролога"
- Нумерология и гороскоп
- Диалоговый режим "подружка"
- Freemium-лимиты и подписка
- Платежи через YooKassa и проверка статусов
- Админ-панель (Flask) для просмотра метрик и переписки

**Стек**
- Python 3.x
- Telegram Bot API (long polling)
- OpenAI API
- YooKassa SDK
- Flask
- SQLite
- Requests, python-dotenv

**Запуск**
1. Установите зависимости:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
2. Скопируйте `.env.example` в `.env` и заполните переменные.
3. Запустите бота:
```bash
python bot.py
```
4. (Опционально) Админ-панель:
```bash
python admin_app.py
```

**Переменные окружения**
См. `.env.example`. Обязательные ключи:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `YOOKASSA_RETURN_URL`
- `ADMIN_TOKEN` (для админ-панели)

**Структура проекта**
- `bot.py` — главный цикл бота (polling) и напоминания
- `services/ai_service.py` — интеграция с OpenAI
- `services/tg_service.py` — Telegram API
- `services/payment_service.py` — YooKassa
- `services/chat_service.py` — логика диалога, сценарии и лимиты
- `storage.py` — SQLite-схема и доступ к данным
- `admin_app.py` — админ-панель (Flask)
- `data/` — база данных и служебные файлы

---

## EN

**Overview**
A Telegram bot for эзотерика/self-discovery with freemium limits, paid subscription, and an admin panel. It integrates Telegram Bot API, OpenAI, and YooKassa, stores data in SQLite, and runs reminders/payment status checks.

**Features**
- Tarot readings and “tarologist” mode
- Numerology and horoscope
- Chat companion mode
- Freemium limits + paid subscription
- YooKassa payments with status checks
- Admin panel (Flask) for metrics and chat logs

**Tech Stack**
- Python 3.x
- Telegram Bot API (long polling)
- OpenAI API
- YooKassa SDK
- Flask
- SQLite
- Requests, python-dotenv

**How to Run**
1. Install dependencies:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
2. Copy `.env.example` to `.env` and set variables.
3. Run the bot:
```bash
python bot.py
```
4. (Optional) Admin panel:
```bash
python admin_app.py
```

**Environment Variables**
See `.env.example`. Required:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `YOOKASSA_RETURN_URL`
- `ADMIN_TOKEN` (for admin panel)

**Project Structure**
- `bot.py` — main polling loop + reminders
- `services/ai_service.py` — OpenAI integration
- `services/tg_service.py` — Telegram API
- `services/payment_service.py` — YooKassa
- `services/chat_service.py` — dialogue flows, limits, scenarios
- `storage.py` — SQLite schema & data access
- `admin_app.py` — admin panel (Flask)
- `data/` — database and service files

