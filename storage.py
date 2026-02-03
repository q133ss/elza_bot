from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3
import threading
from typing import Any, Iterable


@dataclass
class User:
    chat_id: int
    name: str | None = None
    surname: str | None = None
    birth_date: str | None = None
    birth_time: str | None = None
    subscription: str | None = None
    subscription_expires_at: str | None = None
    podruzhka_free_used_at: str | None = None


@dataclass
class TgSession:
    chat_id: int
    state: str
    data: dict[str, Any]


@dataclass
class Reminder:
    id: int
    chat_id: int
    message: str
    send_at: str


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            name TEXT,
            surname TEXT,
            birth_date TEXT,
            birth_time TEXT,
            subscription TEXT,
            subscription_expires_at TEXT,
            podruzhka_free_used_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tg_sessions (
            chat_id INTEGER PRIMARY KEY,
            state TEXT NOT NULL,
            data TEXT
        );

        CREATE TABLE IF NOT EXISTS taro_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_name TEXT,
            birth_date TEXT,
            type TEXT,
            question TEXT,
            cards_count INTEGER,
            result TEXT,
            meta TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS numerology_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_name TEXT,
            surname TEXT,
            birth_date TEXT,
            type TEXT,
            result TEXT,
            meta TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS horoscope_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_name TEXT,
            surname TEXT,
            birth_date TEXT,
            birth_time TEXT,
            sign TEXT,
            type TEXT,
            result TEXT,
            meta TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            send_at TEXT NOT NULL,
            sent_at TEXT
        );
        """
        with self._lock:
            self._conn.executescript(schema)
            self._conn.commit()

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchone()

    def _query_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def _json_dumps(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _json_loads(data: str | None) -> dict[str, Any]:
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}

    def get_or_create_user(self, chat_id: int) -> User:
        row = self._query_one("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
        if row:
            return self._row_to_user(row)

        self._execute("INSERT INTO users (chat_id) VALUES (?)", (chat_id,))
        return User(chat_id=chat_id)

    def save_user(self, user: User) -> None:
        self._execute(
            """
            UPDATE users
            SET name = ?, surname = ?, birth_date = ?, birth_time = ?,
                subscription = ?, subscription_expires_at = ?, podruzhka_free_used_at = ?
            WHERE chat_id = ?
            """,
            (
                user.name,
                user.surname,
                user.birth_date,
                user.birth_time,
                user.subscription,
                user.subscription_expires_at,
                user.podruzhka_free_used_at,
                user.chat_id,
            ),
        )

    def get_or_create_session(self, chat_id: int) -> TgSession:
        row = self._query_one("SELECT * FROM tg_sessions WHERE chat_id = ?", (chat_id,))
        if row:
            return self._row_to_session(row)

        self._execute(
            "INSERT INTO tg_sessions (chat_id, state, data) VALUES (?, ?, ?)",
            (chat_id, "start", self._json_dumps({})),
        )
        return TgSession(chat_id=chat_id, state="start", data={})

    def save_session(self, session: TgSession) -> None:
        self._execute(
            "UPDATE tg_sessions SET state = ?, data = ? WHERE chat_id = ?",
            (session.state, self._json_dumps(session.data), session.chat_id),
        )

    def count_taro_readings(self, chat_id: int, cards_count: int) -> int:
        row = self._query_one(
            "SELECT COUNT(*) AS cnt FROM taro_readings WHERE chat_id = ? AND cards_count = ?",
            (chat_id, cards_count),
        )
        return int(row["cnt"]) if row else 0

    def count_taro_readings_for_date(self, chat_id: int, cards_count: int, date_value: str) -> int:
        row = self._query_one(
            """
            SELECT COUNT(*) AS cnt
            FROM taro_readings
            WHERE chat_id = ? AND cards_count = ? AND date(created_at) = date(?)
            """,
            (chat_id, cards_count, date_value),
        )
        return int(row["cnt"]) if row else 0

    def numerology_exists(self, chat_id: int, type_value: str) -> bool:
        row = self._query_one(
            "SELECT 1 FROM numerology_readings WHERE chat_id = ? AND type = ? LIMIT 1",
            (chat_id, type_value),
        )
        return row is not None

    def horoscope_exists(self, chat_id: int, type_value: str) -> bool:
        row = self._query_one(
            "SELECT 1 FROM horoscope_readings WHERE chat_id = ? AND type = ? LIMIT 1",
            (chat_id, type_value),
        )
        return row is not None

    def create_taro_reading(
        self,
        *,
        chat_id: int,
        user_name: str | None,
        birth_date: str | None,
        type_value: str,
        question: str,
        cards_count: int,
        result: str,
        meta: dict[str, Any],
    ) -> None:
        self._execute(
            """
            INSERT INTO taro_readings
                (chat_id, user_name, birth_date, type, question, cards_count, result, meta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                user_name,
                birth_date,
                type_value,
                question,
                cards_count,
                result,
                self._json_dumps(meta),
                self._now_str(),
            ),
        )

    def create_numerology_reading(
        self,
        *,
        chat_id: int,
        user_name: str | None,
        surname: str | None,
        birth_date: str | None,
        type_value: str,
        result: str,
        meta: dict[str, Any],
    ) -> None:
        self._execute(
            """
            INSERT INTO numerology_readings
                (chat_id, user_name, surname, birth_date, type, result, meta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                user_name,
                surname,
                birth_date,
                type_value,
                result,
                self._json_dumps(meta),
                self._now_str(),
            ),
        )

    def create_horoscope_reading(
        self,
        *,
        chat_id: int,
        user_name: str | None,
        surname: str | None,
        birth_date: str | None,
        birth_time: str | None,
        sign: str,
        type_value: str,
        result: str,
        meta: dict[str, Any],
    ) -> None:
        self._execute(
            """
            INSERT INTO horoscope_readings
                (chat_id, user_name, surname, birth_date, birth_time, sign, type, result, meta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                user_name,
                surname,
                birth_date,
                birth_time,
                sign,
                type_value,
                result,
                self._json_dumps(meta),
                self._now_str(),
            ),
        )

    def reminder_exists(self, chat_id: int) -> bool:
        row = self._query_one("SELECT 1 FROM reminders WHERE chat_id = ? LIMIT 1", (chat_id,))
        return row is not None

    def create_reminder(self, chat_id: int, message: str, send_at: datetime) -> None:
        self._execute(
            "INSERT INTO reminders (chat_id, message, send_at) VALUES (?, ?, ?)",
            (chat_id, message, send_at.strftime("%Y-%m-%d %H:%M:%S")),
        )

    def get_due_reminders(self, now: datetime) -> list[Reminder]:
        rows = self._query_all(
            """
            SELECT id, chat_id, message, send_at
            FROM reminders
            WHERE sent_at IS NULL AND datetime(send_at) <= datetime(?)
            """,
            (now.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        return [Reminder(id=row["id"], chat_id=row["chat_id"], message=row["message"], send_at=row["send_at"]) for row in rows]

    def mark_reminder_sent(self, reminder_id: int) -> None:
        self._execute(
            "UPDATE reminders SET sent_at = ? WHERE id = ?",
            (self._now_str(), reminder_id),
        )

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            chat_id=row["chat_id"],
            name=row["name"],
            surname=row["surname"],
            birth_date=row["birth_date"],
            birth_time=row["birth_time"],
            subscription=row["subscription"],
            subscription_expires_at=row["subscription_expires_at"],
            podruzhka_free_used_at=row["podruzhka_free_used_at"],
        )

    def _row_to_session(self, row: sqlite3.Row) -> TgSession:
        return TgSession(
            chat_id=row["chat_id"],
            state=row["state"],
            data=self._json_loads(row["data"]),
        )

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
