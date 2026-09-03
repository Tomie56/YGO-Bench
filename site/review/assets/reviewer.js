"use strict";

const state = {
  config: null,
  items: [],
  filtered: [],
  reviews: {},
  index: 0,
  decision: null,
  zoom: 1,
};

const elements = Object.fromEntries([
  "categoryFilter", "subtypeFilter", "statusFilter", "issuesOnly", "assetSummary",
  "thumbList", "previousButton", "nextButton", "zoomOutButton", "zoomResetButton",
  "zoomInButton", "itemTitle", "itemCounter", "reviewImage", "itemCategory",
  "itemSubtitle", "itemEnvironment", "itemSource", "itemCore", "itemIssues",
  "reviewNote", "saveReviewButton", "saveStatus", "progressText", "progressBar",
  "storageNotice", "importButton", "exportButton", "importInput",
].map((id) => [id, document.getElementById(id)]));

const labels = {
  all: "全部题型",
  understanding: "理解",
  construction: "构筑",
  puzzles: "策略 Puzzle",
  pending: "待审阅",
  pass: "通过",
  revise: "需修改",
  reject: "删除",
  static_only: "仅静态初始局面，尚未 core 验证",
  not_applicable: "不适用",
};

function reviewStatus(item) {
  return state.reviews[item.id]?.decision || "pending";
}

function storageKey() {
  return `ygo-bench:reviews:${state.config.dataset_version}`;
}

function validateReview(record) {
  if (!record || typeof record !== "object") throw new Error("标注记录必须是对象");
  if (!state.items.some((item) => item.id === record.item_id)) {
    throw new Error(`未知题目 ID：${record.item_id}`);
  }
  if (!["pass", "revise", "reject"].includes(record.decision)) {
    throw new Error(`非法审阅结论：${record.decision}`);
  }
  if (typeof (record.note || "") !== "string" || (record.note || "").length > 4000) {
    throw new Error(`题目 ${record.item_id} 的备注非法`);
  }
}

function loadLocalReviews() {
  const raw = window.localStorage.getItem(storageKey());
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("浏览器中的标注数据格式非法");
  }
  Object.values(parsed).forEach(validateReview);
  return parsed;
}

function persistLocalReviews() {
  window.localStorage.setItem(storageKey(), JSON.stringify(state.reviews));
}

function fillSelect(select, options, current) {
  select.replaceChildren(...options.map(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = value === current;
    return option;
  }));
}

function updateSubtypes() {
  const category = elements.categoryFilter.value;
  const previous = elements.subtypeFilter.value || "all";
  const values = [...new Set(state.items
    .filter((item) => category === "all" || item.category === category)
    .map((item) => item.subtype))].sort();
  const options = [["all", "全部子类型"], ...values.map((value) => [value, value])];
  fillSelect(elements.subtypeFilter, options, values.includes(previous) ? previous : "all");
}

function applyFilters() {
  const activeId = state.filtered[state.index]?.id;
  const category = elements.categoryFilter.value;
  const subtype = elements.subtypeFilter.value;
  const status = elements.statusFilter.value;
  state.filtered = state.items.filter((item) =>
    (category === "all" || item.category === category) &&
    (subtype === "all" || item.subtype === subtype) &&
    (status === "all" || reviewStatus(item) === status) &&
    (!elements.issuesOnly.checked || item.asset_issues.length > 0)
  );
  const activeIndex = state.filtered.findIndex((item) => item.id === activeId);
  state.index = activeIndex >= 0 ? activeIndex : 0;
  renderThumbs();
  renderItem();
}

function renderThumbs() {
  elements.thumbList.replaceChildren(...state.filtered.map((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `thumb-item${index === state.index ? " is-active" : ""}`;
    const image = document.createElement("img");
    image.src = item.thumbnail_url;
    image.alt = "";
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const dot = document.createElement("i");
    dot.className = `status-dot ${reviewStatus(item)}`;
    title.append(dot, document.createTextNode(item.title));
    const subtitle = document.createElement("span");
    subtitle.textContent = item.subtitle;
    text.append(title, subtitle);
    button.append(image, text);
    button.addEventListener("click", () => {
      state.index = index;
      renderThumbs();
      renderItem();
    });
    return button;
  }));
}

function setDecision(decision) {
  state.decision = decision;
  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.decision === decision);
  });
  elements.saveReviewButton.disabled = !decision;
}

function renderItem() {
  const item = state.filtered[state.index];
  const hasItem = Boolean(item);
  elements.previousButton.disabled = !hasItem || state.index === 0;
  elements.nextButton.disabled = !hasItem || state.index >= state.filtered.length - 1;
  elements.itemCounter.textContent = hasItem ? `${state.index + 1} / ${state.filtered.length}` : "0 / 0";
  if (!item) {
    elements.itemTitle.textContent = "没有符合筛选条件的题目";
    elements.reviewImage.removeAttribute("src");
    elements.itemCategory.textContent = "-";
    elements.itemSubtitle.textContent = "-";
    elements.itemEnvironment.textContent = "-";
    elements.itemSource.textContent = "-";
    elements.itemCore.textContent = "-";
    elements.itemIssues.replaceChildren();
    elements.reviewNote.value = "";
    setDecision(null);
    return;
  }
  elements.itemTitle.textContent = item.title;
  elements.reviewImage.src = item.image_url;
  elements.itemCategory.textContent = `${item.category_label} · ${item.subtype}`;
  elements.itemSubtitle.textContent = item.subtitle;
  elements.itemEnvironment.textContent = `${item.regulation} · ${item.snapshot_id}`;
  elements.itemSource.textContent = item.source;
  elements.itemCore.textContent = labels[item.core_status] || item.core_status;
  const issues = item.asset_issues.length ? item.asset_issues : ["无"];
  elements.itemIssues.replaceChildren(...issues.map((value) => {
    const row = document.createElement("li");
    row.textContent = value;
    if (value === "无") row.className = "none";
    return row;
  }));
  const review = state.reviews[item.id];
  elements.reviewNote.value = review?.note || "";
  elements.saveStatus.textContent = review ? `已保存 · ${labels[review.decision]}` : "";
  setDecision(review?.decision || null);
  setZoom(1);
}

function setZoom(value) {
  state.zoom = Math.max(.5, Math.min(2.5, value));
  elements.reviewImage.style.width = `${state.zoom * 100}%`;
  elements.reviewImage.style.maxWidth = state.zoom <= 1 ? "100%" : "none";
}

async function saveReview() {
  const item = state.filtered[state.index];
  if (!item || !state.decision) return;
  elements.saveReviewButton.disabled = true;
  elements.saveStatus.textContent = "保存中";
  const candidate = {
    item_id: item.id,
    dataset_version: state.config.dataset_version,
    decision: state.decision,
    note: elements.reviewNote.value.trim(),
    reviewed_at: new Date().toISOString(),
  };
  let payload;
  if (state.config.storage_mode === "local") {
    validateReview(candidate);
    payload = candidate;
  } else {
    const response = await fetch(state.config.review_url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(candidate),
    });
    payload = await response.json();
    if (!response.ok) {
      elements.saveStatus.textContent = payload.error || "保存失败";
      elements.saveReviewButton.disabled = false;
      return;
    }
  }
  state.reviews[item.id] = payload;
  if (state.config.storage_mode === "local") persistLocalReviews();
  elements.saveStatus.textContent = `已保存 · ${labels[payload.decision]}`;
  updateProgress();
  renderThumbs();
  elements.saveReviewButton.disabled = false;
}

function exportReviews() {
  const records = Object.values(state.reviews).sort((left, right) =>
    left.item_id.localeCompare(right.item_id)
  );
  const body = records.map((record) => JSON.stringify(record)).join("\n") + (records.length ? "\n" : "");
  const blob = new Blob([body], {type: "application/x-ndjson;charset=utf-8"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${state.config.dataset_version}-reviews.jsonl`;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function importReviews(file) {
  const lines = (await file.text()).split(/\r?\n/).filter((line) => line.trim());
  const imported = {};
  lines.forEach((line, index) => {
    let record;
    try {
      record = JSON.parse(line);
    } catch (error) {
      throw new Error(`JSONL 第 ${index + 1} 行无法解析：${error.message}`);
    }
    validateReview(record);
    if (record.dataset_version && record.dataset_version !== state.config.dataset_version) {
      throw new Error(`题目 ${record.item_id} 属于其他数据版本`);
    }
    imported[record.item_id] = {...record, dataset_version: state.config.dataset_version};
  });
  state.reviews = {...state.reviews, ...imported};
  if (state.config.storage_mode === "local") persistLocalReviews();
  updateProgress();
  applyFilters();
  elements.saveStatus.textContent = `已导入 ${Object.keys(imported).length} 条标注`;
}

function updateProgress() {
  const reviewed = Object.keys(state.reviews).filter((id) => state.items.some((item) => item.id === id)).length;
  const percent = state.items.length ? reviewed / state.items.length * 100 : 0;
  elements.progressText.textContent = `${reviewed} / ${state.items.length} 已审阅`;
  elements.progressBar.style.width = `${percent}%`;
}

function bindEvents() {
  elements.categoryFilter.addEventListener("change", () => { updateSubtypes(); applyFilters(); });
  elements.subtypeFilter.addEventListener("change", applyFilters);
  elements.statusFilter.addEventListener("change", applyFilters);
  elements.issuesOnly.addEventListener("change", applyFilters);
  elements.previousButton.addEventListener("click", () => { state.index -= 1; renderThumbs(); renderItem(); });
  elements.nextButton.addEventListener("click", () => { state.index += 1; renderThumbs(); renderItem(); });
  elements.zoomOutButton.addEventListener("click", () => setZoom(state.zoom - .2));
  elements.zoomResetButton.addEventListener("click", () => setZoom(1));
  elements.zoomInButton.addEventListener("click", () => setZoom(state.zoom + .2));
  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", () => setDecision(button.dataset.decision));
  });
  elements.saveReviewButton.addEventListener("click", saveReview);
  elements.exportButton.addEventListener("click", exportReviews);
  elements.importButton.addEventListener("click", () => elements.importInput.click());
  elements.importInput.addEventListener("change", async () => {
    const [file] = elements.importInput.files;
    if (!file) return;
    try {
      await importReviews(file);
    } catch (error) {
      elements.saveStatus.textContent = error.message;
    } finally {
      elements.importInput.value = "";
    }
  });
}

async function initialize() {
  const configResponse = await fetch("config.json");
  if (!configResponse.ok) throw new Error(`Config request failed: ${configResponse.status}`);
  state.config = await configResponse.json();
  const response = await fetch(state.config.catalog_url);
  if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
  const catalog = await response.json();
  state.items = catalog.items;
  state.reviews = state.config.storage_mode === "local" ? loadLocalReviews() : catalog.reviews;
  fillSelect(elements.categoryFilter, [
    ["all", labels.all], ["understanding", labels.understanding],
    ["construction", labels.construction], ["puzzles", labels.puzzles],
  ], "all");
  elements.assetSummary.textContent = `${catalog.asset_snapshot.name} · ${catalog.asset_snapshot.cached_file_count} / ${catalog.asset_snapshot.passcode_count} 张卡图 · 来源 ${catalog.asset_snapshot.sources.join(" + ")}`;
  elements.storageNotice.textContent = state.config.storage_mode === "local"
    ? "结果仅保存在当前浏览器。完成后请导出 JSONL。"
    : "结果写入本地审阅日志，可随时导出备份。";
  updateSubtypes();
  bindEvents();
  applyFilters();
  updateProgress();
}

initialize().catch((error) => {
  elements.itemTitle.textContent = "审阅器加载失败";
  elements.itemSubtitle.textContent = error.message;
});
