import { loadPipelineResult } from "./pipeline-data.js";

const companyMeta = {
  spacex: { name: "SpaceX", region: "美国", color: "azure" },
  blue_origin: { name: "Blue Origin", region: "美国", color: "indigo" },
  yuanxin_satellite: { name: "垣信卫星", region: "中国", color: "orange" },
  china_satnet: { name: "中国星网", region: "中国", color: "pink" },
};

const companyOrder = ["spacex", "blue_origin", "yuanxin_satellite", "china_satnet"];

const providerOrder = ["rss", "official_site", "gdelt", "serpapi", "newsapi"];
const providerLabels = {
  rss: "RSS",
  official_site: "官网页面",
  official_page: "官网页面",
  gdelt: "GDELT",
  serpapi: "SerpApi",
  newsapi: "NewsAPI",
  media: "媒体",
  search: "搜索",
};

const statusLabels = {
  success: "成功",
  rate_limited: "限流",
  failed: "失败",
  skipped_no_secret: "跳过：未配置密钥",
  missing: "无记录",
  unknown: "未知",
};

const state = {
  companyId: "all",
  provider: "all",
  freshness: "all",
  result: null,
};

const elements = {
  dataSource: document.querySelector("#data-source"),
  updatedAt: document.querySelector("#updated-at"),
  kpiCards: document.querySelector("#kpi-cards"),
  runId: document.querySelector("#run-id"),
  runStatus: document.querySelector("#run-status"),
  companyTabs: document.querySelector("#company-tabs"),
  companyFilter: document.querySelector("#company-filter"),
  providerFilter: document.querySelector("#provider-filter"),
  freshnessFilter: document.querySelector("#freshness-filter"),
  resetFilters: document.querySelector("#reset-filters"),
  companyCards: document.querySelector("#company-cards"),
  providerTable: document.querySelector("#provider-table"),
  visibleCount: document.querySelector("#visible-count"),
  newsList: document.querySelector("#news-list"),
  errorAccordion: document.querySelector("#error-accordion"),
};

bootstrap();

async function bootstrap() {
  state.result = await loadPipelineResult();
  populateFilters();
  bindEvents();
  render();
}

function bindEvents() {
  elements.companyFilter.addEventListener("change", (event) => {
    state.companyId = event.target.value;
    render();
  });
  elements.providerFilter.addEventListener("change", (event) => {
    state.provider = event.target.value;
    render();
  });
  elements.freshnessFilter.addEventListener("change", (event) => {
    state.freshness = event.target.value;
    render();
  });
  elements.resetFilters.addEventListener("click", () => {
    state.companyId = "all";
    state.provider = "all";
    state.freshness = "all";
    elements.companyFilter.value = "all";
    elements.providerFilter.value = "all";
    elements.freshnessFilter.value = "all";
    render();
  });
}

function populateFilters() {
  const companies = companiesFromItems(state.result.items);
  elements.companyFilter.append(
    ...companies.map((company) => option(company.id, company.name)),
  );

  const providers = [...new Set(state.result.items.map((item) => itemProvider(item)))].sort();
  elements.providerFilter.append(
    ...providers.map((provider) => option(provider, providerLabel(provider))),
  );
}

function render() {
  const items = sortedItems(state.result.items);
  const companies = companiesFromItems(items);
  const counts = freshnessCounts(items);
  const filteredItems = filterItems(items);

  elements.dataSource.textContent = state.result.__dataSource === "json" ? "实时 JSON" : "模拟数据兜底";
  elements.dataSource.className =
    state.result.__dataSource === "json" ? "badge bg-green-lt" : "badge bg-yellow-lt";
  elements.updatedAt.textContent = formatFullDate(
    state.result.generated_at ?? state.result.finished_at ?? state.result.started_at,
  );
  elements.runId.textContent = `运行 ID：${state.result.run_id ?? "--"}`;
  elements.visibleCount.textContent = `已显示 ${filteredItems.length} 条`;

  renderKpis(items, companies, counts);
  renderRunStatus(counts);
  renderCompanyTabs(companies);
  renderCompanyCards(companies, items);
  renderProviderTable(companies, state.result.fetch_statuses ?? []);
  renderNewsList(filteredItems);
  renderErrors(state.result.fetch_statuses ?? []);
}

function renderKpis(items, companies, counts) {
  const kpis = [
    ["新闻总数", items.length, "primary"],
    ["覆盖公司", companies.length, "azure"],
    ["最新新闻", counts.fresh, "green"],
    ["历史兜底", counts.stale, "purple"],
    ["最后更新", formatFullDate(state.result.generated_at), "secondary"],
  ];
  elements.kpiCards.replaceChildren(
    ...kpis.map(([label, value, color]) => {
      const col = document.createElement("div");
      col.className = "col-sm-6 col-lg";
      col.innerHTML = `
        <div class="card kpi-card">
          <div class="card-body">
            <div class="subheader">${escapeHtml(label)}</div>
            <div class="h2 mb-0 text-${escapeHtml(color)}">${escapeHtml(value)}</div>
          </div>
        </div>
      `;
      return col;
    }),
  );
}

function renderRunStatus(counts) {
  const fallback = state.result.metadata?.stale_fallback ?? {};
  const rows = [
    ["生成时间", formatFullDate(state.result.generated_at ?? state.result.finished_at)],
    ["历史兜底", fallback.enabled === false ? "已关闭" : "已启用"],
    ["兜底公司", arraySummary(fallback.fallback_company_ids)],
    ["最新 / 历史", `${fallback.fresh_item_count ?? counts.fresh} / ${fallback.stale_item_count ?? counts.stale}`],
  ];
  elements.runStatus.replaceChildren(
    ...rows.map(([label, value]) => {
      const col = document.createElement("div");
      col.className = "col-sm-6 col-lg-3";
      col.innerHTML = `
        <div class="datagrid-item">
          <div class="datagrid-title">${escapeHtml(label)}</div>
          <div class="datagrid-content">${escapeHtml(value)}</div>
        </div>
      `;
      return col;
    }),
  );
}

function renderCompanyTabs(companies) {
  const rows = [{ id: "all", name: "全部公司" }, ...companies];
  elements.companyTabs.replaceChildren(
    ...rows.map((company) => {
      const item = document.createElement("li");
      item.className = "nav-item";
      item.innerHTML = `
        <button class="nav-link ${state.companyId === company.id ? "active" : ""}" type="button">
          ${escapeHtml(company.name)}
        </button>
      `;
      item.querySelector("button").addEventListener("click", () => {
        state.companyId = company.id;
        elements.companyFilter.value = company.id;
        render();
      });
      return item;
    }),
  );
}

function renderCompanyCards(companies, items) {
  elements.companyCards.replaceChildren(
    ...companies.map((company) => {
      const companyItems = items.filter((item) => item.company_id === company.id);
      const counts = freshnessCounts(companyItems);
      const latest = sortedItems(companyItems)[0];
      const issues = providerIssues(state.result.fetch_statuses ?? [], company.id);
      const col = document.createElement("div");
      col.className = "col-md-6 col-xl-3";
      col.innerHTML = `
        <div class="card company-card h-100">
          <div class="card-body">
            <div class="d-flex align-items-center justify-content-between mb-3">
              <div>
                <div class="subheader">${escapeHtml(company.region)}</div>
                <h3 class="card-title mb-0">${escapeHtml(company.name)}</h3>
              </div>
              <span class="status status-${escapeHtml(company.color)}">${counts.total}</span>
            </div>
            <div class="row g-2 mb-3">
              <div class="col">
                <div class="small text-muted">最新</div>
                <div class="h3 text-green mb-0">${counts.fresh}</div>
              </div>
              <div class="col">
                <div class="small text-muted">历史</div>
                <div class="h3 text-purple mb-0">${counts.stale}</div>
              </div>
              <div class="col">
                <div class="small text-muted">异常</div>
                <div class="h3 text-yellow mb-0">${issues}</div>
              </div>
            </div>
            <p class="text-muted small mb-0">${latest ? `${formatDate(latest.published_at)} · ${escapeHtml(latest.title)}` : "本轮暂无新闻"}</p>
          </div>
        </div>
      `;
      return col;
    }),
  );
}

function renderProviderTable(companies, statuses) {
  const rows = companies
    .map((company) => {
      const cells = providerOrder
        .map((provider) => {
          const status = statuses.find(
            (row) => row.company_id === company.id && normalizeProvider(row.provider_type ?? row.source_type) === provider,
          );
          const label = status?.provider_status ?? status?.final_status ?? status?.status ?? "missing";
          return `<td>${statusBadge(label)}</td>`;
        })
        .join("");
      return `<tr><td class="fw-bold">${escapeHtml(company.name)}</td>${cells}</tr>`;
    })
    .join("");

  elements.providerTable.innerHTML = `
    <thead>
      <tr>
        <th>公司</th>
        ${providerOrder.map((provider) => `<th>${escapeHtml(providerLabel(provider))}</th>`).join("")}
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  `;
}

function renderNewsList(items) {
  if (!items.length) {
    elements.newsList.innerHTML = `
      <div class="empty">
        <div class="empty-title">没有匹配当前筛选条件的新闻</div>
        <p class="empty-subtitle text-muted">请调整公司、数据源或新鲜度筛选条件。</p>
      </div>
    `;
    return;
  }

  elements.newsList.replaceChildren(
    ...items.map((item) => {
      const freshness = freshnessState(item);
      const entry = document.createElement("a");
      entry.className = "list-group-item list-group-item-action news-row";
      entry.href = item.url;
      entry.target = "_blank";
      entry.rel = "noreferrer";
      entry.innerHTML = `
        <div class="row align-items-center g-3">
          <div class="col">
            <div class="d-flex flex-wrap gap-2 mb-2">
              <span class="badge bg-blue-lt">${escapeHtml(item.company_name)}</span>
              ${providerBadge(itemProvider(item))}
              ${freshnessBadge(freshness)}
            </div>
            <div class="fw-bold">${escapeHtml(item.title)}</div>
            <div class="text-muted small mt-1">
              ${escapeHtml(item.source?.source_name ?? item.source?.source_id ?? "未知来源")} ·
              ${formatFullDate(item.published_at)}
            </div>
            ${staleDetails(item)}
          </div>
          <div class="col-auto">
            <span class="btn btn-sm btn-outline-primary">打开</span>
          </div>
        </div>
      `;
      return entry;
    }),
  );
}

function renderErrors(statuses) {
  const rows = statuses.filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "";
    return label !== "success" || status.reason || status.error_message;
  });

  if (!rows.length) {
    elements.errorAccordion.innerHTML = `
      <div class="empty">
        <div class="empty-title">没有数据源异常</div>
        <p class="empty-subtitle text-muted">本轮所有数据源均正常返回。</p>
      </div>
    `;
    return;
  }

  elements.errorAccordion.innerHTML = rows
    .map((status, index) => {
      const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
      const provider = normalizeProvider(status.provider_type ?? status.source_type);
      const itemId = `error-${index}`;
      return `
        <div class="accordion-item">
          <h3 class="accordion-header">
            <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#${itemId}">
              <span class="me-2">${escapeHtml(status.company_name ?? status.company_id ?? "--")}</span>
              <span class="me-2 text-muted">${escapeHtml(providerLabel(provider))}</span>
              ${statusBadge(label)}
            </button>
          </h3>
          <div id="${itemId}" class="accordion-collapse collapse" data-bs-parent="#error-accordion">
            <div class="accordion-body">
              <div class="mb-2">
                <div class="text-muted small">原因</div>
                <div>${escapeHtml(status.reason ?? "--")}</div>
              </div>
              <div>
                <div class="text-muted small">错误信息</div>
                <div>${escapeHtml(status.error_message ?? "--")}</div>
              </div>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

function filterItems(items) {
  return items.filter((item) => {
    const companyMatches = state.companyId === "all" || item.company_id === state.companyId;
    const providerMatches = state.provider === "all" || itemProvider(item) === state.provider;
    const freshnessMatches =
      state.freshness === "all" || freshnessState(item).kind === state.freshness;
    return companyMatches && providerMatches && freshnessMatches;
  });
}

function companiesFromItems(items) {
  const seen = new Set();
  const companies = companyOrder.map((id) => ({
    id,
    name: companyMeta[id].name,
    region: companyMeta[id].region,
    color: companyMeta[id].color,
  }));

  companyOrder.forEach((id) => seen.add(id));
  return items.reduce((rows, item) => {
    if (seen.has(item.company_id)) return rows;
    seen.add(item.company_id);
    rows.push({
      id: item.company_id,
      name: companyMeta[item.company_id]?.name ?? item.company_name,
      region: companyMeta[item.company_id]?.region ?? "未知地区",
      color: companyMeta[item.company_id]?.color ?? "secondary",
    });
    return rows;
  }, companies);
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
  if (item.stale === true) return { kind: "stale", label: "历史兜底" };
  return { kind: "fresh", label: "最新" };
}

function freshnessBadge(freshness) {
  if (freshness.kind === "stale") return `<span class="badge bg-purple-lt">${freshness.label}</span>`;
  return `<span class="badge bg-green-lt">${freshness.label}</span>`;
}

function staleDetails(item) {
  if (item.stale !== true) return "";
  return `
    <div class="alert alert-warning mt-2 mb-0 p-2">
      <div><strong>兜底原因:</strong> ${escapeHtml(item.stale_reason ?? "--")}</div>
      <div><strong>兜底时间:</strong> ${escapeHtml(item.stale_as_of ?? "--")}</div>
      <div><strong>来源运行 ID:</strong> ${escapeHtml(item.stale_from_run_id ?? "--")}</div>
    </div>
  `;
}

function providerIssues(statuses, companyId) {
  return statuses.filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
    return status.company_id === companyId && label !== "success";
  }).length;
}

function itemProvider(item) {
  return normalizeProvider(item.source?.source_type ?? item.source?.rank_group ?? "unknown");
}

function normalizeProvider(value) {
  const provider = String(value ?? "unknown");
  return provider === "official_page" ? "official_site" : provider;
}

function providerLabel(provider) {
  return providerLabels[normalizeProvider(provider)] ?? String(provider).replaceAll("_", " ");
}

function providerBadge(provider) {
  return `<span class="badge bg-secondary-lt">${escapeHtml(providerLabel(provider))}</span>`;
}

function statusBadge(status) {
  const value = String(status);
  if (value === "success") return `<span class="badge bg-green-lt">${statusLabel(value)}</span>`;
  if (value === "rate_limited") return `<span class="badge bg-yellow-lt">${statusLabel(value)}</span>`;
  if (value === "failed") return `<span class="badge bg-red-lt">${statusLabel(value)}</span>`;
  if (value.startsWith("skipped")) return `<span class="badge bg-secondary-lt">${statusLabel(value)}</span>`;
  return `<span class="badge bg-secondary-lt">${statusLabel(value)}</span>`;
}

function statusLabel(status) {
  return statusLabels[status] ?? String(status).replaceAll("_", " ");
}

function sortedItems(items) {
  return [...items].sort((a, b) => new Date(b.published_at ?? 0) - new Date(a.published_at ?? 0));
}

function option(value, label) {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = label;
  return element;
}

function arraySummary(value) {
  return Array.isArray(value) && value.length ? value.join(", ") : "无";
}

function formatDate(value) {
  if (!value) return "--";
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
