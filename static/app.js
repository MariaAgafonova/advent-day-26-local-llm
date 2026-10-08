"use strict";
const $ = (id) => document.getElementById(id);
let examples = [];
let busy = false;
let connected = false;
const results = [];

function showError(message = "") {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function updateControls() {
  $("send").disabled = busy || !connected;
  $("run-all").disabled = busy || !connected;
  $("model").disabled = busy || !connected;
  $("refresh").disabled = busy;
  $("prompt").disabled = busy;
  document.querySelectorAll(".example").forEach((button) => { button.disabled = busy || !connected; });
  $("download").disabled = !results.length;
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function addText(parent, tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

async function refresh() {
  $("refresh").disabled = true;
  showError();
  try {
    const data = await api("/api/status");
    const previous = $("model").value;
    $("model").replaceChildren();
    data.models.forEach((model) => {
      const size = (model.size / 1e9).toFixed(1);
      $("model").add(new Option(`${model.name} · ${model.details?.parameter_size || ""} · ${size} ГБ`, model.name));
    });
    const names = data.models.map((model) => model.name);
    if (names.includes(previous)) $("model").value = previous;
    else if (names.includes(data.default_model)) $("model").value = data.default_model;
    connected = names.length > 0;
    $("status-dot").className = "dot online";
    $("status-text").textContent = "Ollama доступна";
    $("version").textContent = `Версия ${data.version} · моделей: ${names.length}`;
    if (!connected) showError("В Ollama нет локальных моделей. Установите модель и проверьте соединение снова.");
    examples = data.examples;
    $("examples").replaceChildren();
    examples.forEach((example, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "example";
      addText(button, "span", `0${index + 1} / ${example.level.toUpperCase()}`, "level");
      addText(button, "strong", example.title);
      const bottom = addText(button, "span", "Подставить запрос", "example-bottom");
      addText(bottom, "span", "↗");
      button.addEventListener("click", () => { $("prompt").value = example.prompt; $("prompt").focus(); });
      $("examples").append(button);
    });
  } catch (error) {
    connected = false;
    $("status-dot").className = "dot offline";
    $("status-text").textContent = "Нет соединения";
    $("version").textContent = "Проверьте, запущена ли Ollama";
    showError(error.message);
  } finally {
    updateControls();
  }
}

function renderResult(result, label) {
  const card = document.createElement("article");
  card.className = "result";
  const top = document.createElement("div");
  top.className = "result-top";
  addText(top, "span", label, "result-title");
  addText(top, "span", result.model);
  card.append(top);
  addText(card, "p", result.prompt, "result-prompt");
  // Model output is text, never executable HTML.
  addText(card, "div", result.answer, "answer");
  if (result.truncated) addText(card, "p", "Ответ достиг лимита 1024 токена и может быть неполным. Уточните запрос или попросите более короткий ответ.", "warning");
  const speed = result.tokens_per_second === null ? "—" : result.tokens_per_second;
  addText(card, "div", `${result.elapsed_seconds} с · ${result.output_tokens} токенов · ${speed} токенов/с`, "metrics");
  $("results").prepend(card);
  $("empty").hidden = true;
  $("count").textContent = results.length;
}

async function run(prompts) {
  if (busy || !connected) return;
  busy = true;
  showError();
  updateControls();
  const model = $("model").value;
  $("progress").hidden = false;
  try {
    for (let i = 0; i < prompts.length; i++) {
      const item = prompts[i];
      const start = Date.now();
      const update = () => {
        $("progress-text").textContent = `${prompts.length > 1 ? `Запрос ${i + 1} из ${prompts.length}. ` : ""}Модель отвечает… ${Math.floor((Date.now() - start) / 1000)} с`;
      };
      update();
      const timer = setInterval(update, 1000);
      try {
        const result = await api("/api/chat", {model, prompt: item.prompt});
        results.push({...result, level: item.level, saved_at: new Date().toISOString()});
        renderResult(result, item.level || "Ваш запрос");
      } finally {
        clearInterval(timer);
      }
    }
  } catch (error) {
    showError(error.message || "Не удалось получить ответ. Проверьте соединение.");
  } finally {
    busy = false;
    $("progress").hidden = true;
    updateControls();
  }
}

$("prompt-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) { showError("Введите запрос."); return; }
  run([{prompt, level: "Ваш запрос"}]);
});
$("prompt").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    $("prompt-form").requestSubmit();
  }
});
$("run-all").addEventListener("click", () => run(examples));
$("refresh").addEventListener("click", refresh);
$("download").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify({results}, null, 2)], {type: "application/json;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = "day26-results.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
refresh();
