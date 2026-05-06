"""
Purpose: Temporary local HTTP server to serve a processed LectureKit session JSON.

Use case:
- You already have a saved `/process` response at `/tmp/karpathy_micrograd_process.json`.
- This script exposes a lightweight endpoint at `http://127.0.0.1:9999/session` so you can
  load the session into browser localStorage without making any backend API calls.

Data flow:
browser DevTools -> fetch(http://127.0.0.1:9999/session) -> localStorage["lecturekit_session"] -> /study
"""

from __future__ import annotations

import http.server
import json
import socketserver
from typing import Any, Dict


def _load_session() -> Dict[str, Any]:
    """
    Load the saved `/process` response and project only the fields the frontend expects.
    """
    with open("/tmp/karpathy_micrograd_process.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "video_id": data["video_id"],
        "youtube_url": data["youtube_url"],
        "chunk_count": data["chunk_count"],
        "outline": data["outline"],
        "summary_90s": data["summary_90s"],
        "summary_5min": data["summary_5min"],
        "summary_full": data["summary_full"],
        "flashcards": data["flashcards"],
        "indexed": data["indexed"],
    }


class Handler(http.server.BaseHTTPRequestHandler):
    """
    Serve `GET /session` with JSON + permissive CORS.
    """

    def do_OPTIONS(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path.rstrip("/") != "/session":
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        session_json = json.dumps(_load_session(), ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(session_json)

    def log_message(self, _format: str, *_args: object) -> None:  # noqa: D401
        # Keep output clean; print only the startup line.
        return


def main() -> None:
    """
    Start the server on localhost:9999.
    """
    with socketserver.TCPServer(("127.0.0.1", 9999), Handler) as httpd:
        print("Serving on http://127.0.0.1:9999/session")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

