import { loadPipelineResult } from "./pipeline-data.js";

const credibilityMeta = {
  official: { label: "Official", tone: "official", score: 100 },
  regulator_and_filing: { label: "Regulator", tone: "regulator", score: 98 },
  wire_and_aggregator: { label: "Wire", tone: "wire", score: 80 },
  media: { label: "Media", tone: "media", score: 70 },
  search: { label: "Search", tone: "search", score: 55 },
};

const companyMeta = {
  spacex: { name: "SpaceX", region: "United States", accent: "teal" },
  blue_origin: { name: "Blue Origin", region: "United States", accent: "blue" },
  yuanxin_satellite: { name: "垣信卫星", region: "China", accent: "amber" },
  china_satnet: { name: "中国星网", region: "China", accent: "rose" },
};

const state = {
  companyId: "all",
  credibility: "all",
  result: null,
};

const elements = {
  runId: document.querySelector("#run-id"),
  itemCount: document.querySelector("#item-count"),
  dataSource: document.querySelector("#data-source"),
  visibleCount: document.querySelector("#visible-count"),
  companyFilter: document.querySelector("#company-filter"),
  credibilityFilter: document.querySelector("#credibility-filter"),
  resetFilters: document.querySelector("#reset-filters"),
  companyCards: document.querySelector("#company-cards"),
  newsList: document.querySelector("#news-list"),
  timeline: document.querySelector("#timeline"),
  runStatus: document.querySelector("#run-status"),
  providerList: document.querySelector("#provider-list"),
};

bootstrap();

async function bootstrap() {
  state.result = await loadPipelineResult();
  populateCompanyFilter(state.result);
  bindEvents();
  render();
}

function bindEvents() {
  elements.companyFilter.addEventListener("change", (event) => {
    state.companyId = event.target.value;
    render();
  });

  elements.credibilityFilter.addEventListener("change", (event) => {
    state.credibility = event.target.value;
    render();
  });

  elements.resetFilters.addEventListener("click", () => {
    state.companyId = "all";
    state.credibility = "all";
    elements.companyFilter.value = "all";
    elements.credibilityFilter.value = "all";
    render();
  });
}

function populateCompanyFilter(result) {
  const companies = companiesFromItems(result.items);
  elements.companyFilter.append(
    ...companies.map((company) => {
      const option = document.createElement("option");
      option.value = company.id;
      option.textContent = company.name;
      return option;
    }),
  );
}

function render() {
  const items = sortedItems(state.result.items);
  const filteredItems = filterItems(items);
  const summariesByItem = new Map(state.result.summaries.map((summary) => [summary.item_id, summary]));

  elements.runId.textContent = `run_id: ${state.result.run_id}`;
  elements.itemCount.textContent = `${state.result.items.length} items`;
  elements.dataSource.textContent = state.result.__dataSource === "json" ? "live JSON" : "mock fallback";
  elements.visibleCount.textContent = `${filteredItems.length}`;

  renderCompanyCards(items, filteredItems, summariesByItem);
  renderNewsList(filteredItems, summariesByItem);
  renderTimeline(filteredItems, summariesByItem);
  renderRunStatus(state.result);
  renderProviderStatus(state.result.fetch_statuses ?? []);
}

function renderCompanyCards(allItems, visibleItems, summariesByItem) {
  const companies = companiesFromItems(allItems);
  elements.companyCards.replaceChildren(
    ...companies.map((company) => {
      const companyItems = visibleItems.filter((item) => item.company_id === company.id);
      const allCompanyItems = allItems.filter((item) => item.company_id === company.id);
      const latest = sortedItems(allCompanyItems)[0];
      const freshness = freshnessCounts(allCompanyItems);
      const topRank = bestRank(allCompanyItems);
      const card = document.createElement("article");
      card.className = `company-card accent-${company.accent}`;
      card.innerHTML = `
        <div class="card-topline">
          <span>${escapeHtml(company.region)}</span>
          <span class="credibility-tag ${credibilityMeta[topRank]?.tone ?? "media"}">
            ${credibilityMeta[topRank]?.label ?? topRank}
          </span>
        </div>
        <h3>${escapeHtml(company.name)}</h3>
        <div class="metric-row">
          <div><strong>${freshness.fresh}</strong><span>fresh</span></div>
          <div><strong>${freshness.stale}</strong><span>stale</span></div>
          <div><strong>${freshness.total}</strong><span>total</span></div>
        </div>
        <p>${companyItems.length} 条匹配当前筛选 · ${latest ? formatDate(latest.published_at) : "No date"} · ${escapeHtml(latest?.title ?? "No sample item")}</p>
      `;
      card.addEventListener("click", () => {
        state.companyId = company.id;
        elements.companyFilter.value = company.id;
        render();
      });
      return card;
    }),
  );
}

function renderNewsList(items, summariesByItem) {
  if (items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "没有匹配当前筛选条件的样本新闻。";
    elements.newsList.replaceChildren(empty);
    return;
  }

  elements.newsList.replaceChildren(
    ...items.map((item) => {
      const summary = summariesByItem.get(item.id);
      const rankGroup = item.source.rank_group;
      const credibility = credibilityMeta[rankGroup] ?? credibilityMeta.media;
      const freshness = freshnessState(item);
      const article = document.createElement("article");
      article.className = "news-item";
      article.innerHTML = `
        <div class="news-main">
          <div class="news-row">
            <span class="company-pill">${escapeHtml(item.company_name)}</span>
            <span class="credibility-tag ${credibility.tone}">${credibility.label}</span>
            <span class="freshness-tag ${freshness.className}">${freshness.label}</span>
            <span class="priority-tag priority-${summary?.priority ?? "medium"}">${summary?.priority ?? "medium"}</span>
          </div>
          <h3><a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(summary?.headline ?? item.metadata?.event_type ?? "Unclassified sample item")}</p>
          ${staleDetails(item)}
          <div class="tag-row">
            ${item.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
          </div>
        </div>
        <div class="news-aside">
          <time datetime="${escapeAttribute(item.published_at ?? "")}">${formatDate(item.published_at)}</time>
          <span>${escapeHtml(item.source.source_name)}</span>
          <strong>${summary?.importance_score ?? "--"}</strong>
        </div>
      `;
      return article;
    }),
  );
}

function renderTimeline(items, summariesByItem) {
  const timelineItems = items.slice(0, 7).map((item) => {
    const summary = summariesByItem.get(item.id);
    const rankGroup = item.source.rank_group;
    const credibility = credibilityMeta[rankGroup] ?? credibilityMeta.media;
    const entry = document.createElement("li");
    entry.innerHTML = `
      <time datetime="${escapeAttribute(item.published_at ?? "")}">${formatDate(item.published_at)}</time>
      <div>
        <span class="timeline-company">${escapeHtml(item.company_name)}</span>
        <strong>${escapeHtml(summary?.headline ?? item.title)}</strong>
        <span class="credibility-tag ${credibility.tone}">${credibility.label}</span>
      </div>
    `;
    return entry;
  });

  elements.timeline.replaceChildren(...timelineItems);
}

function renderRunStatus(result) {
  const staleFallback = result.metadata?.stale_fallback ?? {};
  const counts = freshnessCounts(result.items ?? []);
  const rows = [
    ["run_id", result.run_id ?? "--"],
    ["generated_at", formatFullDate(result.generated_at ?? result.finished_at ?? result.started_at)],
    ["总新闻数", String(result.items?.length ?? 0)],
    ["fresh", String(staleFallback.fresh_item_count ?? counts.fresh)],
    ["stale", String(staleFallback.stale_item_count ?? counts.stale)],
    ["fallback companies", formatList(staleFallback.fallback_company_ids ?? [])],
  ];

  elements.runStatus.replaceChildren(
    ...rows.map(([label, value]) => {
      const item = document.createElement("div");
      item.className = "status-cell";
      item.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
      return item;
    }),
  );
}

function renderProviderStatus(statuses) {
  if (!statuses.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state compact";
    empty.textContent = "暂无 provider 状态。";
    elements.providerList.replaceChildren(empty);
    return;
  }

  elements.providerList.replaceChildren(
    ...statuses.map((status) => {
      const providerType = status.provider_type ?? status.source_type ?? "provider";
      const providerStatus = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
      const details = [status.reason, status.error_message].filter(Boolean);
      const row = document.createElement("details");
      row.className = "provider-row";
      row.innerHTML = `
        <summary>
          <span>${escapeHtml(status.company_name ?? status.company_id ?? "--")}</span>
          <strong>${escapeHtml(providerLabel(providerType))}</strong>
          <span class="provider-badge ${providerStatusClass(providerStatus)}">${escapeHtml(providerStatus)}</span>
        </summary>
        <div class="provider-detail">
          <p><strong>provider_id</strong>${escapeHtml(status.provider_id ?? status.source_id ?? "--")}</p>
          <p><strong>reason</strong>${escapeHtml(details[0] ?? "--")}</p>
          <p><strong>error_message</strong>${escapeHtml(status.error_message ?? "--")}</p>
        </div>
      `;
      return row;
    }),
  );
}

function companiesFromItems(items) {
  const seen = new Set();
  return items.reduce((companies, item) => {
    if (seen.has(item.company_id)) return companies;
    seen.add(item.company_id);
    companies.push({
      id: item.company_id,
      name: companyMeta[item.company_id]?.name ?? item.company_name,
      region: companyMeta[item.company_id]?.region ?? "Unknown",
      accent: companyMeta[item.company_id]?.accent ?? "teal",
    });
    return companies;
  }, []);
}

function sortedItems(items) {
  return [...items].sort((a, b) => new Date(b.published_at ?? 0) - new Date(a.published_at ?? 0));
}

function freshnessCounts(items) {
  return items.reduce(
    (counts, item) => {
      const freshness = freshnessState(item);
      counts.total += 1;
      if (freshness.kind === "stale") {
        counts.stale += 1;
      } else {
        counts.fresh += 1;
      }
      return counts;
    },
    { fresh: 0, stale: 0, total: 0 },
  );
}

function freshnessState(item) {
  if (item.stale === true) {
    return { kind: "stale", label: "历史兜底", className: "is-stale" };
  }
  if (item.fresh === true || item.stale === false || item.fresh === undefined) {
    return { kind: "fresh", label: "最新", className: "is-fresh" };
  }
  return { kind: "unknown", label: "未知", className: "is-unknown" };
}

function staleDetails(item) {
  if (item.stale !== true) return "";
  const rows = [
    ["stale_reason", item.stale_reason],
    ["stale_as_of", item.stale_as_of],
    ["stale_from_run_id", item.stale_from_run_id],
  ];
  return `
    <dl class="stale-details">
      ${rows
        .map(
          ([label, value]) =>
            `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "--")}</dd></div>`,
        )
        .join("")}
    </dl>
  `;
}

function filterItems(items) {
  return items.filter((item) => {
    const companyMatches = state.companyId === "all" || item.company_id === state.companyId;
    const credibilityMatches = state.credibility === "all" || item.source.rank_group === state.credibility;
    return companyMatches && credibilityMatches;
  });
}

function bestRank(items) {
  const order = ["official", "regulator_and_filing", "wire_and_aggregator", "media", "search"];
  return order.find((rankGroup) => items.some((item) => item.source.rank_group === rankGroup)) ?? "media";
}

function formatDate(value) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatFullDate(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatList(value) {
  if (!Array.isArray(value) || value.length === 0) return "none";
  return value.join(", ");
}

function providerLabel(value) {
  return String(value).replaceAll("_", " ");
}

function providerStatusClass(status) {
  const value = String(status);
  if (value === "success") return "provider-success";
  if (value === "failed") return "provider-failed";
  if (value === "rate_limited") return "provider-rate";
  if (value.startsWith("skipped")) return "provider-skipped";
  return "provider-unknown";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
