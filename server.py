from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "thunai.sqlite3"
MAX_BODY_BYTES = 16_000


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS check_ins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mood TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


class ThunaiHandler(BaseHTTPRequestHandler):
    server_version = "ThunaiLocal/1.0"

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY_BYTES:
            raise ValueError("Request must be between 1 byte and 16 KB.")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value

    def do_GET(self) -> None:
        if self.path == "/api/checkins":
            with sqlite3.connect(DB_PATH) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id, mood, note, created_at FROM check_ins "
                    "ORDER BY id DESC LIMIT 20"
                ).fetchall()
            self.send_json(200, {"checkins": [dict(row) for row in rows]})
            return

        relative = "index.html" if self.path in ("/", "/index.html") else self.path.lstrip("/")
        candidate = (ROOT / relative).resolve()
        if ROOT not in candidate.parents or not candidate.is_file():
            self.send_error(404)
            return

        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(candidate.suffix, "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            if self.path == "/api/checkins":
                mood = payload.get("mood")
                note = payload.get("note", "")
                if mood not in {"great", "okay", "low", "unwell"}:
                    self.send_json(400, {"error": "Choose a valid check-in mood."})
                    return
                if not isinstance(note, str) or len(note) > 500:
                    self.send_json(400, {"error": "Notes must be 500 characters or fewer."})
                    return
                with sqlite3.connect(DB_PATH) as connection:
                    cursor = connection.execute(
                        "INSERT INTO check_ins (mood, note) VALUES (?, ?)",
                        (mood, note.strip()),
                    )
                self.send_json(201, {"id": cursor.lastrowid, "saved": True})
                return

            if self.path == "/api/chat":
                messages = payload.get("messages")
                if not isinstance(messages, list) or not messages or len(messages) > 10:
                    self.send_json(400, {"error": "Please send a message under 4,000 characters."})
                    return
                conversation = []
                for item in messages:
                    if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                        self.send_json(400, {"error": "Conversation contains an invalid message."})
                        return
                    content = item.get("content")
                    if not isinstance(content, str) or not content.strip() or len(content) > 4_000:
                        self.send_json(400, {"error": "Please send a message under 4,000 characters."})
                        return
                    conversation.append({"role": item["role"], "content": content.strip()})
                if conversation[-1]["role"] != "user":
                    self.send_json(400, {"error": "The last conversation message must be from you."})
                    return
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    self.send_json(503, {"error": "GPT is not configured yet. Add OPENAI_API_KEY to your environment and restart Thunai."})
                    return

                request_body = {
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are Thunai, a warm and respectful companion for an older adult. "
                                "Use short, clear sentences and one question at a time. Never diagnose, "
                                "prescribe, or replace a clinician. If the person describes immediate "
                                "danger or a medical emergency, tell them to contact local emergency "
                                "services and a trusted person now. Do not claim you have contacted anyone."
                            ),
                        },
                    ] + conversation,
                    "max_tokens": 350,
                    "temperature": 0.6,
                }
                request = Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=json.dumps(request_body).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urlopen(request, timeout=30) as response:
                        result = json.loads(response.read())
                except HTTPError as error:
                    self.send_json(502, {"error": f"GPT request failed ({error.code}). Please try again."})
                    return
                except (URLError, TimeoutError):
                    self.send_json(502, {"error": "Could not reach GPT. Check the connection and try again."})
                    return

                answer = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                self.send_json(200, {"reply": answer})
                return

            self.send_json(404, {"error": "Not found."})
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


if __name__ == "__main__":
    init_db()
    host = os.environ.get("THUNAI_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Thunai is running at http://{host}:{port}")
    ThreadingHTTPServer((host, port), ThunaiHandler).serve_forever()
