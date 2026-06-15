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
  visibleCount: document.querySelector("#visible-count"),
  companyFilter: document.querySelector("#company-filter"),
  credibilityFilter: document.querySelector("#credibility-filter"),
  resetFilters: document.querySelector("#reset-filters"),
  companyCards: document.querySelector("#company-cards"),
  newsList: document.querySelector("#news-list"),
  timeline: document.querySelector("#timeline"),
};

bootstrap();

async function bootstrap() {
  state.result = await loadPipelineResult({ mode: "mock" });
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
  elements.visibleCount.textContent = `${filteredItems.length}`;

  renderCompanyCards(items, filteredItems, summariesByItem);
  renderNewsList(filteredItems, summariesByItem);
  renderTimeline(filteredItems, summariesByItem);
}

function renderCompanyCards(allItems, visibleItems, summariesByItem) {
  const companies = companiesFromItems(allItems);
  elements.companyCards.replaceChildren(
    ...companies.map((company) => {
      const companyItems = visibleItems.filter((item) => item.company_id === company.id);
      const allCompanyItems = allItems.filter((item) => item.company_id === company.id);
      const latest = sortedItems(allCompanyItems)[0];
      const highPriority = allCompanyItems.filter((item) => {
        const summary = summariesByItem.get(item.id);
        return summary?.priority === "high" || summary?.priority === "critical";
      }).length;
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
          <div><strong>${companyItems.length}</strong><span>当前显示</span></div>
          <div><strong>${allCompanyItems.length}</strong><span>样本总量</span></div>
          <div><strong>${highPriority}</strong><span>高优先级</span></div>
        </div>
        <p>${latest ? formatDate(latest.published_at) : "No date"} · ${escapeHtml(latest?.title ?? "No sample item")}</p>
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
      const article = document.createElement("article");
      article.className = "news-item";
      article.innerHTML = `
        <div class="news-main">
          <div class="news-row">
            <span class="company-pill">${escapeHtml(item.company_name)}</span>
            <span class="credibility-tag ${credibility.tone}">${credibility.label}</span>
            <span class="priority-tag priority-${summary?.priority ?? "medium"}">${summary?.priority ?? "medium"}</span>
          </div>
          <h3><a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(summary?.headline ?? item.metadata?.event_type ?? "Unclassified sample item")}</p>
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
