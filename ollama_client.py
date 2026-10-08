"""Dependency-free client for the local Ollama HTTP API."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
MAX_PROMPT_LENGTH = 8000
SYSTEM_PROMPT = "Отвечай на русском языке, ясно и по существу. Следуй формату из запроса."
EXAMPLES = [
    {
        "level": "Простой",
        "title": "Короткий вопрос",
        "prompt": "Как называется столица Сербии? Ответь одним предложением.",
    },
    {
        "level": "Средний",
        "title": "Задача в несколько шагов",
        "prompt": "В магазине 3 блокнота по 240 рублей и 2 ручки по 80 рублей. "
        "На всю покупку действует скидка 15%. Покупатель дал 1000 рублей. "
        "Рассчитай стоимость до скидки, сумму скидки, итоговую стоимость и сдачу. "
        "Покажи вычисления кратко.",
    },
    {
        "level": "Сложный",
        "title": "Код и граничные случаи",
        "prompt": "Напиши на Python функцию merge_intervals(intervals), которая объединяет "
        "пересекающиеся и соприкасающиеся закрытые интервалы. Вход — список пар целых "
        "чисел [start, end], где start <= end. Не изменяй исходный список. "
        "Обработай пустой список. Для [[1,3],[2,6],[8,10],[10,12]] результат должен "
        "быть [[1,6],[8,12]]. Дай код функции, 3 assert-проверки (обычный случай, "
        "пустой список, вложенные интервалы) и кратко оцени сложность. До 250 слов.",
    },
]


class OllamaError(RuntimeError):
    pass


def request_json(path, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(OLLAMA_URL + path, data=data, headers={"Content-Type": "application/json"})
    # Loopback traffic must not travel through a configured HTTP proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except (ValueError, AttributeError):
            pass
        raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise OllamaError(f"Ollama не ответила за {timeout} секунд. Попробуйте более короткий запрос или модель 4B.") from exc
    except (URLError, OSError) as exc:
        raise OllamaError("Ollama недоступна на 127.0.0.1:11434. Запустите Ollama или выполните ollama serve.") from exc
    except (ValueError, UnicodeError) as exc:
        raise OllamaError("Ollama вернула некорректный JSON.") from exc
    if not isinstance(result, dict):
        raise OllamaError("Ollama вернула неожиданный формат ответа.")
    if result.get("error"):
        raise OllamaError(str(result["error"]))
    return result


def local_models():
    return [m for m in request_json("/api/tags").get("models", []) if not m.get("remote_host")]


def status():
    return {
        "url": OLLAMA_URL,
        "version": request_json("/api/version")["version"],
        "models": local_models(),
        "default_model": DEFAULT_MODEL,
        "examples": EXAMPLES,
    }


def ask(prompt, model=DEFAULT_MODEL):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Введите запрос.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(f"Запрос должен быть не длиннее {MAX_PROMPT_LENGTH} символов.")
    if not isinstance(model, str) or model not in {m["name"] for m in local_models()}:
        raise ValueError("Выберите установленную локальную модель из списка.")
    start = time.perf_counter()
    raw = request_json(
        "/api/chat",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 1024},
        },
        timeout=300,
    )
    message = raw.get("message")
    answer = message.get("content") if isinstance(message, dict) else None
    if raw.get("done") is not True or not isinstance(answer, str) or not answer.strip():
        raise OllamaError("Модель не вернула завершённый непустой ответ. Попробуйте ещё раз.")
    duration = raw.get("eval_duration", 0) / 1_000_000_000
    tokens = raw.get("eval_count", 0)
    return {
        "model": raw.get("model", model),
        "prompt": prompt,
        "answer": answer.strip(),
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "output_tokens": tokens,
        "tokens_per_second": round(tokens / duration, 2) if duration else None,
        "truncated": raw.get("done_reason") == "length",
        "raw": raw,
    }
