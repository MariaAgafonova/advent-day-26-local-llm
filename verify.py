"""Send three real requests through the application and save evidence."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from ollama_client import DEFAULT_MODEL, EXAMPLES, OLLAMA_URL, request_json


def main():
    parser = argparse.ArgumentParser(description="Проверка трёх запросов к локальной LLM")
    parser.add_argument("--port", type=int, default=8526)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    opener = build_opener(ProxyHandler({}))
    with opener.open(base_url + "/api/status", timeout=15) as response:
        state = json.load(response)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "application_url": base_url,
        "ollama_url": OLLAMA_URL,
        "ollama_version": state["version"],
        "model": args.model,
        "installed_models": state["models"],
        "results": [],
    }
    output = Path(__file__).resolve().parent / "output"
    output.mkdir(exist_ok=True)
    for index, example in enumerate(EXAMPLES, 1):
        print(f"[{index}/3] {example['level']}: {example['title']}…", flush=True)
        body = json.dumps({"model": args.model, "prompt": example["prompt"]}, ensure_ascii=False).encode("utf-8")
        request = Request(base_url + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=320) as response:
            result = json.load(response)
        if not result.get("answer") or not result.get("raw", {}).get("done") or result.get("truncated"):
            raise RuntimeError(f"Запрос {index}: ответ пуст, не завершён или обрезан.")
        report["results"].append({**example, **result})
        (output / "day26-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Ответ получен: {result['elapsed_seconds']} с, {result['output_tokens']} токенов", flush=True)
        print(result["answer"], flush=True)
    report["running_models"] = request_json("/api/ps").get("models", [])
    if not any(m["name"] == args.model for m in report["running_models"]):
        raise RuntimeError("После запросов модель отсутствует в списке запущенных моделей Ollama.")
    report["passed"] = True
    (output / "day26-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# День 26. Результаты запуска локальной LLM", "",
        f"Проверено (UTC): {report['checked_at_utc']}", "",
        f"- Ollama: **{report['ollama_version']}**.",
        f"- Модель: **{args.model}**.",
        f"- API модели: `{OLLAMA_URL}`; приложение: `{base_url}`.",
        "- Три реальных запроса прошли через HTTP API приложения и Ollama.",
        "- Получены непустые завершённые ответы без обрезания по лимиту токенов.",
        "- После запросов модель присутствует в `/api/ps` (загружена локально).", "",
        "| Сложность | Время, с | Токены ответа | Токенов/с |",
        "|---|---:|---:|---:|",
    ]
    for item in report["results"]:
        lines.append(f"| {item['level']} | {item['elapsed_seconds']} | {item['output_tokens']} | {item['tokens_per_second']} |")
    lines += ["", "Время запроса включает загрузку модели, если она ещё не находилась в памяти. "
              "Скорость в токенах/с рассчитана по времени генерации Ollama. "
              "Эта проверка подтверждает получение ответов; их смысловую корректность оценивают отдельно.", ""]
    for index, item in enumerate(report["results"], 1):
        lines += [f"## {index}. {item['level']}: {item['title']}", "", "**Запрос**", "", item["prompt"],
                  "", "**Ответ модели (без редактирования)**", "", item["answer"], ""]
    lines += ["## Исходные данные", "", "Полные ответы Ollama, метрики и список запущенных моделей: "
              "[output/day26-results.json](output/day26-results.json).", ""]
    (output.parent / "DAY26_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nГотово: DAY26_RESULTS.md и output/day26-results.json", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
