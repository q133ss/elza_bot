# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta
import os
import time
from typing import Any

from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request, session, url_for

from storage import Storage
from services.tg_service import TgService


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def create_app() -> Flask:
    load_dotenv()

    db_path = _env("DATABASE_PATH", os.path.join("data", "taro.db"))
    admin_token = _env("ADMIN_TOKEN")
    admin_secret = _env("ADMIN_SECRET_KEY", "change-me")
    telegram_token = _env("TELEGRAM_BOT_TOKEN")
    telegram_timeout = _env_int("TELEGRAM_TIMEOUT", 20)

    if not admin_token:
        raise ValueError("ADMIN_TOKEN is required for admin panel")

    app = Flask(__name__)
    app.secret_key = admin_secret
    storage = Storage(db_path)
    tg = TgService(telegram_token, timeout=telegram_timeout) if telegram_token else None

    def require_admin() -> bool:
        return session.get("admin") is True

    def login_required() -> Any:
        if require_admin():
            return None
        return redirect(url_for("login", next=request.path))

    def _month_range(value: datetime) -> tuple[datetime, datetime]:
        start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end

    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value if value else None

    def render_page(title: str, body: str, **context: Any) -> str:
        template = """
        <!doctype html>
        <html lang="ru">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>{{ title }}</title>
            <style>
              :root {
                --bg: #f7f4ef;
                --panel: #ffffff;
                --ink: #1c1b1a;
                --muted: #6b6460;
                --accent: #c56a3a;
                --border: #e8e0d8;
              }
              * { box-sizing: border-box; }
              body {
                margin: 0;
                font-family: "Georgia", "Times New Roman", serif;
                background: var(--bg);
                color: var(--ink);
              }
              header {
                background: var(--panel);
                border-bottom: 1px solid var(--border);
                padding: 16px 24px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
              }
              header nav a {
                margin-right: 16px;
                text-decoration: none;
                color: var(--ink);
                font-weight: 600;
              }
              header nav a:last-child { margin-right: 0; }
              main { padding: 24px; max-width: 1200px; margin: 0 auto; }
              .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
              .card {
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 16px;
              }
              .muted { color: var(--muted); font-size: 14px; }
              table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--border); }
              th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
              th { background: #fbf8f4; font-size: 14px; }
              form .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
              input, select, textarea {
                width: 100%;
                padding: 8px 10px;
                border: 1px solid var(--border);
                border-radius: 8px;
                background: #fff;
                font-family: inherit;
              }
              button {
                padding: 8px 14px;
                border: none;
                border-radius: 8px;
                background: var(--accent);
                color: white;
                cursor: pointer;
                font-weight: 600;
              }
              .actions { display: flex; gap: 8px; flex-wrap: wrap; }
              .message {
                border: 1px solid var(--border);
                background: var(--panel);
                border-radius: 10px;
                padding: 10px;
                margin-bottom: 10px;
              }
              .message .meta { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
              .badge {
                display: inline-block;
                padding: 2px 8px;
                border-radius: 999px;
                background: #f2e7dc;
                color: #6a3b22;
                font-size: 12px;
              }
            </style>
          </head>
          <body>
            <header>
              <div><strong>Admin Panel</strong></div>
              <nav>
                <a href="{{ url_for('dashboard') }}">Главная</a>
                <a href="{{ url_for('users') }}">Пользователи</a>
                <a href="{{ url_for('support') }}">Поддержка</a>
                <a href="{{ url_for('settings') }}">Настройки</a>
                <a href="{{ url_for('broadcast') }}">Рассылка</a>
                <a href="{{ url_for('logout') }}">Выход</a>
              </nav>
            </header>
            <main>
              {{ body|safe }}
            </main>
          </body>
        </html>
        """
        rendered_body = render_template_string(body, **context)
        return render_template_string(template, title=title, body=rendered_body, **context)

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str:
        if request.method == "POST":
            token = request.form.get("token", "")
            if token == admin_token:
                session["admin"] = True
                next_url = request.args.get("next") or url_for("dashboard")
                return redirect(next_url)

        body = """
        <h1>Вход</h1>
        <form method="post">
          <div style="max-width: 320px;">
            <label class="muted">Токен администратора</label>
            <input type="password" name="token" required />
            <div style="margin-top: 12px;">
              <button type="submit">Войти</button>
            </div>
          </div>
        </form>
        """
        return render_page("Вход", body)

    @app.route("/logout")
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def dashboard() -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        now = datetime.now()
        start, end = _month_range(now)
        total_users = storage.count_users()
        new_users = storage.count_new_users_between(start, end)
        tokens = storage.sum_tokens_between(start, end)
        active_subs = storage.count_active_subscriptions(now)
        paid_count, paid_amount = storage.payments_summary_between(start, end)

        body = """
        <h1>Главная</h1>
        <p class="muted">Период: {{ start.strftime('%d.%m.%Y') }} – {{ (end - timedelta(seconds=1)).strftime('%d.%m.%Y') }}</p>
        <div class="cards">
          <div class="card">
            <div class="muted">Всего пользователей</div>
            <div style="font-size: 28px;">{{ total_users }}</div>
          </div>
          <div class="card">
            <div class="muted">Новые пользователи (месяц)</div>
            <div style="font-size: 28px;">{{ new_users }}</div>
          </div>
          <div class="card">
            <div class="muted">Токены OpenAI (месяц)</div>
            <div style="font-size: 28px;">{{ tokens }}</div>
          </div>
          <div class="card">
            <div class="muted">Активные подписки</div>
            <div style="font-size: 28px;">{{ active_subs }}</div>
          </div>
          <div class="card">
            <div class="muted">Оплаты (месяц)</div>
            <div style="font-size: 28px;">{{ paid_count }}</div>
            <div class="muted">Сумма: {{ paid_amount }} ?</div>
          </div>
        </div>
        """
        return render_page(
            "Главная",
            body,
            start=start,
            end=end,
            total_users=total_users,
            new_users=new_users,
            tokens=tokens,
            active_subs=active_subs,
            paid_count=paid_count,
            paid_amount=paid_amount,
            timedelta=timedelta,
        )

    @app.route("/users")
    def users() -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        query = request.args.get("q") or ""
        users_list = storage.get_users(search=query or None, limit=300, offset=0)

        body = """
        <h1>Пользователи</h1>
        <form method="get" style="margin-bottom: 12px;">
          <div class="row">
            <div>
              <input type="text" name="q" placeholder="Поиск по chat_id или имени" value="{{ query }}" />
            </div>
            <div>
              <button type="submit">Найти</button>
            </div>
          </div>
        </form>
        <table>
          <thead>
            <tr>
              <th>Chat ID</th>
              <th>Имя</th>
              <th>Фамилия</th>
              <th>Подписка</th>
              <th>До</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
          {% for user in users_list %}
            <tr>
              <td>{{ user.chat_id }}</td>
              <td>{{ user.name or '-' }}</td>
              <td>{{ user.surname or '-' }}</td>
              <td>{{ user.subscription or 'free' }}</td>
              <td>{{ user.subscription_expires_at or '-' }}</td>
              <td><a href="{{ url_for('user_detail', chat_id=user.chat_id) }}">Детали</a></td>
            </tr>
          {% else %}
            <tr><td colspan="6">Нет данных</td></tr>
          {% endfor %}
          </tbody>
        </table>
        """
        return render_page("Пользователи", body, users_list=users_list, query=query)

    @app.route("/users/<int:chat_id>", methods=["GET", "POST"])
    def user_detail(chat_id: int) -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        user = storage.get_user(chat_id)
        if not user:
            return render_page("Пользователь", "<p>Пользователь не найден.</p>")

        admin_message_result = ""
        if request.method == "POST":
            admin_message = (request.form.get("admin_message") or "").strip()
            if admin_message:
                if not tg:
                    admin_message_result = "TELEGRAM_BOT_TOKEN не задан — отправка недоступна."
                else:
                    try:
                        tg.send_message(chat_id, admin_message)
                        storage.log_chat_message(
                            chat_id,
                            "assistant",
                            admin_message,
                            meta={"source": "admin_reply"},
                        )
                        admin_message_result = "Сообщение отправлено пользователю."
                    except Exception:
                        admin_message_result = "Не удалось отправить сообщение пользователю."
            else:
                user.name = _clean(request.form.get("name"))
                user.surname = _clean(request.form.get("surname"))
                user.birth_date = _clean(request.form.get("birth_date"))
                user.birth_time = _clean(request.form.get("birth_time"))
                user.subscription = _clean(request.form.get("subscription"))
                user.subscription_expires_at = _clean(request.form.get("subscription_expires_at"))
                user.podruzhka_free_used_at = _clean(request.form.get("podruzhka_free_used_at"))
                storage.save_user(user)

        limit = _env_int("ADMIN_DIALOG_LIMIT", 800)
        messages = storage.get_chat_messages(chat_id, limit=limit)

        body = """
        <h1>Пользователь {{ user.chat_id }}</h1>
        <div class="card" style="margin-bottom: 16px;">
          <form method="post">
            <div class="row">
              <div>
                <label class="muted">Имя</label>
                <input type="text" name="name" value="{{ user.name or '' }}" />
              </div>
              <div>
                <label class="muted">Фамилия</label>
                <input type="text" name="surname" value="{{ user.surname or '' }}" />
              </div>
              <div>
                <label class="muted">Дата рождения (YYYY-MM-DD)</label>
                <input type="text" name="birth_date" value="{{ user.birth_date or '' }}" />
              </div>
              <div>
                <label class="muted">Время рождения (HH:MM:SS)</label>
                <input type="text" name="birth_time" value="{{ user.birth_time or '' }}" />
              </div>
              <div>
                <label class="muted">Подписка</label>
                <select name="subscription">
                  <option value="" {% if not user.subscription %}selected{% endif %}>free</option>
                  <option value="paid" {% if user.subscription == 'paid' %}selected{% endif %}>paid</option>
                </select>
              </div>
              <div>
                <label class="muted">Подписка до (YYYY-MM-DD HH:MM:SS)</label>
                <input type="text" name="subscription_expires_at" value="{{ user.subscription_expires_at or '' }}" />
              </div>
              <div>
                <label class="muted">Podruzhka free used at</label>
                <input type="text" name="podruzhka_free_used_at" value="{{ user.podruzhka_free_used_at or '' }}" />
              </div>
            </div>
            <div style="margin-top: 12px;" class="actions">
              <button type="submit">Сохранить</button>
            </div>
          </form>
        </div>

        <div class="card" style="margin-bottom: 16px;">
          <h3>Ответить пользователю</h3>
          {% if admin_message_result %}
            <div class="muted" style="margin-bottom: 8px;">{{ admin_message_result }}</div>
          {% endif %}
          <form method="post">
            <textarea name="admin_message" rows="4" placeholder="Текст ответа" required></textarea>
            <div style="margin-top: 12px;" class="actions">
              <button type="submit">Отправить</button>
            </div>
          </form>
        </div>

        <h2>Диалог (последние {{ messages|length }})</h2>
        {% for msg in messages %}
          <div class="message">
            <div class="meta">
              <span class="badge">{{ msg['role'] }}</span>
              {{ msg['created_at'] }}
            </div>
            <div>{{ msg['content'] }}</div>
          </div>
        {% else %}
          <p>Сообщений нет.</p>
        {% endfor %}
        """
        return render_page(
            "Пользователь",
            body,
            user=user,
            messages=messages,
            admin_message_result=admin_message_result,
        )

    @app.route("/support")
    def support() -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        limit = _env_int("ADMIN_SUPPORT_LIMIT", 200)
        requests_list = storage.get_support_requests(limit=limit)

        body = """
        <h1>Поддержка</h1>
        <p class="muted">Заявки от пользователей. Чтобы ответить — открой пользователя и отправь сообщение в блоке «Ответить пользователю».</p>
        <table>
          <thead>
            <tr>
              <th>Chat ID</th>
              <th>Дата</th>
              <th>Сообщение</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
          {% for item in requests_list %}
            <tr>
              <td>{{ item.chat_id }}</td>
              <td>{{ item.created_at }}</td>
              <td>{{ item.content }}</td>
              <td><a href="{{ url_for('user_detail', chat_id=item.chat_id) }}">Открыть</a></td>
            </tr>
          {% else %}
            <tr><td colspan="4">Нет заявок</td></tr>
          {% endfor %}
          </tbody>
        </table>
        """
        return render_page("Поддержка", body, requests_list=requests_list)

    @app.route("/settings", methods=["GET", "POST"])
    def settings() -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        if request.method == "POST":
            price_value = request.form.get("subscription_price_rub", "")
            try:
                price_int = int(price_value)
                if price_int > 0:
                    storage.set_subscription_price_rub(price_int)
            except ValueError:
                pass

        current_price = storage.get_subscription_price_rub()
        body = """
        <h1>Настройки</h1>
        <div class="card" style="max-width: 420px;">
          <form method="post">
            <label class="muted">Цена подписки (1 месяц), ?</label>
            <input type="number" name="subscription_price_rub" value="{{ current_price }}" min="1" />
            <div style="margin-top: 12px;">
              <button type="submit">Сохранить</button>
            </div>
          </form>
        </div>
        """
        return render_page("Настройки", body, current_price=current_price)

    @app.route("/broadcast", methods=["GET", "POST"])
    def broadcast() -> Any:
        redirect_response = login_required()
        if redirect_response:
            return redirect_response

        result_message = ""
        recipients_preview: list[int] = []

        if request.method == "POST":
            if tg is None:
                result_message = "TELEGRAM_BOT_TOKEN не задан — рассылка недоступна."
            else:
                message = (request.form.get("message") or "").strip()
                mode = request.form.get("mode") or "all"
                subscription = request.form.get("subscription") or ""
                active_only = request.form.get("active_only") == "on"
                raw_ids = request.form.get("chat_ids") or ""
                dry_run = request.form.get("dry_run") == "on"
                max_recipients = request.form.get("max_recipients") or ""
                delay_ms = request.form.get("delay_ms") or ""

                limit_value = None
                if max_recipients.strip().isdigit():
                    limit_value = max(1, int(max_recipients))

                delay_value = 0.0
                if delay_ms.strip().isdigit():
                    delay_value = max(0, int(delay_ms)) / 1000.0

                if not message:
                    result_message = "Сообщение не может быть пустым."
                else:
                    recipients: list[int] = []
                    if mode == "ids":
                        tokens = [part.strip() for part in raw_ids.replace(",", " ").split()]
                        ids: list[int] = []
                        for token in tokens:
                            if token.isdigit():
                                ids.append(int(token))
                        recipients = list(dict.fromkeys(ids))
                    else:
                        sub_filter = None
                        if subscription in {"paid", "free"}:
                            sub_filter = subscription
                        recipients = storage.get_recipient_ids(
                            subscription=sub_filter,
                            active_only=active_only,
                            now=datetime.now(),
                            limit=limit_value,
                        )

                    recipients_preview = recipients[:10]

                    if dry_run:
                        result_message = f"Найдено получателей: {len(recipients)}."
                    else:
                        sent = 0
                        failed = 0
                        for chat_id in recipients:
                            try:
                                tg.send_message(chat_id, message)
                                storage.log_chat_message(
                                    chat_id,
                                    "assistant",
                                    message,
                                    meta={"source": "admin_broadcast"},
                                )
                                sent += 1
                            except Exception:
                                failed += 1
                            if delay_value > 0:
                                time.sleep(delay_value)

                        result_message = f"Отправлено: {sent}. Ошибок: {failed}."

        body = """
        <h1>Рассылка</h1>
        {% if result_message %}
          <div class="card" style="margin-bottom: 12px;">{{ result_message }}</div>
        {% endif %}
        {% if tg is none %}
          <div class="card" style="margin-bottom: 12px;">
            <strong>Внимание:</strong> переменная TELEGRAM_BOT_TOKEN не задана.
          </div>
        {% endif %}
        <form method="post">
          <div class="card" style="margin-bottom: 16px;">
            <label class="muted">Сообщение</label>
            <textarea name="message" rows="5" required>{{ request.form.get('message','') }}</textarea>
          </div>
          <div class="card" style="margin-bottom: 16px;">
            <div class="row">
              <div>
                <label class="muted">Кому отправить</label>
                <select name="mode">
                  <option value="all" {% if request.form.get('mode','all') == 'all' %}selected{% endif %}>Всем</option>
                  <option value="filter" {% if request.form.get('mode') == 'filter' %}selected{% endif %}>По фильтрам</option>
                  <option value="ids" {% if request.form.get('mode') == 'ids' %}selected{% endif %}>По chat_id</option>
                </select>
              </div>
              <div>
                <label class="muted">Подписка</label>
                <select name="subscription">
                  <option value="" {% if request.form.get('subscription','') == '' %}selected{% endif %}>Любая</option>
                  <option value="paid" {% if request.form.get('subscription') == 'paid' %}selected{% endif %}>Платные</option>
                  <option value="free" {% if request.form.get('subscription') == 'free' %}selected{% endif %}>Бесплатные</option>
                </select>
              </div>
              <div>
                <label class="muted">Только активные</label>
                <div><input type="checkbox" name="active_only" {% if request.form.get('active_only') %}checked{% endif %} /> активная подписка</div>
              </div>
              <div>
                <label class="muted">Лимит получателей</label>
                <input type="number" name="max_recipients" min="1" value="{{ request.form.get('max_recipients','') }}" />
              </div>
              <div>
                <label class="muted">Задержка (мс)</label>
                <input type="number" name="delay_ms" min="0" value="{{ request.form.get('delay_ms','50') }}" />
              </div>
            </div>
            <div style="margin-top: 12px;">
              <label class="muted">Chat ID (для режима "По chat_id")</label>
              <textarea name="chat_ids" rows="3" placeholder="12345 67890">{{ request.form.get('chat_ids','') }}</textarea>
            </div>
            <div style="margin-top: 12px;">
              <label><input type="checkbox" name="dry_run" {% if request.form.get('dry_run') %}checked{% endif %} /> Только проверить количество (без отправки)</label>
            </div>
          </div>
          <button type="submit">Отправить</button>
        </form>
        {% if recipients_preview %}
          <p class="muted">Пример получателей: {{ recipients_preview }}</p>
        {% endif %}
        """
        return render_page(
            "Рассылка",
            body,
            result_message=result_message,
            recipients_preview=recipients_preview,
            tg=tg,
            request=request,
        )

    return app


if __name__ == "__main__":
    load_dotenv()
    host = _env("ADMIN_HOST", "127.0.0.1")
    port = _env_int("ADMIN_PORT", 8080)
    app = create_app()
    app.run(host=host, port=port, debug=False)
