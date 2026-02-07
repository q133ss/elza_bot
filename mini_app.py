# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, render_template_string


TEMPLATE = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="color-scheme" content="light" />
    <title>Таро-бот</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
      :root {
        --bg-1: #f1eee7;
        --bg-2: #f8f4ff;
        --ink: #1b1a18;
        --muted: #5d5954;
        --accent: #b04b2f;
        --accent-2: #355da7;
        --card: rgba(255, 255, 255, 0.86);
        --border: rgba(40, 34, 28, 0.12);
        --glow: rgba(176, 75, 47, 0.18);
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        font-family: "Cormorant Garamond", "Times New Roman", serif;
        color: var(--ink);
        background: radial-gradient(circle at top, rgba(176, 75, 47, 0.18), transparent 60%),
          radial-gradient(circle at 20% 20%, rgba(53, 93, 167, 0.18), transparent 50%),
          linear-gradient(140deg, var(--bg-1), var(--bg-2));
        min-height: 100vh;
      }

      .page {
        padding: 20px 20px 28px;
        max-width: 880px;
        margin: 0 auto;
      }

      .header {
        display: grid;
        grid-template-columns: 64px 1fr;
        gap: 16px;
        align-items: center;
        background: var(--card);
        border-radius: 22px;
        border: 1px solid var(--border);
        padding: 16px 18px;
        box-shadow: 0 12px 32px rgba(30, 24, 18, 0.12);
        backdrop-filter: blur(8px);
      }

      .avatar {
        width: 64px;
        height: 64px;
        border-radius: 18px;
        background: linear-gradient(150deg, #f4d7c6, #d7defa);
        display: grid;
        place-items: center;
        font-family: "Manrope", "Segoe UI", sans-serif;
        font-size: 22px;
        font-weight: 700;
        color: #3c2a21;
        overflow: hidden;
        border: 1px solid rgba(0, 0, 0, 0.08);
      }

      .avatar img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .greeting h1 {
        margin: 0;
        font-weight: 600;
        font-size: 24px;
      }

      .greeting p {
        margin: 6px 0 0;
        font-family: "Manrope", "Segoe UI", sans-serif;
        color: var(--muted);
        font-size: 14px;
        letter-spacing: 0.01em;
      }

      .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-family: "Manrope", "Segoe UI", sans-serif;
        font-size: 12px;
        color: #2c2c2c;
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 6px 10px;
        margin-top: 10px;
      }

      .badge span {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #2f9e61;
        box-shadow: 0 0 8px rgba(47, 158, 97, 0.6);
      }

      .panel {
        margin-top: 22px;
        background: var(--card);
        border-radius: 24px;
        border: 1px solid var(--border);
        padding: 18px;
        box-shadow: 0 20px 40px rgba(40, 30, 20, 0.1);
      }

      .panel h2 {
        margin: 0 0 6px;
        font-size: 20px;
        font-weight: 600;
      }

      .panel p {
        margin: 0;
        font-family: "Manrope", "Segoe UI", sans-serif;
        color: var(--muted);
        font-size: 14px;
      }

      .menu {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
        margin-top: 18px;
      }

      .menu button {
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 16px 18px;
        background: #fff;
        text-align: left;
        font-family: "Manrope", "Segoe UI", sans-serif;
        font-size: 15px;
        cursor: default;
        box-shadow: 0 12px 20px rgba(25, 18, 12, 0.08);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
      }

      .menu button:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 24px rgba(25, 18, 12, 0.12);
      }

      .menu span {
        display: block;
        font-size: 12px;
        color: var(--muted);
        margin-top: 6px;
      }

      .footer {
        margin-top: 22px;
        font-family: "Manrope", "Segoe UI", sans-serif;
        font-size: 12px;
        color: var(--muted);
        text-align: center;
      }

      @media (max-width: 560px) {
        .header {
          grid-template-columns: 52px 1fr;
          padding: 14px;
        }
        .avatar {
          width: 52px;
          height: 52px;
          border-radius: 14px;
        }
        .greeting h1 {
          font-size: 20px;
        }
      }
    </style>
  </head>
  <body>
    <div class="page">
      <section class="header">
        <div class="avatar" id="avatar">Ю</div>
        <div class="greeting">
          <h1 id="greeting">Добрый день, Юля.</h1>
          <p id="subtitle">О чем сегодня поговорим?</p>
          <div class="badge"><span></span>Аккаунт подключен</div>
        </div>
      </section>

      <section class="panel">
        <h2>Меню</h2>
        <p>Выбери направление — пока это красивые заглушки, клики ничего не делают.</p>
        <div class="menu">
          <button type="button">🃏 Расклад Таро<span>Быстрый расклад под запрос</span></button>
          <button type="button">🃏 Режим таролога<span>Глубокий диалог и расклады</span></button>
          <button type="button">🔢 Нумерология<span>Числа судьбы и энергии</span></button>
          <button type="button">♒ Гороскоп<span>Твой день в звездной оптике</span></button>
          <button type="button">💬 Подружка<span>Теплый разговор без фильтров</span></button>
          <button type="button">💎 Подписка<span>Доступ к расширенным режимам</span></button>
          <button type="button">ℹ️ Помощь<span>Поддержка и FAQ</span></button>
        </div>
      </section>

      <div class="footer" id="user-meta">Подключаем тебя...</div>
    </div>

    <script>
      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
      }

      const greetingEl = document.getElementById("greeting");
      const subtitleEl = document.getElementById("subtitle");
      const avatarEl = document.getElementById("avatar");
      const metaEl = document.getElementById("user-meta");

      const now = new Date();
      const hour = now.getHours();
      let hello = "Добрый день";
      if (hour < 6) hello = "Доброй ночи";
      else if (hour < 12) hello = "Доброе утро";
      else if (hour < 18) hello = "Добрый день";
      else hello = "Добрый вечер";

      let name = "друг";
      let userMeta = "";
      const user = tg?.initDataUnsafe?.user;
      if (user) {
        name = user.first_name || user.username || name;
        userMeta = `@${user.username || "без_юзернейма"} · id ${user.id}`;
        if (user.photo_url) {
          const img = document.createElement("img");
          img.src = user.photo_url;
          img.alt = name;
          avatarEl.textContent = "";
          avatarEl.appendChild(img);
        } else if (name) {
          avatarEl.textContent = name.charAt(0).toUpperCase();
        }
      }

      greetingEl.textContent = `${hello}, ${name}.`;
      subtitleEl.textContent = "О чем сегодня поговорим?";
      metaEl.textContent = userMeta ? `Подключено как ${userMeta}` : "Открой мини-приложение из Telegram, чтобы привязать аккаунт.";
    </script>
  </body>
</html>
"""


def create_app() -> Flask:
    load_dotenv()
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template_string(TEMPLATE)

    return app


if __name__ == "__main__":
    load_dotenv()
    host = os.getenv("MINI_APP_HOST", "127.0.0.1")
    port = int(os.getenv("MINI_APP_PORT", "8090"))
    create_app().run(host=host, port=port)
