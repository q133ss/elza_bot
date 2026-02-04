# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta
import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request, session, url_for

from storage import Storage


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

    if not admin_token:
        raise ValueError("ADMIN_TOKEN is required for admin panel")

    app = Flask(__name__)
    app.secret_key = admin_secret
    storage = Storage(db_path)

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
                <a href="{{ url_for('settings') }}">Настройки</a>
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

        if request.method == "POST":
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
        return render_page("Пользователь", body, user=user, messages=messages)

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

    return app


if __name__ == "__main__":
    load_dotenv()
    host = _env("ADMIN_HOST", "127.0.0.1")
    port = _env_int("ADMIN_PORT", 8080)
    app = create_app()
    app.run(host=host, port=port, debug=False)
