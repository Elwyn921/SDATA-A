import { loadPipelineResult } from "./pipeline-data.js";

const industryGroups = [
  {
    id: "satellite_platform",
    name: "卫星平台与整星制造",
    description: "整星研制、平台能力与卫星制造企业",
    companies: [
      { id: "galaxyspace", name: "银河航天", region: "中国" },
      { id: "hongqing_technology", name: "蓝箭鸿擎", region: "中国" },
      { id: "minospace", name: "微纳星空", region: "中国" },
    ],
  },
  {
    id: "launch_services",
    name: "运载火箭与发射服务",
    description: "商业火箭、发射服务与运载能力",
    companies: [
      { id: "landspace", name: "蓝箭航天", region: "中国" },
      { id: "space_pioneer", name: "天兵科技", region: "中国" },
      { id: "cas_space", name: "中科宇航", region: "中国" },
      { id: "i_space", name: "星际荣耀", region: "中国" },
      { id: "galactic_energy", name: "星河动力", region: "中国" },
      { id: "yushi_space", name: "宇石空间", region: "中国" },
    ],
  },
  {
    id: "satellite_internet",
    name: "卫星互联网服务",
    description: "星座建设、网络运营与卫星互联网基础设施",
    companies: [
      { id: "yuanxin_satellite", name: "垣信卫星", region: "中国" },
      { id: "china_satnet", name: "中国星网", region: "中国" },
    ],
  },
  {
    id: "global_majors",
    name: "国外大厂",
    description: "海外发射、载人航天与商业航天头部企业",
    companies: [
      { id: "blue_origin", name: "Blue Origin", region: "美国" },
      { id: "spacex", name: "SpaceX", region: "美国" },
    ],
  },
];

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
  skipped_no_secret: "未配置密钥",
  missing: "无记录",
  unknown: "未知",
};

const companyMeta = new Map();
const companyToGroup = new Map();
industryGroups.forEach((group) => {
  group.companies.forEach((company) => {
    companyMeta.set(company.id, { ...company, groupId: group.id, groupName: group.name });
    companyToGroup.set(company.id, group.id);
  });
});

const state = {
  groupId: "all",
  companyId: "all",
  result: null,
};

const elements = {
  dataSource: document.querySelector("#data-source"),
  updatedAt: document.querySelector("#updated-at"),
  totalCount: document.querySelector("#total-count"),
  companyCount: document.querySelector("#company-count"),
  industrySections: document.querySelector("#industry-sections"),
  categoryTabs: document.querySelector("#category-tabs"),
  companyFilter: document.querySelector("#company-filter"),
  resetFilters: document.querySelector("#reset-filters"),
  visibleCount: document.querySelector("#visible-count"),
  newsList: document.querySelector("#news-list"),
  providerTable: document.querySelector("#provider-table"),
  errorAccordion: document.querySelector("#error-accordion"),
  diagnosticsSummary: document.querySelector("#diagnostics-summary"),
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
    if (state.companyId !== "all") {
      state.groupId = companyToGroup.get(state.companyId) ?? "all";
    }
    render();
  });

  elements.resetFilters.addEventListener("click", () => {
    state.groupId = "all";
    state.companyId = "all";
    elements.companyFilter.value = "all";
    render();
  });
}

function populateFilters() {
  const companies = companiesFromItems(state.result.items);
  const knownIds = new Set();

  industryGroups.forEach((group) => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = group.name;
    group.companies.forEach((company) => {
      knownIds.add(company.id);
      optgroup.append(option(company.id, company.name));
    });
    elements.companyFilter.append(optgroup);
  });

  const extraCompanies = companies.filter((company) => !knownIds.has(company.id));
  if (extraCompanies.length) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = "未分类公司";
    extraCompanies.forEach((company) => optgroup.append(option(company.id, company.name)));
    elements.companyFilter.append(optgroup);
  }
}

function render() {
  const items = sortedItems(state.result.items ?? []);
  const companies = companiesFromItems(items);
  const coveredCompanies = companies.filter((company) => company.total > 0);
  const filteredItems = filterItems(items);

  elements.dataSource.textContent = state.result.__dataSource === "json" ? "实时数据" : "示例数据";
  elements.updatedAt.textContent = formatFullDate(
    state.result.generated_at ?? state.result.finished_at ?? state.result.started_at,
  );
  elements.totalCount.textContent = String(items.length);
  elements.companyCount.textContent = String(coveredCompanies.length);
  elements.visibleCount.textContent = `已显示 ${filteredItems.length} 条`;

  renderCategoryTabs();
  renderIndustrySections(items);
  renderNewsList(filteredItems);
  renderProviderTable(companies, state.result.fetch_statuses ?? []);
  renderDiagnostics(state.result.fetch_statuses ?? [], items);
}

function renderCategoryTabs() {
  const rows = [{ id: "all", name: "全部" }, ...industryGroups];
  elements.categoryTabs.replaceChildren(
    ...rows.map((group) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = state.groupId === group.id ? "active" : "";
      button.textContent = group.name;
      button.addEventListener("click", () => {
        state.groupId = group.id;
        state.companyId = "all";
        elements.companyFilter.value = "all";
        render();
      });
      return button;
    }),
  );
}

function renderIndustrySections(items) {
  elements.industrySections.replaceChildren(
    ...industryGroups.map((group) => {
      const groupItems = items.filter((item) => companyToGroup.get(item.company_id) === group.id);
      const covered = group.companies.filter((company) =>
        groupItems.some((item) => item.company_id === company.id),
      ).length;
      const section = document.createElement("section");
      section.className = "industry-section";
      section.innerHTML = `
        <div class="industry-heading">
          <div>
            <span>${covered}/${group.companies.length} 家覆盖</span>
            <h2>${escapeHtml(group.name)}</h2>
            <p>${escapeHtml(group.description)}</p>
          </div>
          <button class="section-filter" type="button">查看该分类</button>
        </div>
        <div class="company-grid"></div>
      `;
      section.querySelector(".section-filter").addEventListener("click", () => {
        state.groupId = group.id;
        state.companyId = "all";
        elements.companyFilter.value = "all";
        document.querySelector(".news-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
        render();
      });

      section.querySelector(".company-grid").replaceChildren(
        ...group.companies.map((company) => companyCard(company, items)),
      );
      return section;
    }),
  );
}

function companyCard(company, items) {
  const companyItems = sortedItems(items.filter((item) => item.company_id === company.id));
  const latest = companyItems[0];
  const issues = providerIssues(state.result.fetch_statuses ?? [], company.id);
  const card = document.createElement("article");
  card.className = "company-card";
  card.innerHTML = `
    <div class="company-card-top">
      <div>
        <span>${escapeHtml(company.region)}</span>
        <h3>${escapeHtml(company.name)}</h3>
      </div>
      <strong>${companyItems.length}</strong>
    </div>
    <p>${latest ? escapeHtml(latest.title) : "暂无新闻"}</p>
    <div class="company-card-foot">
      <span>${latest ? formatFullDate(latest.published_at) : "--"}</span>
      <span>${issues ? `${issues} 个异常` : "数据源正常"}</span>
    </div>
  `;
  card.addEventListener("click", () => {
    state.companyId = company.id;
    state.groupId = companyToGroup.get(company.id) ?? "all";
    elements.companyFilter.value = company.id;
    document.querySelector(".news-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    render();
  });
  return card;
}

function renderNewsList(items) {
  if (!items.length) {
    elements.newsList.innerHTML = `
      <div class="empty">
        <div class="empty-title">没有匹配当前筛选条件的新闻</div>
        <p class="empty-subtitle text-muted">请调整产业链分类或公司筛选。</p>
      </div>
    `;
    return;
  }

  elements.newsList.replaceChildren(
    ...items.map((item) => {
      const entry = document.createElement("article");
      entry.className = "news-row";
      entry.tabIndex = 0;
      entry.addEventListener("click", () => window.open(item.url, "_blank", "noopener,noreferrer"));
      entry.addEventListener("keydown", (event) => {
        if (event.key === "Enter") window.open(item.url, "_blank", "noopener,noreferrer");
      });
      entry.innerHTML = `
        <div class="news-main">
          <div class="news-badges">
            <span class="news-company">${escapeHtml(companyName(item.company_id, item.company_name))}</span>
            <span class="news-sector">${escapeHtml(groupNameForCompany(item.company_id))}</span>
            ${providerBadge(itemProvider(item))}
            ${freshnessBadge(item)}
          </div>
          <h3>${escapeHtml(item.title)}</h3>
          <div class="news-meta">
            <span>${escapeHtml(item.source?.source_name ?? item.source?.source_id ?? "未知来源")}</span>
            <span>${formatFullDate(item.published_at)}</span>
          </div>
        </div>
        <span class="open-link">打开</span>
      `;
      return entry;
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

function renderDiagnostics(statuses, items) {
  const issueRows = statuses.filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "";
    return label !== "success" || status.reason || status.error_message;
  });
  const archivedCount = items.filter((item) => item.stale === true).length;
  elements.diagnosticsSummary.textContent =
    `${issueRows.length} 个数据源异常，${archivedCount} 条归档新闻`;

  if (!issueRows.length) {
    elements.errorAccordion.innerHTML = `
      <div class="diagnostic-empty">本轮未发现数据源访问异常。</div>
    `;
    return;
  }

  elements.errorAccordion.innerHTML = issueRows
    .map((status) => {
      const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
      const provider = normalizeProvider(status.provider_type ?? status.source_type);
      return `
        <details class="diagnostic-item">
          <summary>
            <span>${escapeHtml(companyName(status.company_id, status.company_name))}</span>
            <span>${escapeHtml(providerLabel(provider))}</span>
            ${statusBadge(label)}
          </summary>
          <div>
            <p><strong>原始状态</strong>${escapeHtml(label)}</p>
            <p><strong>原因</strong>${escapeHtml(status.reason ?? "--")}</p>
            <p><strong>错误信息</strong>${escapeHtml(status.error_message ?? "--")}</p>
          </div>
        </details>
      `;
    })
    .join("");
}

function filterItems(items) {
  return items.filter((item) => {
    const groupMatches = state.groupId === "all" || companyToGroup.get(item.company_id) === state.groupId;
    const companyMatches = state.companyId === "all" || item.company_id === state.companyId;
    return groupMatches && companyMatches;
  });
}

function companiesFromItems(items) {
  const rows = new Map();

  industryGroups.forEach((group) => {
    group.companies.forEach((company) => {
      rows.set(company.id, {
        id: company.id,
        name: company.name,
        region: company.region,
        groupId: group.id,
        groupName: group.name,
        total: 0,
      });
    });
  });

  items.forEach((item) => {
    const id = item.company_id;
    if (!rows.has(id)) {
      rows.set(id, {
        id,
        name: item.company_name ?? id,
        region: "未知地区",
        groupId: "uncategorized",
        groupName: "未分类",
        total: 0,
      });
    }
    rows.get(id).total += 1;
  });

  return [...rows.values()];
}

function providerIssues(statuses, companyId) {
  return statuses.filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
    return status.company_id === companyId && label !== "success";
  }).length;
}

function companyName(companyId, fallback) {
  return companyMeta.get(companyId)?.name ?? fallback ?? companyId ?? "未知公司";
}

function groupNameForCompany(companyId) {
  return companyMeta.get(companyId)?.groupName ?? "未分类";
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
  return `<span class="badge provider-badge">${escapeHtml(providerLabel(provider))}</span>`;
}

function freshnessBadge(item) {
  if (item.stale === true) return `<span class="badge archive-badge">归档</span>`;
  return `<span class="badge fresh-badge">最新</span>`;
}

function statusBadge(status) {
  const value = String(status);
  const label = statusLabels[value] ?? value.replaceAll("_", " ");
  if (value === "success") return `<span class="badge status-success">${escapeHtml(label)}</span>`;
  if (value === "rate_limited") return `<span class="badge status-rate">${escapeHtml(label)}</span>`;
  if (value === "failed") return `<span class="badge status-failed">${escapeHtml(label)}</span>`;
  if (value.startsWith("skipped")) return `<span class="badge status-skipped">${escapeHtml(label)}</span>`;
  return `<span class="badge status-missing">${escapeHtml(label)}</span>`;
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
