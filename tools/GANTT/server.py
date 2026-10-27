#!/usr/bin/env python3
"""Local editor for tools/GANTT/roadmap.yaml.

    python tools/GANTT/server.py

Then open the printed address. Edits write the YAML file.
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from roadmap_io import RoadmapError, add_task, load_roadmap, save_roadmap, update_task, view_roadmap

HERE = Path(__file__).resolve().parent
HTML_PATH = HERE / "web" / "index.html"
BOOT_LINE = "const BOOT = null;"


def json_for_script(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False)
    return (
        text.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_page(view: dict) -> bytes:
    template = HTML_PATH.read_text(encoding="utf-8")
    if BOOT_LINE not in template:
        raise RoadmapError("The page template is missing its data placeholder", 500)
    page = template.replace(BOOT_LINE, "const BOOT = " + json_for_script(view) + ";", 1)
    return page.encode("utf-8")


def handler_factory(roadmap_path: Path, today: date | None = None):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/favicon.ico":
                self._send(204, b"", "text/plain")
                return
            try:
                if path == "/":
                    with lock:
                        view = view_roadmap(load_roadmap(roadmap_path), today)
                    self._send(200, render_page(view), "text/html; charset=utf-8")
                    return
                if path == "/api/roadmap":
                    with lock:
                        view = view_roadmap(load_roadmap(roadmap_path), today)
                    self._send_json(200, view)
                    return
            except RoadmapError as exc:
                self._send_json(exc.status, {"error": str(exc)})
                return
            self._send_json(404, {"error": "Not found"})

        def do_POST(self):
            if not self._drain():
                return
            match = re.fullmatch(r"/api/epics/([^/]+)/tasks", urlparse(self.path).path)
            if not match:
                self._send_json(404, {"error": "Not found"})
                return
            self._mutate(lambda data: add_task(data, unquote(match.group(1))))

        def do_PATCH(self):
            match = re.fullmatch(r"/api/items/([^/]+)", urlparse(self.path).path)
            if not match:
                self._send_json(404, {"error": "Not found"})
                return
            item_id = unquote(match.group(1))
            try:
                fields = self._read_json()
            except RoadmapError as exc:
                self._send_json(exc.status, {"error": str(exc)})
                return
            self._mutate(lambda data: update_task(data, item_id, fields))

        def _mutate(self, change):
            try:
                with lock:
                    data = load_roadmap(roadmap_path)
                    change(data)
                    save_roadmap(roadmap_path, data)
                    view = view_roadmap(data, today)
            except RoadmapError as exc:
                self._send_json(exc.status, {"error": str(exc)})
                return
            self._send_json(200, view)

        def _drain(self) -> bool:
            length = self.headers.get("Content-Length")
            if not length:
                return True
            try:
                size = int(length)
            except ValueError:
                self._send_json(400, {"error": "Content-Length is invalid"})
                return False
            if size > 1_000_000:
                self.close_connection = True
                self._send_json(413, {"error": "Request is too large"})
                return False
            if size > 0:
                self.rfile.read(size)
            return True

        def _read_json(self) -> dict:
            length = self.headers.get("Content-Length")
            if length is None:
                raise RoadmapError("Request body is missing")
            try:
                size = int(length)
            except ValueError as exc:
                raise RoadmapError("Content-Length is invalid") from exc
            if size > 1_000_000:
                raise RoadmapError("Request is too large", 413)
            raw = self.rfile.read(size)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RoadmapError("Body is not JSON") from exc
            if not isinstance(body, dict):
                raise RoadmapError("Body must be an object")
            return body

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            print("%s - %s" % (self.log_date_time_string(), fmt % args))

    return Handler


def serve(path: Path, host: str, port: int) -> None:
    if not path.exists():
        raise SystemExit(f"Roadmap file not found: {path}")
    if not HTML_PATH.exists():
        raise SystemExit(f"Page not found: {HTML_PATH}")
    load_roadmap(path)
    httpd = ThreadingHTTPServer((host, port), handler_factory(path))
    print(f"Roadmap editor  http://{host}:{port}", flush=True)
    print(f"Saving {path}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit the Cool Spine roadmap in a browser")
    parser.add_argument("--file", type=Path, default=HERE / "roadmap.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.file, args.host, args.port)


if __name__ == "__main__":
    main()
