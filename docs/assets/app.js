import { loadPipelineResult } from "./pipeline-data.js";

const companyMeta = {
  spacex: { name: "SpaceX", region: "United States", accent: "teal" },
  blue_origin: { name: "Blue Origin", region: "United States", accent: "blue" },
  yuanxin_satellite: { name: "垣信卫星", region: "China", accent: "amber" },
  china_satnet: { name: "中国星网", region: "China", accent: "rose" },
};

const sourceLabels = {
  official: "Official",
  official_site: "Official Page",
  regulator_and_filing: "Regulator",
  wire_and_aggregator: "Wire",
  media: "Media",
  search: "Search",
  gdelt: "GDELT",
  rss: "RSS",
  serpapi: "SerpApi",
  newsapi: "NewsAPI",
};

const providerOrder = ["rss", "official_site", "gdelt", "serpapi", "newsapi"];

const state = {
  companyId: "all",
  source: "all",
  freshness: "all",
  result: null,
};

const elements = {
  updatedAt: document.querySelector("#updated-at"),
  totalCount: document.querySelector("#total-count"),
  freshCount: document.querySelector("#fresh-count"),
  staleCount: document.querySelector("#stale-count"),
  dataSource: document.querySelector("#data-source"),
  runId: document.querySelector("#run-id"),
  staleFallback: document.querySelector("#stale-fallback-summary"),
  companyTabs: document.querySelector("#company-tabs"),
  companyCards: document.querySelector("#company-cards"),
  providerMatrix: document.querySelector("#provider-matrix"),
  sourceFilter: document.querySelector("#source-filter"),
  freshnessFilter: document.querySelector("#freshness-filter"),
  resetFilters: document.querySelector("#reset-filters"),
  visibleCount: document.querySelector("#visible-count"),
  newsList: document.querySelector("#news-list"),
  exceptionList: document.querySelector("#exception-list"),
};

bootstrap();

async function bootstrap() {
  state.result = await loadPipelineResult();
  populateSourceFilter(state.result.items);
  bindEvents();
  render();
}

function bindEvents() {
  elements.sourceFilter.addEventListener("change", (event) => {
    state.source = event.target.value;
    render();
  });

  elements.freshnessFilter.addEventListener("change", (event) => {
    state.freshness = event.target.value;
    render();
  });

  elements.resetFilters.addEventListener("click", () => {
    state.companyId = "all";
    state.source = "all";
    state.freshness = "all";
    elements.sourceFilter.value = "all";
    elements.freshnessFilter.value = "all";
    render();
  });
}

function render() {
  const items = sortedItems(state.result.items ?? []);
  const filteredItems = filterItems(items);
  const companies = companiesFromItems(items);
  const counts = freshnessCounts(items);

  elements.updatedAt.textContent = formatFullDate(
    state.result.generated_at ?? state.result.finished_at ?? state.result.started_at,
  );
  elements.totalCount.textContent = String(items.length);
  elements.freshCount.textContent = String(counts.fresh);
  elements.staleCount.textContent = String(counts.stale);
  elements.dataSource.textContent = state.result.__dataSource === "json" ? "live JSON" : "mock fallback";
  elements.runId.textContent = state.result.run_id ?? "--";
  elements.staleFallback.textContent = staleFallbackSummary(state.result, counts);
  elements.visibleCount.textContent = `${filteredItems.length} shown`;

  renderCompanyTabs(companies);
  renderCompanyCards(companies, items);
  renderProviderMatrix(companies, state.result.fetch_statuses ?? []);
  renderNewsList(filteredItems);
  renderExceptions(state.result.fetch_statuses ?? []);
}

function populateSourceFilter(items) {
  const sources = [...new Set(items.map((item) => sourceKey(item)).filter(Boolean))].sort();
  elements.sourceFilter.append(
    ...sources.map((source) => {
      const option = document.createElement("option");
      option.value = source;
      option.textContent = sourceLabel(source);
      return option;
    }),
  );
}

function renderCompanyTabs(companies) {
  const allButton = segmentButton("all", "All", state.companyId === "all");
  const buttons = companies.map((company) =>
    segmentButton(company.id, company.name, state.companyId === company.id),
  );
  elements.companyTabs.replaceChildren(allButton, ...buttons);
}

function segmentButton(value, label, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "segment is-active" : "segment";
  button.textContent = label;
  button.addEventListener("click", () => {
    state.companyId = value;
    render();
  });
  return button;
}

function renderCompanyCards(companies, items) {
  elements.companyCards.replaceChildren(
    ...companies.map((company) => {
      const companyItems = items.filter((item) => item.company_id === company.id);
      const counts = freshnessCounts(companyItems);
      const providers = providerSummary(state.result.fetch_statuses ?? [], company.id);
      const latest = sortedItems(companyItems)[0];
      const card = document.createElement("article");
      card.className = `company-card accent-${company.accent}`;
      card.innerHTML = `
        <div class="company-card-header">
          <div>
            <span>${escapeHtml(company.region)}</span>
            <h3>${escapeHtml(company.name)}</h3>
          </div>
          <strong>${counts.total}</strong>
        </div>
        <div class="metric-row">
          <div><strong>${counts.fresh}</strong><span>fresh</span></div>
          <div><strong>${counts.stale}</strong><span>stale</span></div>
          <div><strong>${providers.problem}</strong><span>issues</span></div>
        </div>
        <p>${latest ? formatDate(latest.published_at) : "No date"} · ${escapeHtml(latest?.title ?? "No news in current feed")}</p>
      `;
      card.addEventListener("click", () => {
        state.companyId = company.id;
        render();
      });
      return card;
    }),
  );
}

function renderProviderMatrix(companies, statuses) {
  const companyRows = companies.map((company) => {
    const cells = providerOrder
      .map((provider) => providerCell(statuses, company.id, provider))
      .join("");
    return `
      <tr>
        <th scope="row">${escapeHtml(company.name)}</th>
        ${cells}
      </tr>
    `;
  });

  elements.providerMatrix.innerHTML = `
    <thead>
      <tr>
        <th scope="col">Company</th>
        ${providerOrder.map((provider) => `<th scope="col">${escapeHtml(sourceLabel(provider))}</th>`).join("")}
      </tr>
    </thead>
    <tbody>${companyRows.join("")}</tbody>
  `;
}

function providerCell(statuses, companyId, providerType) {
  const status = statuses.find(
    (row) => row.company_id === companyId && normalizeProvider(row.provider_type ?? row.source_type) === providerType,
  );
  const label = status?.provider_status ?? status?.final_status ?? status?.status ?? "missing";
  return `<td><span class="provider-badge ${providerStatusClass(label)}">${escapeHtml(label)}</span></td>`;
}

function renderNewsList(items) {
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = `
      <strong>No news items match the active filters.</strong>
      <span>Adjust company, source, or freshness filters to widen the feed.</span>
    `;
    elements.newsList.replaceChildren(empty);
    return;
  }

  elements.newsList.replaceChildren(
    ...items.map((item) => {
      const source = sourceKey(item);
      const freshness = freshnessState(item);
      const article = document.createElement("article");
      article.className = "news-item";
      article.innerHTML = `
        <div class="news-body">
          <div class="news-meta">
            <span class="company-pill">${escapeHtml(item.company_name)}</span>
            <span class="source-badge source-${sourceTone(source)}">${escapeHtml(sourceLabel(source))}</span>
            <span class="freshness-tag ${freshness.className}">${freshness.label}</span>
          </div>
          <h3><a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></h3>
          <div class="news-footer">
            <span>${escapeHtml(item.source?.source_name ?? item.source?.source_id ?? "Unknown source")}</span>
            <time datetime="${escapeAttribute(item.published_at ?? "")}">${formatFullDate(item.published_at)}</time>
          </div>
          ${staleDetails(item)}
        </div>
        <a class="open-link" href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">Open</a>
      `;
      return article;
    }),
  );
}

function renderExceptions(statuses) {
  const exceptionRows = statuses.filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "";
    return (
      label !== "success" ||
      status.reason ||
      status.error_message ||
      status.rate_limited === true ||
      status.should_fallback === true
    );
  });

  if (!exceptionRows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state compact";
    empty.innerHTML = `<strong>No provider exceptions.</strong><span>All providers reported success for this run.</span>`;
    elements.exceptionList.replaceChildren(empty);
    return;
  }

  elements.exceptionList.replaceChildren(
    ...exceptionRows.map((status) => {
      const providerType = normalizeProvider(status.provider_type ?? status.source_type);
      const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
      const details = document.createElement("details");
      details.className = "exception-row";
      details.innerHTML = `
        <summary>
          <span>${escapeHtml(status.company_name ?? status.company_id ?? "--")}</span>
          <strong>${escapeHtml(sourceLabel(providerType))}</strong>
          <span class="provider-badge ${providerStatusClass(label)}">${escapeHtml(label)}</span>
        </summary>
        <div class="exception-detail">
          <p><strong>reason</strong>${escapeHtml(status.reason ?? "--")}</p>
          <p><strong>error_message</strong>${escapeHtml(status.error_message ?? "--")}</p>
        </div>
      `;
      return details;
    }),
  );
}

function filterItems(items) {
  return items.filter((item) => {
    const companyMatches = state.companyId === "all" || item.company_id === state.companyId;
    const sourceMatches = state.source === "all" || sourceKey(item) === state.source;
    const freshness = freshnessState(item).kind;
    const freshnessMatches = state.freshness === "all" || freshness === state.freshness;
    return companyMatches && sourceMatches && freshnessMatches;
  });
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

function freshnessCounts(items) {
  return items.reduce(
    (counts, item) => {
      counts.total += 1;
      if (freshnessState(item).kind === "stale") counts.stale += 1;
      else counts.fresh += 1;
      return counts;
    },
    { fresh: 0, stale: 0, total: 0 },
  );
}

function freshnessState(item) {
  if (item.stale === true) return { kind: "stale", label: "Stale fallback", className: "is-stale" };
  return { kind: "fresh", label: "Fresh", className: "is-fresh" };
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

function providerSummary(statuses, companyId) {
  const rows = statuses.filter((status) => status.company_id === companyId);
  return rows.reduce(
    (summary, row) => {
      const label = row.provider_status ?? row.final_status ?? row.status ?? "unknown";
      if (label !== "success") summary.problem += 1;
      return summary;
    },
    { problem: 0 },
  );
}

function sourceKey(item) {
  return normalizeProvider(item.source?.source_type ?? item.source?.rank_group ?? item.source?.source_id ?? "unknown");
}

function normalizeProvider(value) {
  const text = String(value ?? "unknown");
  if (text === "official_page") return "official_site";
  return text;
}

function sourceLabel(value) {
  const key = normalizeProvider(value);
  return sourceLabels[key] ?? key.replaceAll("_", " ");
}

function sourceTone(source) {
  const key = normalizeProvider(source);
  if (key === "official_site" || key === "official") return "official";
  if (key === "gdelt" || key === "wire_and_aggregator") return "wire";
  if (key === "rss" || key === "media") return "media";
  if (key === "serpapi" || key === "newsapi" || key === "search") return "search";
  return "neutral";
}

function providerStatusClass(status) {
  const value = String(status);
  if (value === "success") return "provider-success";
  if (value === "failed") return "provider-failed";
  if (value === "rate_limited") return "provider-rate";
  if (value.startsWith("skipped")) return "provider-skipped";
  return "provider-unknown";
}

function staleFallbackSummary(result, counts) {
  const fallback = result.metadata?.stale_fallback ?? {};
  const enabled = fallback.enabled === false ? "disabled" : "enabled";
  const fresh = fallback.fresh_item_count ?? counts.fresh;
  const stale = fallback.stale_item_count ?? counts.stale;
  const companies = Array.isArray(fallback.fallback_company_ids) ? fallback.fallback_company_ids.length : 0;
  return `${enabled} · fresh ${fresh} · stale ${stale} · companies ${companies}`;
}

function sortedItems(items) {
  return [...items].sort((a, b) => new Date(b.published_at ?? 0) - new Date(a.published_at ?? 0));
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
