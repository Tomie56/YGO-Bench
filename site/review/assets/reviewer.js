"use strict";

const state = {
  config: null,
  catalog: null,
  items: [],
  filtered: [],
  reviews: {},
  index: 0,
  decision: null,
  zoom: 1,
  selectedCard: null,
  zoneCatalog: [],
  activeZoneKey: null,
};

const elements = Object.fromEntries([
  "categoryFilter", "subtypeFilter", "statusFilter", "issuesOnly", "assetSummary",
  "thumbList", "previousButton", "nextButton", "zoomOutButton", "zoomResetButton",
  "zoomInButton", "itemTitle", "itemCounter", "reviewImage", "itemCategory",
  "itemSubtitle", "itemEnvironment", "itemSource", "itemCore", "itemIssues",
  "reviewNote", "saveReviewButton", "saveStatus", "progressText", "progressBar",
  "storageNotice", "importButton", "exportButton", "importInput", "zoneBrowser",
  "zoneGroups", "imageStage", "interactiveStage", "duelBoard", "cardDetail", "cardDetailArt",
  "cardDetailName", "cardDetailPasscode", "cardDetailStats",
  "cardDetailDescription", "cardDetailContext",
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

const attributes = {
  1: "地", 2: "水", 4: "炎", 8: "风", 16: "光", 32: "暗", 64: "神",
};

const races = {
  1: "战士族", 2: "魔法师族", 4: "天使族", 8: "恶魔族", 16: "不死族",
  32: "机械族", 64: "水族", 128: "炎族", 256: "岩石族", 512: "鸟兽族",
  1024: "植物族", 2048: "昆虫族", 4096: "雷族", 8192: "龙族",
  16384: "兽族", 32768: "兽战士族", 65536: "恐龙族", 131072: "鱼族",
  262144: "海龙族", 524288: "爬虫类族", 1048576: "念动力族",
  2097152: "幻神兽族", 4194304: "创造神族", 8388608: "幻龙族",
  16777216: "电子界族", 33554432: "幻想魔族",
};

const typeFlags = [
  [0x1, "怪兽"], [0x2, "魔法"], [0x4, "陷阱"], [0x10, "通常"],
  [0x20, "效果"], [0x40, "融合"], [0x80, "仪式"], [0x200, "灵魂"],
  [0x400, "同盟"], [0x800, "二重"], [0x1000, "调整"], [0x2000, "同调"],
  [0x10000, "速攻"], [0x20000, "永续"], [0x40000, "装备"],
  [0x80000, "场地"], [0x100000, "反击"], [0x200000, "反转"],
  [0x400000, "卡通"], [0x800000, "超量"], [0x1000000, "灵摆"],
  [0x4000000, "连接"],
];

function makeElement(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function cardDetails(card) {
  return card?.card_id == null ? null : state.catalog.card_catalog[String(card.card_id)] || null;
}

function cardImageUrl(cardId) {
  return `${state.catalog.asset_snapshot.card_image_base_url}/${cardId}.jpg`;
}

function attachCardImage(container, cardId, alt) {
  const image = document.createElement("img");
  image.src = cardImageUrl(cardId);
  image.alt = alt;
  image.loading = "lazy";
  image.addEventListener("error", () => {
    image.remove();
    container.classList.add("is-missing");
    container.append(makeElement("span", "missing-card-text", `NO IMAGE\n${cardId}`));
  }, {once: true});
  container.append(image);
}

function formatType(typeValue) {
  const values = typeFlags.filter(([flag]) => (typeValue & flag) !== 0).map(([, label]) => label);
  return values.join(" / ") || "未知类型";
}

function formatStat(value) {
  return value < 0 ? "?" : String(value);
}

function sideLabel(controller) {
  return controller === 0 ? "我方" : "对手";
}

function renderCardDetail(card, context = "") {
  state.selectedCard = card;
  elements.cardDetail.hidden = false;
  elements.cardDetailArt.replaceChildren();
  elements.cardDetailContext.textContent = context || `${sideLabel(card.controller)} · ${card.location_label}`;
  const details = cardDetails(card);
  if (!details) {
    elements.cardDetailArt.className = "card-detail__art card-back";
    elements.cardDetailName.textContent = "隐藏卡牌";
    elements.cardDetailPasscode.textContent = "身份未向当前观察者公开";
    elements.cardDetailStats.textContent = `${sideLabel(card.controller)} · ${card.location_label} · ${card.position}`;
    elements.cardDetailDescription.textContent = "该区域只显示卡背与数量，交互不会揭示卡名、卡号或效果。";
    return;
  }
  elements.cardDetailArt.className = "card-detail__art";
  attachCardImage(elements.cardDetailArt, details.card_id, details.name);
  elements.cardDetailName.textContent = details.name;
  elements.cardDetailPasscode.textContent = `PASSCODE ${details.card_id} · ${formatType(details.type)}`;
  const isMonster = (details.type & 0x1) !== 0;
  elements.cardDetailStats.textContent = isMonster
    ? `${attributes[details.attribute] || "未知属性"} · ${races[details.race] || "未知种族"} · Lv/Rank ${details.level} · ATK ${formatStat(details.attack)} / DEF ${formatStat(details.defense)}`
    : `${sideLabel(card.controller)} · ${card.location_label} · ${card.position}`;
  elements.cardDetailDescription.textContent = details.description || "无效果文本。";
}

function showCardPrompt() {
  state.selectedCard = null;
  elements.cardDetail.hidden = false;
  elements.cardDetailArt.className = "card-detail__art card-detail__placeholder";
  elements.cardDetailArt.replaceChildren(makeElement("span", "", "CARD"));
  elements.cardDetailName.textContent = "选择一张卡牌";
  elements.cardDetailPasscode.textContent = "右键场上卡牌，或点击下方区域列表";
  elements.cardDetailStats.textContent = "隐藏卡只显示其公开信息";
  elements.cardDetailDescription.textContent = "卡牌详情不会改变题目状态，也不会执行任何对局动作。";
  elements.cardDetailContext.textContent = "审阅模式";
}

function interactiveCard(card, {compact = false, board = false, pile = false, onSelect = null} = {}) {
  const details = cardDetails(card);
  const button = makeElement("button", `interactive-card${compact ? " interactive-card--compact" : ""}`);
  button.type = "button";
  button.dataset.uid = card.uid;
  button.title = details ? `${details.name} · 点击或右键查看详情` : "隐藏卡牌";
  const faceDownOnField = card.face_down && ["LOCATION_MZONE", "LOCATION_SZONE"].includes(card.location);
  const showFace = details && (!board || !faceDownOnField);
  if (showFace) {
    attachCardImage(button, details.card_id, details.name);
  } else {
    button.classList.add("card-back");
    button.setAttribute("aria-label", "隐藏卡牌");
  }
  if (board && !pile && card.defense) button.classList.add("is-defense");
  if (pile) button.classList.add("interactive-card--pile");
  if (board && !pile && card.location === "LOCATION_MZONE") {
    button.classList.add(card.controller === 0 ? "is-player-monster" : "is-opponent-monster");
  }
  const select = () => onSelect ? onSelect(card) : renderCardDetail(card);
  button.addEventListener("click", select);
  button.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    select();
  });
  return button;
}

function cardsFor(field, controller, location) {
  return field.cards.filter((card) => card.controller === controller && card.location === location);
}

function fieldCard(field, controller, location, sequence) {
  return field.cards.find((card) =>
    card.controller === controller && card.location === location && card.sequence === sequence
  );
}

function zoneKey(controller, location) {
  return `${controller}:${location}`;
}

function zoneSlot(card, label) {
  const slot = makeElement("div", "board-zone");
  slot.append(card ? interactiveCard(card, {board: true}) : makeElement("span", "board-zone__label", label));
  return slot;
}

function zoneRow(field, controller, location, prefix) {
  const row = makeElement("div", "board-zone-row");
  for (let sequence = 0; sequence < 5; sequence += 1) {
    row.append(zoneSlot(fieldCard(field, controller, location, sequence), `${prefix}${sequence + 1}`));
  }
  return row;
}

function pileSummary(field, controller) {
  const column = makeElement("div", "pile-summary");
  [
    ["LOCATION_DECK", "Deck"], ["LOCATION_GRAVE", "GY"],
    ["LOCATION_REMOVED", "Ban"], ["LOCATION_EXTRA", "Extra"],
  ].forEach(([location, label]) => {
    const cards = cardsFor(field, controller, location);
    const topCard = cards.at(-1);
    const row = makeElement("div", "pile-summary__item");
    const key = zoneKey(controller, location);
    const focusPile = () => focusZoneBrowser(key, true);
    row.dataset.zoneKey = key;
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    row.setAttribute("aria-label", `${sideLabel(controller)} ${label}，${cards.length} 张`);
    const slot = topCard
      ? interactiveCard(topCard, {board: true, pile: true, onSelect: focusPile})
      : makeElement("div", "pile-card--empty");
    row.append(
      slot,
      makeElement("span", "pile-summary__label", label),
      makeElement("strong", "pile-summary__count", String(cards.length)),
    );
    row.addEventListener("click", focusPile);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusPile();
      }
    });
    column.append(row);
  });
  return column;
}

function fieldSide(field, controller) {
  const wrapper = makeElement("div", `field-side field-side--${controller === 0 ? "player" : "opponent"}`);
  const main = makeElement("div", "field-side__main");
  if (controller === 1) {
    main.append(zoneRow(field, controller, "LOCATION_SZONE", "S"));
    main.append(zoneRow(field, controller, "LOCATION_MZONE", "M"));
  } else {
    main.append(zoneRow(field, controller, "LOCATION_MZONE", "M"));
    main.append(zoneRow(field, controller, "LOCATION_SZONE", "S"));
  }
  wrapper.append(main, pileSummary(field, controller));
  return wrapper;
}

function handStrip(field, controller) {
  const wrapper = makeElement("div", `hand-strip hand-strip--${controller === 0 ? "player" : "opponent"}`);
  const cards = cardsFor(field, controller, "LOCATION_HAND");
  wrapper.append(makeElement("span", "hand-strip__label", `${sideLabel(controller)}手牌 ${cards.length}`));
  const list = makeElement("div", "hand-strip__cards");
  cards.forEach((card) => list.append(interactiveCard(card, {compact: true, board: true})));
  wrapper.append(list);
  return wrapper;
}

function renderDuelBoard(field) {
  elements.duelBoard.replaceChildren();
  const opponentBar = makeElement("div", "player-bar");
  opponentBar.append(makeElement("span", "", field.ai_name || "Opponent"), makeElement("strong", "", `${field.life_points.opponent} LP`));
  const playerBar = makeElement("div", "player-bar");
  playerBar.append(makeElement("span", "", "Player 0"), makeElement("strong", "", `${field.life_points.player} LP`));
  const emz = makeElement("div", "emz-row");
  [5, 6].forEach((sequence, index) => {
    const card = field.cards.find((candidate) =>
      candidate.location === "LOCATION_MZONE" && candidate.sequence === sequence
    );
    const slot = zoneSlot(card, `EMZ ${index + 1}`);
    slot.classList.add(index === 0 ? "emz-left" : "emz-right");
    emz.append(slot);
  });
  const objective = makeElement("div", "board-objective", field.objective);
  elements.duelBoard.append(
    opponentBar,
    handStrip(field, 1),
    fieldSide(field, 1),
    emz,
    fieldSide(field, 0),
    handStrip(field, 0),
    playerBar,
    objective,
  );
}

function renderZonePanel(group) {
  const panel = elements.zoneGroups.querySelector(".zone-panel");
  panel.replaceChildren();
  const heading = makeElement("div", "zone-panel__heading");
  heading.append(makeElement("strong", "", group.label), makeElement("span", "", `${group.cards.length} 张`));
  const list = makeElement("div", "zone-card-list");
  group.cards.forEach((card, index) => {
    const entry = makeElement("div", "zone-card-entry");
    entry.append(interactiveCard(card, {
      compact: true,
      onSelect: () => renderCardDetail(card, `${group.label} · 第 ${index + 1} 张`),
    }));
    const details = cardDetails(card);
    const text = makeElement("div", "zone-card-entry__text");
    text.append(
      makeElement("strong", "", details?.name || "隐藏卡牌"),
      makeElement("span", "", `第 ${index + 1} 张 · ${card.position}`),
    );
    entry.append(text);
    list.append(entry);
  });
  if (!group.cards.length) list.append(makeElement("p", "zone-empty", "该区域为空"));
  if (group.warning) list.append(makeElement("p", "zone-warning", group.warning));
  panel.append(heading, list);
}

function focusZoneBrowser(key, reveal = false) {
  const group = state.zoneCatalog.find((candidate) => candidate.key === key);
  if (!group) return;
  state.activeZoneKey = key;
  elements.zoneGroups.querySelectorAll(".zone-tab").forEach((tab) => {
    const active = tab.dataset.zoneKey === key;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".pile-summary__item").forEach((pile) => {
    pile.classList.toggle("is-active", pile.dataset.zoneKey === key);
  });
  renderZonePanel(group);
  if (reveal) {
    elements.imageStage.scrollTo({top: elements.zoneBrowser.offsetTop - 8, behavior: "smooth"});
  }
}

function renderZoneBrowser(field) {
  const pileSpecs = [
    ["LOCATION_DECK", "Deck"], ["LOCATION_GRAVE", "GY"],
    ["LOCATION_REMOVED", "Ban"], ["LOCATION_EXTRA", "Extra"],
  ];
  state.zoneCatalog = [0, 1].flatMap((controller) => pileSpecs.map(([location, label]) => ({
    key: zoneKey(controller, location),
    label: `${sideLabel(controller)} ${label}`,
    cards: cardsFor(field, controller, location),
  })));
  state.zoneCatalog.push({
    key: "all:SET",
    label: "场上盖放卡",
    cards: field.cards.filter((card) =>
      card.face_down && ["LOCATION_MZONE", "LOCATION_SZONE"].includes(card.location)
    ),
  });
  state.zoneCatalog.push({
    key: "all:OVERLAY",
    label: "超量素材",
    cards: field.overlay.materials,
    warning: field.overlay.unresolved_calls
      ? `${field.overlay.unresolved_calls} 处动态 Overlay 调用尚未静态解析`
      : "",
  });

  const tabs = makeElement("div", "zone-tabs");
  tabs.setAttribute("role", "tablist");
  state.zoneCatalog.forEach((group) => {
    const tab = makeElement("button", "zone-tab");
    tab.type = "button";
    tab.dataset.zoneKey = group.key;
    tab.setAttribute("role", "tab");
    tab.append(makeElement("span", "", group.label), makeElement("strong", "", String(group.cards.length)));
    tab.addEventListener("click", () => focusZoneBrowser(group.key, true));
    tabs.append(tab);
  });
  elements.zoneGroups.replaceChildren(tabs, makeElement("section", "zone-panel"));
  const preferred = state.zoneCatalog.find((group) => group.key === state.activeZoneKey)
    || state.zoneCatalog.find((group) => group.cards.length)
    || state.zoneCatalog[0];
  focusZoneBrowser(preferred.key);
}

function renderInteractivePuzzle(item) {
  elements.reviewImage.hidden = true;
  elements.interactiveStage.hidden = false;
  elements.zoneBrowser.hidden = false;
  renderDuelBoard(item.interactive_state);
  renderZoneBrowser(item.interactive_state);
  showCardPrompt();
}

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
    elements.reviewImage.hidden = false;
    elements.interactiveStage.hidden = true;
    elements.zoneBrowser.hidden = true;
    elements.cardDetail.hidden = true;
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
  if (item.category === "puzzles" && item.interactive_state) {
    renderInteractivePuzzle(item);
  } else {
    elements.reviewImage.hidden = false;
    elements.reviewImage.src = item.image_url;
    elements.interactiveStage.hidden = true;
    elements.zoneBrowser.hidden = true;
    elements.cardDetail.hidden = true;
  }
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
  if (elements.interactiveStage.hidden) {
    elements.reviewImage.style.width = `${state.zoom * 100}%`;
    elements.reviewImage.style.maxWidth = state.zoom <= 1 ? "100%" : "none";
    return;
  }
  elements.interactiveStage.style.width = "100%";
  elements.interactiveStage.style.maxWidth = "1100px";
  elements.interactiveStage.style.zoom = String(state.zoom);
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
  state.catalog = catalog;
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
