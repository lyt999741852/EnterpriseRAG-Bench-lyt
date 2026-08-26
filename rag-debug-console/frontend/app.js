const api = async (path, options) => {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || "Request failed");
  return body;
};

const state = { versions: [], selectedQuestion: null };
const $ = selector => document.querySelector(selector);

function notice(message) {
  $("#notice-message").textContent = message;
  $("#notice").showModal();
}

function setModeHelp() {
  const pinned = $("#mode").value === "pinned";
  $("#mode-help").textContent = pinned
    ? "固定已发布版本，适合可重复回归。"
    : "调用最新已发布版本，适合日常单题联调。";
}

async function loadHealth() {
  const health = await api("/api/health");
  $("#health").textContent = `服务正常 · ${health.gateway} · 推理锁 ${health.resource_locks["rag-inference"]}`;
}

async function loadVersions() {
  const result = await api("/api/rag-versions");
  state.versions = result.versions;
  const select = $("#version");
  select.innerHTML = result.versions.map(version => `<option value="${version.id}">${version.label} · ${version.id}</option>`).join("");
  select.value = result.versions.find(version => version.is_latest)?.id || result.versions[0].id;
}

function renderCatalog(groups) {
  const target = $("#catalog");
  target.innerHTML = groups.length ? groups.map(group => `
    <section class="catalog-group"><h2>${group.category} · ${group.questions.length}</h2>
      ${group.questions.map(item => `<button class="question-entry" data-id="${item.id}" data-question="${encodeURIComponent(item.text)}"><b>${item.id}</b>${item.text}</button>`).join("")}
    </section>`).join("") : "<p class=\"meta\">没有匹配题目。</p>";
  target.querySelectorAll(".question-entry").forEach(button => button.addEventListener("click", () => {
    state.selectedQuestion = { id: button.dataset.id, text: decodeURIComponent(button.dataset.question) };
    $("#question").value = state.selectedQuestion.text;
    document.querySelector('[data-view="chat"]').click();
  }));
}

async function loadCatalog(query = "") {
  const result = await api(`/api/questions?q=${encodeURIComponent(query)}`);
  renderCatalog(result.groups);
}

function traceHtml(trace) {
  return Object.entries(trace).map(([name, item]) => `<div class="trace-item"><b>${name}</b>${Object.entries(item).filter(([key]) => key !== "views" && key !== "document_ids").map(([key, value]) => `${key}: ${value}`).join(" · ")}</div>`).join("");
}

function metricsHtml(metrics) {
  const judge = metrics.judge;
  const entries = [
    ["Recall", metrics.document_recall_pct],
    ["Invalid docs", metrics.invalid_extra_docs],
    ["Correctness", judge?.correctness_pct],
    ["Completeness", judge?.completeness_pct],
    ["Overall", judge?.overall_pct]
  ].filter(([, value]) => value !== undefined && value !== null);
  return entries.length ? `<div class="metrics">${entries.map(([label, value]) => `<span><b>${label}</b> ${value}${label === "Invalid docs" ? "" : "%"}</span>`).join("")}</div>` : "<p class=\"metric-note\">评测服务尚未返回指标。</p>";
}

function renderRun(run) {
  const conversation = $("#conversation");
  conversation.querySelector(".empty")?.remove();
  conversation.insertAdjacentHTML("beforeend", `
    <article class="message"><div class="avatar">你</div><div><p class="meta">${run.question.id || "手动输入"} · ${run.mode}</p><div class="content"></div></div></article>
    <article class="message assistant"><div class="avatar">RAG</div><div><p class="meta">${run.status} · ${run.timing_ms.total}ms · ${run.rag_version.id}</p><div class="content"><span></span><div class="citations">${run.answer.document_ids.map(id => `<span class="citation">${id}</span>`).join("")}</div>${metricsHtml(run.metrics)}<details class="trace"><summary>查看执行轨迹</summary><div class="trace-grid">${traceHtml(run.trace)}</div></details></div></div></article>`);
  const messages = conversation.querySelectorAll(".message");
  messages[messages.length - 2].querySelector(".content").textContent = run.question.text;
  messages[messages.length - 1].querySelector(".content > span").textContent = run.answer.text;
  conversation.lastElementChild.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function submitQuestion(event) {
  event.preventDefault();
  const question = $("#question").value.trim();
  if (!question) return;
  const payload = { question, mode: $("#mode").value, rag_version: $("#version").value };
  if (state.selectedQuestion?.text === question) payload.question_id = state.selectedQuestion.id;
  try {
    const run = await api("/api/chat-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    renderRun(run);
    $("#question").value = "";
    state.selectedQuestion = null;
  } catch (error) { notice(error.message); }
}

async function loadHistory() {
  const { runs } = await api("/api/chat-runs");
  $("#history").innerHTML = runs.length ? runs.map(run => `<article class="history-item" data-run="${run.run_id}"><h2>${run.question.id || "手动问题"} · ${run.status}</h2><p>${run.question.text}</p><p>${run.mode} · ${run.rag_version} · ${new Date(run.created_at).toLocaleString()}</p></article>`).join("") : "<div class=\"empty\">还没有运行记录。</div>";
  $("#history").querySelectorAll("[data-run]").forEach(item => item.addEventListener("click", async () => {
    renderRun(await api(`/api/chat-runs/${item.dataset.run}`));
    document.querySelector('[data-view="chat"]').click();
  }));
}

async function startBatch(suite) {
  try {
    const run = await api("/api/batch-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ suite, mode: "pinned", rag_version: $("#version").value }) });
    notice(`${suite} 已创建：${run.run_id}`);
    showView("batch");
  } catch (error) { notice(error.message); }
}

async function loadBatches() {
  const { runs } = await api("/api/batch-runs");
  $("#batches").innerHTML = runs.length ? runs.map(run => {
    const percent = run.total ? Math.round(run.completed / run.total * 100) : 0;
    return `<article class="history-item"><h2>${run.suite} · ${run.status}</h2><p>${run.completed} / ${run.total} · ${percent}% · ${run.rag_version.id}</p><div class="batch-progress"><span style="width:${percent}%"></span></div>${["queued", "running"].includes(run.status) ? `<button class="secondary cancel-batch" data-run="${run.run_id}">取消任务</button>` : ""}</article>`;
  }).join("") : "<div class=\"empty\">还没有批量任务。</div>";
  $("#batches").querySelectorAll(".cancel-batch").forEach(button => button.addEventListener("click", async () => { await api(`/api/batch-runs/${button.dataset.run}/cancel`, { method: "POST" }); loadBatches(); }));
}

function showView(view) {
  document.querySelectorAll(".nav").forEach(button => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach(section => section.classList.toggle("active", section.id === `${view}-view`));
  if (view === "history") loadHistory().catch(error => notice(error.message));
  if (view === "batch") loadBatches().catch(error => notice(error.message));
}

document.addEventListener("DOMContentLoaded", async () => {
  try { await Promise.all([loadHealth(), loadVersions(), loadCatalog()]); } catch (error) { notice(error.message); }
  $("#chat-form").addEventListener("submit", submitQuestion);
  $("#mode").addEventListener("change", setModeHelp); setModeHelp();
  $("#catalog-search").addEventListener("input", event => loadCatalog(event.target.value).catch(error => notice(error.message)));
  document.querySelectorAll(".nav").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#clear-chat").addEventListener("click", () => { $("#conversation").innerHTML = '<div class="empty">会话已清空。</div>'; });
  $("#refresh-history").addEventListener("click", () => loadHistory().catch(error => notice(error.message)));
  $("#refresh-batches").addEventListener("click", () => loadBatches().catch(error => notice(error.message)));
  $("#notice-close").addEventListener("click", () => $("#notice").close());
  $("#daily-test").addEventListener("click", () => startBatch("daily-50.v1"));
  $("#full-test").addEventListener("click", () => startBatch("full-500"));
});
