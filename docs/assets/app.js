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

const staleReasonLabels = {
  partial_run_not_updated: "本轮未更新，沿用上一轮结果",
  partial_run_company_empty: "本轮该公司无新结果，沿用上一轮结果",
  current_run_company_empty: "本轮无结果，使用历史数据",
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
  elements.dataSource.parentElement.classList.toggle("is-live", state.result.__dataSource === "json");
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
    ["新闻总数", items.length, "本轮可展示条目", "blue"],
    ["覆盖公司", companies.length, "当前监测对象", "slate"],
    ["最新新闻", counts.fresh, "fresh=true", "green"],
    ["历史兜底", counts.stale, "stale=true", "purple"],
    ["最后更新", formatFullDate(state.result.generated_at), "北京时间", "amber"],
  ];
  elements.kpiCards.replaceChildren(
    ...kpis.map(([label, value, caption, tone]) => {
      const card = document.createElement("article");
      card.className = `kpi-card tone-${tone}`;
      card.innerHTML = `
        <div class="kpi-label">${escapeHtml(label)}</div>
        <div class="kpi-value">${escapeHtml(value)}</div>
        <div class="kpi-caption">${escapeHtml(caption)}</div>
      `;
      return card;
    }),
  );
}

function renderRunStatus(counts) {
  const fallback = state.result.metadata?.stale_fallback ?? {};
  const rows = [
    ["生成时间", formatFullDate(state.result.generated_at ?? state.result.finished_at), "clock"],
    ["历史兜底", fallback.enabled === false ? "已关闭" : "已启用", "shield"],
    ["兜底公司", arraySummary(fallback.fallback_company_ids), "company"],
    ["最新 / 历史", `${fallback.fresh_item_count ?? counts.fresh} / ${fallback.stale_item_count ?? counts.stale}`, "ratio"],
  ];
  elements.runStatus.replaceChildren(
    ...rows.map(([label, value, icon]) => {
      const item = document.createElement("div");
      item.className = "run-status-item";
      item.innerHTML = `
        <span class="run-icon run-icon-${escapeHtml(icon)}"></span>
        <span>
          <span class="run-label">${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </span>
      `;
      return item;
    }),
  );
}

function renderCompanyTabs(companies) {
  const rows = [{ id: "all", name: "全部" }, ...companies];
  elements.companyTabs.replaceChildren(
    ...rows.map((company) => {
      const item = document.createElement("li");
      item.innerHTML = `
        <button class="${state.companyId === company.id ? "active" : ""}" type="button">
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
      const card = document.createElement("article");
      card.className = `company-card company-${company.id}`;
      card.innerHTML = `
        <div class="company-card-top">
          <div>
            <div class="company-region">${escapeHtml(company.region)}</div>
            <h3>${escapeHtml(company.name)}</h3>
          </div>
          <span class="company-count">${counts.total}</span>
        </div>
        <div class="company-metrics">
          <span><em>${counts.fresh}</em> 最新</span>
          <span><em>${counts.stale}</em> 历史</span>
          <span><em>${issues}</em> 异常</span>
        </div>
        <div class="company-latest">
          <span>${latest ? formatDate(latest.published_at) : "--"}</span>
          <p>${latest ? escapeHtml(latest.title) : "本轮暂无新闻"}</p>
        </div>
      `;
      return card;
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
      return `<tr><td class="provider-company">${escapeHtml(company.name)}</td>${cells}</tr>`;
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
      const entry = document.createElement("article");
      entry.className = "news-row";
      entry.tabIndex = 0;
      entry.addEventListener("click", () => window.open(item.url, "_blank", "noopener,noreferrer"));
      entry.addEventListener("keydown", (event) => {
        if (event.key === "Enter") window.open(item.url, "_blank", "noopener,noreferrer");
      });
      entry.href = item.url;
      entry.innerHTML = `
        <div class="news-main">
          <div class="news-badges">
            <span class="news-company">${escapeHtml(item.company_name)}</span>
            ${providerBadge(itemProvider(item))}
            ${freshnessBadge(freshness, item)}
          </div>
          <h3>${escapeHtml(item.title)}</h3>
          <div class="news-meta">
            <span>${escapeHtml(item.source?.source_name ?? item.source?.source_id ?? "未知来源")}</span>
            <span>${formatFullDate(item.published_at)}</span>
          </div>
        </div>
        <span class="open-link">打开</span>
      `;
      const staleTrigger = entry.querySelector(".stale-badge-wrap");
      if (staleTrigger) {
        staleTrigger.addEventListener("click", (event) => event.stopPropagation());
        staleTrigger.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") event.stopPropagation();
        });
      }
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
              <span class="diagnostic-company">${escapeHtml(status.company_name ?? status.company_id ?? "--")}</span>
              <span class="diagnostic-provider">${escapeHtml(providerLabel(provider))}</span>
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
  if (item.stale === true) return { kind: "stale", label: "使用上一轮数据" };
  return { kind: "fresh", label: "最新" };
}

function freshnessBadge(freshness, item) {
  if (freshness.kind === "stale") return staleBadge(item, freshness.label);
  return `<span class="badge bg-green-lt">${freshness.label}</span>`;
}

function staleBadge(item, label) {
  const details = staleTooltipDetails(item);
  return `
    <span class="stale-badge-wrap" tabindex="0" aria-label="${escapeHtml(details.aria)}">
      <span class="badge stale-badge">${escapeHtml(label)}</span>
      <span class="stale-tooltip" role="tooltip">
        <strong>使用历史结果</strong>
        <span>${escapeHtml(details.reason)}</span>
        <span>兜底时间：${escapeHtml(details.asOf)}</span>
        <span>来源运行 ID：${escapeHtml(details.runId)}</span>
      </span>
    </span>
  `;
}

function staleTooltipDetails(item) {
  const reason = staleReasonLabel(item.stale_reason);
  const asOf = formatStaleAsOf(item.stale_as_of);
  const runId = shortRunId(item.stale_from_run_id);
  return {
    reason,
    asOf,
    runId,
    aria: `使用上一轮数据。${reason}。兜底时间：${asOf}。来源运行 ID：${runId}`,
  };
}

function staleReasonLabel(reason) {
  return staleReasonLabels[reason] ?? "使用历史数据";
}

function shortRunId(value) {
  return value ? String(value).slice(0, 8) : "--";
}

function formatStaleAsOf(value) {
  if (!value) return "--";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (match) return `${match[1]}/${match[2]}/${match[3]} ${match[4]}:${match[5]}`;
  return formatFullDate(value);
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
