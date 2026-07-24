import {
  loadDashboardData,
  loadDeferredDashboardData,
} from "../../assets/pipeline-data.js";

const endpoints = {
  manifestUrl: "../data/news/latest/manifest.json",
  url: "../data/news/latest/pipeline_result.json",
  archiveUrl: "../data/news/archive/index.json",
  dailyIndexUrl: "../data/news/latest/daily_index.json",
  reportUrl: "../data/reports/latest/daily_report.json",
  indexUrl: "../data/indices/latest/aerospace_index.json",
  catalogUrl: "../data/news/archive/catalog.json",
  eventTimelineUrl: "../data/news/latest/event_timeline.json",
};

const groups = [
  { id: "satellite_platform", name: "卫星制造", color: "#5ce1e6", companies: ["galaxyspace", "hongqing_technology", "minospace"] },
  { id: "launch_services", name: "火箭发射", color: "#4a8cff", companies: ["landspace", "space_pioneer", "cas_space", "i_space", "galactic_energy", "yushi_space"] },
  { id: "satellite_internet", name: "卫星互联网", color: "#9a7cff", companies: ["yuanxin_satellite", "china_satnet"] },
  { id: "global_majors", name: "海外公司", color: "#ff9d5c", companies: ["spacex", "blue_origin"] },
];

const companyNames = {
  galaxyspace: "银河航天",
  hongqing_technology: "蓝箭鸿擎",
  minospace: "微纳星空",
  landspace: "蓝箭航天",
  space_pioneer: "天兵科技",
  cas_space: "中科宇航",
  i_space: "星际荣耀",
  galactic_energy: "星河动力",
  yushi_space: "宇石空间",
  yuanxin_satellite: "垣信卫星",
  china_satnet: "中国星网",
  spacex: "SpaceX",
  blue_origin: "Blue Origin",
};

const eventColors = {
  launch: "#5ce1e6",
  financing: "#9a7cff",
  order: "#ff9d5c",
  regulation: "#ff6f7d",
  market: "#ff8b69",
  partnership: "#52d59b",
  product: "#4a8cff",
  corporate: "#8ea8bd",
  other: "#8ea8bd",
};

const state = {
  result: null,
  report: null,
  dailyIndex: null,
  indexSnapshot: null,
  items: [],
  events: [],
  versionToken: "",
};

start();

async function start() {
  try {
    const dashboard = await loadDashboardData(endpoints);
    state.result = dashboard.result;
    state.report = dashboard.dailyReport;
    state.dailyIndex = dashboard.dailyIndex;
    state.indexSnapshot = dashboard.indexSnapshot;
    state.items = dashboard.result.items ?? [];
    state.versionToken = dashboard.versionToken;
    render();
    const deferred = await loadDeferredDashboardData({
      versionToken: state.versionToken,
      catalogUrl: endpoints.catalogUrl,
      eventTimelineUrl: endpoints.eventTimelineUrl,
    });
    state.items = mergeItems(state.items, deferred.archiveCatalog?.items ?? []);
    state.events = deferred.eventTimeline?.events ?? [];
    render();
  } catch (error) {
    console.error(error);
    document.querySelector("#live-label").textContent = "数据暂时无法连接";
    document.querySelector("#hero-summary").textContent =
      "当前数据文件暂时无法载入，请稍后刷新页面。";
  }
}

function render() {
  const latestDate = latestNewsDate(state.items);
  const dayItems = state.items.filter((item) => dateKey(item.published_at) === latestDate);
  const companies = new Set(state.items.map((item) => item.company_id).filter(Boolean));
  const news = state.indexSnapshot?.news_activity ?? {};
  const china = state.indexSnapshot?.markets?.china;
  const us = state.indexSnapshot?.markets?.united_states;

  setText("#live-label", `最新数据 · ${formatTime(state.result.generated_at)}`);
  setText("#updated-at", formatDateTime(state.result.generated_at));
  setText("#company-count", companies.size);
  setText("#today-count", dayItems.length);
  setText("#pulse-label", news.heat_label ?? "实时累计");
  setText("#news-index", number(news.index_value, 1));
  setText("#news-index-meta", `${news.news_count ?? dayItems.length} 条 · 30 日均值 ${number(news.baseline_average, 1)}`);
  setText("#china-index", china?.index_value == null ? "--" : number(china.index_value, 2));
  setText("#china-change", `BK0480 · ${signed(china?.index_change_pct)}`);
  classForChange(document.querySelector("#china-change"), china?.index_change_pct);
  setText("#us-change", signed(us?.basket_change_pct ?? us?.change_pct));
  setText("#us-breadth", `${us?.advancers ?? 0} 涨 / ${us?.decliners ?? 0} 跌`);
  setText("#event-count", state.events.length || "载入中");
  setText("#market-time", state.indexSnapshot?.as_of_date ?? "--");

  renderBrief(dayItems, latestDate);
  renderTrend(news.history ?? []);
  renderSectors();
  renderMarket(us);
  renderHeatmap(latestDate);
  renderEvents();
}

function renderBrief(dayItems, latestDate) {
  const reportDate = state.report?.report_date;
  const reportCurrent =
    state.report?.source_run_id === state.result.run_id &&
    reportDate === latestDate &&
    Boolean(state.report?.executive_summary);
  const companyCount = new Set(dayItems.map((item) => item.company_id).filter(Boolean)).size;
  setText("#brief-title", `${formatDay(latestDate)}产业动态`);
  setText("#brief-status", reportCurrent ? "简报已同步" : "实时生成");
  const fallback =
    dayItems.length
      ? `${latestDate} 共收录 ${dayItems.length} 条新闻，覆盖 ${companyCount} 家公司。当前内容直接由最新新闻汇总，不等待定时简报。`
      : `${latestDate} 暂无新增新闻，历史资料仍可继续回看。`;
  setText("#brief-summary", reportCurrent ? state.report.executive_summary : fallback);
  const highlights = reportCurrent
    ? (state.report.top_news ?? []).slice(0, 4)
    : [...dayItems].sort((a, b) => score(b) - score(a)).slice(0, 4);
  const list = document.querySelector("#brief-highlights");
  list.replaceChildren(
    ...highlights.map((item) => {
      const li = document.createElement("li");
      li.innerHTML = `<a href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>`;
      return li;
    }),
  );
  if (!highlights.length) list.innerHTML = "<li>暂无当日重点动态</li>";
  setText("#hero-summary", reportCurrent ? state.report.executive_summary : fallback);
}

function renderTrend(history) {
  const rows = history.slice(-60);
  const container = document.querySelector("#news-trend");
  if (!rows.length) {
    container.textContent = "暂无历史趋势";
    return;
  }
  const width = 900;
  const height = 260;
  const max = Math.max(200, ...rows.map((row) => Number(row.index_value) || 0));
  const points = rows.map((row, index) => {
    const x = rows.length === 1 ? width / 2 : index / (rows.length - 1) * width;
    const y = height - (Number(row.index_value) || 0) / max * (height - 24) - 8;
    return { x, y, row };
  });
  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="近 60 日新闻活跃度趋势">
      <defs>
        <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#5ce1e6" stop-opacity=".32"/>
          <stop offset="100%" stop-color="#5ce1e6" stop-opacity="0"/>
        </linearGradient>
      </defs>
      ${[.25,.5,.75].map((ratio) => `<line class="chart-grid" x1="0" y1="${height * ratio}" x2="${width}" y2="${height * ratio}"/>`).join("")}
      <polygon class="trend-area" points="${area}"></polygon>
      <polyline class="trend-line" points="${line}"></polyline>
      ${points.filter((_, index) => index === points.length - 1 || index % 12 === 0).map((point) => `<circle class="trend-dot" cx="${point.x}" cy="${point.y}" r="4"><title>${point.row.date} · ${number(point.row.index_value, 1)}</title></circle>`).join("")}
    </svg>
  `;
  setText("#trend-total", `${rows.reduce((sum, row) => sum + Number(row.news_count || 0), 0)} 篇`);
}

function renderSectors() {
  const latestDate = latestNewsDate(state.items);
  const recent = state.items.filter((item) => daysBetween(dateKey(item.published_at), latestDate) < 30);
  const rows = groups.map((group) => ({
    ...group,
    count: recent.filter((item) => group.companies.includes(item.company_id)).length,
  }));
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  let cursor = 0;
  const stops = rows.map((row) => {
    const start = cursor;
    cursor += total ? row.count / total * 100 : 0;
    return `${row.color} ${start}% ${cursor}%`;
  });
  document.querySelector("#sector-donut").style.background =
    total ? `conic-gradient(${stops.join(",")})` : "#1a2b3b";
  setText("#sector-total", total);
  document.querySelector("#sector-legend").innerHTML = rows.map((row) => `
    <div><i style="background:${row.color}"></i><span>${row.name}</span><strong>${row.count}</strong></div>
  `).join("");
}

function renderMarket(market) {
  const members = (market?.members ?? [])
    .filter((member) => Number.isFinite(Number(member.change_pct)) && Math.abs(Number(member.change_pct)) < 30)
    .sort((a, b) => Math.abs(Number(b.change_pct)) - Math.abs(Number(a.change_pct)))
    .slice(0, 5);
  const max = Math.max(1, ...members.map((member) => Math.abs(Number(member.change_pct))));
  const container = document.querySelector("#market-bars");
  container.innerHTML = members.map((member) => {
    const change = Number(member.change_pct);
    return `
      <div class="market-row ${change > 0 ? "is-up" : ""}">
        <header><span>${escapeHtml(member.name)}</span><strong class="${change > 0 ? "positive" : change < 0 ? "negative" : ""}">${signed(change)}</strong></header>
        <div class="market-track"><i style="width:${Math.max(3, Math.abs(change) / max * 100)}%"></i></div>
      </div>
    `;
  }).join("");
  if (!members.length) container.innerHTML = '<div class="loading-card">当前暂无有效成分股行情</div>';
}

function renderHeatmap(latestDate) {
  const dates = Array.from({ length: 14 }, (_, index) => addDays(latestDate, index - 13));
  const counts = new Map();
  for (const item of state.items) {
    const key = `${item.company_id}|${dateKey(item.published_at)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const max = Math.max(1, ...counts.values());
  const companies = Object.keys(companyNames);
  const cells = ['<span></span>', ...dates.map((date) => `<span class="heat-date">${date.slice(5).replace("-", "/")}</span>`)];
  for (const companyId of companies) {
    cells.push(`<span class="heat-label">${companyNames[companyId]}</span>`);
    for (const date of dates) {
      const count = counts.get(`${companyId}|${date}`) ?? 0;
      const level = count ? Math.max(.15, count / max) : 0;
      cells.push(`<i class="heat-cell" style="--level:${level}" title="${companyNames[companyId]} · ${date} · ${count} 条"></i>`);
    }
  }
  document.querySelector("#company-heatmap").innerHTML = cells.join("");
}

function renderEvents() {
  if (!state.events.length) return;
  const events = [...state.events]
    .sort((a, b) => Number(b.importance_score || 0) - Number(a.importance_score || 0))
    .slice(0, 9);
  document.querySelector("#event-stream").replaceChildren(
    ...events.map((event) => {
      const card = document.createElement("a");
      card.className = "event-card";
      card.href = event.latest_url || "#";
      card.target = "_blank";
      card.rel = "noopener noreferrer";
      card.style.setProperty("--event-color", eventColors[event.event_type] ?? eventColors.other);
      card.innerHTML = `
        <header><span class="event-type">${escapeHtml(event.event_label || event.event_type || "事件")}</span><span>${escapeHtml(companyNames[event.company_id] || event.company_name || event.company_id)}</span></header>
        <h3>${escapeHtml(event.headline)}</h3>
        <p>${escapeHtml(event.summary || "")}</p>
        <footer>${formatDay(dateKey(event.latest_at))} · ${event.article_count ?? 0} 篇报道 · 重要度 ${event.importance_score ?? 0}</footer>
      `;
      return card;
    }),
  );
  const newest = dateKey(events[0]?.latest_at);
  setText("#event-range", `${state.events.length} 个事件 · 更新至 ${formatDay(newest)}`);
}

function mergeItems(primary, archived) {
  const byId = new Map();
  [...archived, ...primary].forEach((item) => byId.set(item.id || item.canonical_url || item.url, item));
  return [...byId.values()];
}

function latestNewsDate(items) {
  return items.reduce((latest, item) => Math.max(latest, dateKey(item.published_at) ? Date.parse(`${dateKey(item.published_at)}T00:00:00Z`) : 0), 0)
    ? items.map((item) => dateKey(item.published_at)).sort().at(-1)
    : "";
}

function dateKey(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function addDays(value, offset) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

function daysBetween(value, anchor) {
  if (!value || !anchor) return 9999;
  return Math.max(0, Math.round((Date.parse(`${anchor}T00:00:00Z`) - Date.parse(`${value}T00:00:00Z`)) / 86400000));
}

function formatDateTime(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function formatTime(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function formatDay(value) {
  if (!value) return "--";
  return `${Number(value.slice(5, 7))}月${Number(value.slice(8, 10))}日`;
}

function score(item) {
  return Number(item.importance_score ?? item.score ?? item.quality_score ?? 0);
}

function number(value, decimals = 0) {
  const resolved = Number(value);
  return Number.isFinite(resolved)
    ? resolved.toLocaleString("zh-CN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    : "--";
}

function signed(value) {
  const resolved = Number(value);
  if (!Number.isFinite(resolved)) return "--";
  return `${resolved > 0 ? "+" : ""}${resolved.toFixed(2)}%`;
}

function classForChange(element, value) {
  const resolved = Number(value);
  element.classList.toggle("positive", resolved > 0);
  element.classList.toggle("negative", resolved < 0);
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = String(value ?? "--");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
