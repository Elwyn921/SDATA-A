import { loadDashboardData } from "./pipeline-data.js";

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
  timeRange: "latest",
  selectedDate: null,
  visibleLimit: 120,
  result: null,
  items: [],
  archiveIndex: null,
  dailyReport: null,
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
  newsPanelTitle: document.querySelector("#news-panel-title"),
  newsList: document.querySelector("#news-list"),
  timeTabs: document.querySelector("#time-tabs"),
  briefingTitle: document.querySelector("#briefing-title"),
  briefingStatus: document.querySelector("#briefing-status"),
  briefingSummary: document.querySelector("#briefing-summary"),
  briefingStats: document.querySelector("#briefing-stats"),
  briefingHighlights: document.querySelector("#briefing-highlights"),
  volumeCaption: document.querySelector("#volume-caption"),
  volumeSummary: document.querySelector("#volume-summary"),
  volumeChart: document.querySelector("#volume-chart"),
  archiveSummary: document.querySelector("#archive-summary"),
  archiveDays: document.querySelector("#archive-days"),
  providerTable: document.querySelector("#provider-table"),
  errorAccordion: document.querySelector("#error-accordion"),
  diagnosticsSummary: document.querySelector("#diagnostics-summary"),
};

bootstrap();

async function bootstrap() {
  const dashboard = await loadDashboardData();
  state.result = dashboard.result;
  state.items = mergeNewsItems(state.result.items ?? [], dashboard.archiveCatalog?.items ?? []);
  state.archiveIndex = dashboard.archiveIndex;
  state.dailyReport = dashboard.dailyReport;
  state.selectedDate = latestNewsDate(state.items);
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
    state.visibleLimit = 120;
    render();
  });

  elements.resetFilters.addEventListener("click", () => {
    state.groupId = "all";
    state.companyId = "all";
    state.timeRange = "latest";
    state.selectedDate = latestNewsDate(state.items);
    state.visibleLimit = 120;
    elements.companyFilter.value = "all";
    render();
  });
}

function populateFilters() {
  const companies = companiesFromItems(state.items);
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
  const items = sortedItems(state.items);
  const companies = companiesFromItems(items);
  const coveredCompanies = companies.filter((company) => company.total > 0);
  const filteredItems = filterItems(items);

  elements.dataSource.textContent = state.result.__dataSource === "json" ? "生产数据快照" : "示例数据";
  elements.updatedAt.textContent = formatFullDate(
    state.result.generated_at ?? state.result.finished_at ?? state.result.started_at,
  );
  elements.totalCount.textContent = String(items.length);
  elements.companyCount.textContent = String(coveredCompanies.length);
  elements.newsPanelTitle.textContent = newsPanelTitle();

  renderDailyBriefing(items);
  renderVolumeIndex(items);
  renderTimeTabs();
  renderCategoryTabs();
  renderIndustrySections(items);
  renderNewsList(filteredItems);
  renderProviderTable(companies, state.result.fetch_statuses ?? []);
  renderDiagnostics(state.result.fetch_statuses ?? [], items);
}

function renderTimeTabs() {
  const tabs = [
    { id: "latest", name: "最近一天" },
    { id: "week", name: "近 7 天" },
    { id: "archive", name: "历史归档" },
    { id: "all", name: "全部" },
  ];
  elements.timeTabs.replaceChildren(
    ...tabs.map((tab) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = state.timeRange === tab.id && !state.selectedDate ? "active" : "";
      if (tab.id === "latest" && state.selectedDate === latestNewsDate(state.items)) {
        button.className = "active";
      }
      button.textContent = tab.name;
      button.addEventListener("click", () => {
        state.timeRange = tab.id;
        state.selectedDate = tab.id === "latest" ? latestNewsDate(state.items) : null;
        state.visibleLimit = 120;
        render();
      });
      return button;
    }),
  );
}

function renderDailyBriefing(items) {
  const report = state.dailyReport;
  const reportHasSummary = Boolean(report?.executive_summary?.trim());
  const reportIsAi = report?.generation_status === "completed";
  const reportDate = report?.report_date ?? dateKey(report?.generated_at);
  const latestDate = latestNewsDate(items);
  const briefingDate = reportHasSummary && reportDate ? reportDate : latestDate;
  const dayItems = items.filter((item) => dateKey(item.published_at) === briefingDate);
  const companies = new Set(dayItems.map((item) => item.company_id).filter(Boolean));
  const previousDate = addDays(briefingDate, -1);
  const previousCount = items.filter((item) => dateKey(item.published_at) === previousDate).length;
  const change = dayItems.length - previousCount;
  const comparison = previousCount
    ? `，较前一日${change >= 0 ? "增加" : "减少"} ${Math.abs(change)} 条`
    : "";

  elements.briefingTitle.textContent = `${formatDateLabel(briefingDate)}情报简报`;
  elements.briefingStatus.textContent = reportIsAi ? "AI 简报" : "自动简报";
  elements.briefingStatus.className = `briefing-status ${reportIsAi ? "is-ai" : "is-rules"}`;
  elements.briefingSummary.textContent = reportHasSummary
    ? report.executive_summary
    : dayItems.length
      ? `当日收录 ${dayItems.length} 条新闻，覆盖 ${companies.size} 家公司${comparison}。简报按新闻发布时间生成，不再把历史抓取结果标记为最新。`
      : "当日没有收录到新闻，系统保留历史归档供回看。";

  const topCompanies = countBy(dayItems, (item) => companyName(item.company_id, item.company_name))
    .slice(0, 3);
  const stats = [
    ["当日新闻", dayItems.length],
    ["覆盖公司", companies.size],
    ["前一日", previousCount],
    ["高频公司", topCompanies[0]?.[0] ?? "--"],
  ];
  elements.briefingStats.replaceChildren(
    ...stats.map(([label, value]) => {
      const block = document.createElement("div");
      block.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
      return block;
    }),
  );

  const reportHighlights = reportHasSummary
    ? (report.top_news ?? []).filter((item) => item.title).slice(0, 4)
    : dayItems.slice(0, 4);
  elements.briefingHighlights.replaceChildren(
    ...reportHighlights.map((item) => {
      const row = document.createElement("li");
      const link = document.createElement("a");
      link.textContent = item.title;
      link.href = item.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      if (!item.url) link.removeAttribute("target");
      row.append(link);
      return row;
    }),
  );
  if (!reportHighlights.length) {
    const empty = document.createElement("li");
    empty.textContent = "暂无当日重点动态";
    elements.briefingHighlights.append(empty);
  }
}

function renderVolumeIndex(items) {
  const latestDate = latestNewsDate(items);
  const counts = new Map(countBy(items, (item) => dateKey(item.published_at)));
  counts.delete("");
  const days = latestDate
    ? Array.from({ length: 30 }, (_, index) => addDays(latestDate, index - 29))
    : [];
  const values = days.map((date) => ({ date, count: counts.get(date) ?? 0 }));
  const max = Math.max(1, ...values.map((row) => row.count));
  const total = values.reduce((sum, row) => sum + row.count, 0);
  const average = values.length ? (total / values.length).toFixed(1) : "0";

  elements.volumeCaption.textContent = latestDate
    ? `${formatDateLabel(days[0])}—${formatDateLabel(latestDate)} · 按北京时间统计`
    : "暂无可统计的新闻日期";
  elements.volumeSummary.innerHTML = `
    <div><span>最近 30 天</span><strong>${total}</strong></div>
    <div><span>日均</span><strong>${average}</strong></div>
    <div><span>峰值</span><strong>${max}</strong></div>
  `;
  elements.volumeChart.replaceChildren(
    ...values.map((row, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = state.selectedDate === row.date ? "volume-bar is-selected" : "volume-bar";
      button.style.setProperty("--bar-height", `${Math.max(3, (row.count / max) * 100)}%`);
      button.title = `${formatDateLabel(row.date)}：${row.count} 条新闻`;
      button.setAttribute("aria-label", button.title);
      button.innerHTML = `
        <span class="volume-value">${row.count || ""}</span>
        <i></i>
        <span class="volume-date">${index % 5 === 0 || index === values.length - 1 ? row.date.slice(5).replace("-", "/") : ""}</span>
      `;
      button.addEventListener("click", () => selectArchiveDate(row.date));
      return button;
    }),
  );

  const populatedDays = [...counts.entries()]
    .filter(([date]) => date)
    .sort(([a], [b]) => b.localeCompare(a));
  const runs = Array.isArray(state.archiveIndex?.runs) ? state.archiveIndex.runs : [];
  elements.archiveSummary.textContent = `${populatedDays.length} 个新闻日期 · ${runs.length} 次采集快照`;

  const select = document.createElement("select");
  select.className = "archive-select form-select";
  select.setAttribute("aria-label", "选择历史归档日期");
  select.append(option("", "选择日期…"));
  populatedDays.forEach(([date, count]) => select.append(option(date, `${date} · ${count} 条`)));
  select.value = state.selectedDate ?? "";
  select.addEventListener("change", (event) => {
    if (event.target.value) selectArchiveDate(event.target.value);
  });

  const recentButtons = populatedDays.slice(0, 6).map(([date, count]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = state.selectedDate === date ? "archive-day active" : "archive-day";
    button.textContent = `${date.slice(5).replace("-", "/")} · ${count}`;
    button.addEventListener("click", () => selectArchiveDate(date));
    return button;
  });
  elements.archiveDays.replaceChildren(select, ...recentButtons);
}

function selectArchiveDate(date) {
  state.selectedDate = date;
  state.timeRange = date === latestNewsDate(state.items) ? "latest" : "date";
  state.visibleLimit = 120;
  render();
  document.querySelector(".news-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function newsPanelTitle() {
  if (state.selectedDate) return `${formatDateLabel(state.selectedDate)}新闻归档`;
  if (state.timeRange === "week") return "近 7 天新闻";
  if (state.timeRange === "archive") return "历史新闻归档";
  return "全部新闻时间线";
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
        state.visibleLimit = 120;
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
        state.visibleLimit = 120;
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
    state.visibleLimit = 120;
    elements.companyFilter.value = company.id;
    document.querySelector(".news-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    render();
  });
  return card;
}

function renderNewsList(items) {
  const visibleItems = items.slice(0, state.visibleLimit);
  const latestDate = latestNewsDate(state.items);
  elements.visibleCount.textContent = visibleItems.length < items.length
    ? `已显示 ${visibleItems.length} / ${items.length} 条`
    : `已显示 ${items.length} 条`;
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
    ...visibleItems.map((item) => {
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
            ${freshnessBadge(item, latestDate)}
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
  if (visibleItems.length < items.length) {
    const footer = document.createElement("div");
    footer.className = "news-load-more";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-secondary";
    button.textContent = `继续加载（剩余 ${items.length - visibleItems.length} 条）`;
    button.addEventListener("click", () => {
      state.visibleLimit += 120;
      render();
    });
    footer.append(button);
    elements.newsList.append(footer);
  }
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
  const latestDate = latestNewsDate(items);
  const archivedCount = items.filter(
    (item) => daysBetween(dateKey(item.published_at), latestDate) >= 7,
  ).length;
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
  const latestDate = latestNewsDate(state.items);
  return items.filter((item) => {
    const groupMatches = state.groupId === "all" || companyToGroup.get(item.company_id) === state.groupId;
    const companyMatches = state.companyId === "all" || item.company_id === state.companyId;
    const itemDate = dateKey(item.published_at);
    const age = daysBetween(itemDate, latestDate);
    let timeMatches = true;
    if (state.selectedDate) timeMatches = itemDate === state.selectedDate;
    else if (state.timeRange === "week") timeMatches = age >= 0 && age < 7;
    else if (state.timeRange === "archive") timeMatches = age >= 7;
    return groupMatches && companyMatches && timeMatches;
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

function freshnessBadge(item, latestDate) {
  if (item.stale === true) return `<span class="badge stale-badge">待刷新</span>`;
  const age = daysBetween(dateKey(item.published_at), latestDate);
  if (age === 0) return `<span class="badge fresh-badge">当日</span>`;
  if (age > 0 && age < 7) return `<span class="badge recent-badge">${age} 天前</span>`;
  return `<span class="badge archive-badge">历史归档</span>`;
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

function mergeNewsItems(currentItems, archivedItems) {
  const rows = new Map();
  archivedItems.forEach((item) => rows.set(itemIdentity(item), item));
  currentItems.forEach((item) => rows.set(itemIdentity(item), item));
  return [...rows.values()];
}

function itemIdentity(item) {
  const identity = item.id ?? item.url ?? item.title ?? "unknown";
  return `${item.company_id ?? "unknown"}:${identity}`;
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

function dateKey(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function latestNewsDate(items) {
  return items.reduce((latest, item) => {
    const date = dateKey(item.published_at);
    return date > latest ? date : latest;
  }, "");
}

function addDays(date, amount) {
  if (!date) return "";
  const value = new Date(`${date}T12:00:00+08:00`);
  value.setUTCDate(value.getUTCDate() + amount);
  return dateKey(value);
}

function daysBetween(olderDate, newerDate) {
  if (!olderDate || !newerDate) return Number.POSITIVE_INFINITY;
  const older = new Date(`${olderDate}T00:00:00Z`);
  const newer = new Date(`${newerDate}T00:00:00Z`);
  return Math.round((newer - older) / 86_400_000);
}

function formatDateLabel(date) {
  if (!date) return "暂无日期";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Shanghai",
  }).format(new Date(`${date}T12:00:00+08:00`));
}

function countBy(items, keyFunction) {
  const counts = new Map();
  items.forEach((item) => {
    const key = keyFunction(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
