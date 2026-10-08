import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import app
from ollama_client import DEFAULT_MODEL, OllamaError, ask, request_json


class ClientTests(unittest.TestCase):
    def test_empty_prompt_never_reaches_model(self):
        with patch("ollama_client.request_json") as request:
            with self.assertRaises(ValueError):
                ask("   ")
            request.assert_not_called()

    def test_unknown_or_cloud_model_is_rejected(self):
        with patch("ollama_client.request_json", return_value={"models": [{"name": "cloud", "remote_host": "https://example.com"}]}):
            for model in ("missing", "cloud"):
                with self.subTest(model=model), self.assertRaises(ValueError):
                    ask("Привет", model)

    def test_empty_answer_is_not_success(self):
        with patch("ollama_client.request_json", side_effect=[{"models": [{"name": DEFAULT_MODEL}]}, {"done": True, "message": {"content": ""}}]):
            with self.assertRaises(OllamaError):
                ask("Привет")

    def test_truncation_is_visible_and_answer_preserved(self):
        raw = {"done": True, "done_reason": "length", "message": {"content": "Частичный ответ"}, "eval_count": 10, "eval_duration": 2_000_000_000}
        with patch("ollama_client.request_json", side_effect=[{"models": [{"name": DEFAULT_MODEL}]}, raw]):
            result = ask("Привет")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["answer"], "Частичный ответ")
        self.assertEqual(result["tokens_per_second"], 5)

    def test_unreachable_ollama_has_actionable_error(self):
        with patch("ollama_client.build_opener") as opener:
            opener.return_value.open.side_effect = URLError("refused")
            with self.assertRaisesRegex(OllamaError, "ollama serve"):
                request_json("/api/tags")


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, payload, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        return self.opener.open(Request(self.base + "/api/chat", data=payload, headers=headers), timeout=5)

    def test_invalid_json_and_cross_origin_never_call_model(self):
        with patch("app.ask") as model:
            for body, origin, expected in [(b"{", None, 400), (b"[]", None, 400), (b"{}", "https://example.com", 403)]:
                with self.subTest(body=body, origin=origin), self.assertRaises(HTTPError) as raised:
                    self.post(body, origin)
                self.assertEqual(raised.exception.code, expected)
            model.assert_not_called()

    def test_busy_model_returns_conflict(self):
        app.GENERATION_LOCK.acquire()
        try:
            with self.assertRaises(HTTPError) as raised:
                self.post(b'{"prompt":"hello"}')
            self.assertEqual(raised.exception.code, 409)
        finally:
            app.GENERATION_LOCK.release()

    def test_failure_releases_generation_lock_for_retry(self):
        with patch("app.ask", side_effect=[OllamaError("unavailable"), {"answer": "Привет"}]):
            with self.assertRaises(HTTPError) as raised:
                self.post(b'{"prompt":"hello"}')
            self.assertEqual(raised.exception.code, 502)
            with self.post(b'{"prompt":"hello"}') as response:
                self.assertEqual(json.load(response)["answer"], "Привет")


if __name__ == "__main__":
    unittest.main()
