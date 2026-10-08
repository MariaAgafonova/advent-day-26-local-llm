"""Local web application and CLI. Python 3.10+, standard library only."""

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ollama_client import DEFAULT_MODEL, OllamaError, ask, status

ROOT = Path(__file__).resolve().parent
GENERATION_LOCK = threading.Lock()
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, value, content_type="application/json"):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8") if content_type == "application/json" else value
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if self.path in STATIC:
            filename, content_type = STATIC[self.path]
            return self.send(200, (ROOT / "static" / filename).read_bytes(), content_type)
        if self.path == "/api/status":
            try:
                return self.send(200, status())
            except OllamaError as exc:
                return self.send(503, {"error": str(exc)})
        self.send(404, {"error": "Страница не найдена."})

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send(404, {"error": "Страница не найдена."})
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in hosts:
            return self.send(403, {"error": "Недопустимый адрес сервера."})
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            return self.send(403, {"error": "Недопустимый источник запроса."})
        if self.headers.get_content_type() != "application/json":
            return self.send(415, {"error": "Требуется application/json."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                return self.send(413, {"error": "Недопустимый размер запроса."})
            self.connection.settimeout(10)
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Ожидается JSON-объект.")
        except (ValueError, UnicodeError, TimeoutError) as exc:
            return self.send(400, {"error": "Некорректный запрос: " + str(exc)})
        if not GENERATION_LOCK.acquire(blocking=False):
            return self.send(409, {"error": "Модель уже отвечает на запрос. Дождитесь завершения."})
        try:
            self.send(200, ask(data.get("prompt"), data.get("model", DEFAULT_MODEL)))
        except ValueError as exc:
            self.send(400, {"error": str(exc)})
        except OllamaError as exc:
            self.send(502, {"error": str(exc)})
        finally:
            GENERATION_LOCK.release()


def main():
    parser = argparse.ArgumentParser(description="День 26 — локальная LLM через Ollama API")
    parser.add_argument("--port", type=int, default=8526)
    parser.add_argument("--ask", help="Отправить один запрос из CLI вместо запуска интерфейса")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    if args.ask is not None:
        try:
            result = ask(args.ask, args.model)
        except (ValueError, OllamaError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(result["answer"])
        print(f"\n{result['model']} · {result['elapsed_seconds']} с · {result['output_tokens']} токенов")
        if result["truncated"]:
            print("Внимание: ответ достиг лимита 1024 токена.")
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"День 26: http://127.0.0.1:{args.port}  |  Ctrl+C — остановить", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
