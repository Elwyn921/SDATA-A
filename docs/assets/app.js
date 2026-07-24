import {
  loadDashboardData,
  loadDeferredDashboardData,
} from "./pipeline-data.js";

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

const providerOrder = [
  "rss",
  "official_site",
  "spaceflight_news",
  "gdelt",
  "serpapi",
  "brave_news",
  "newsapi",
];
const providerLabels = {
  rss: "RSS",
  official_site: "官网页面",
  official_page: "官网页面",
  gdelt: "GDELT",
  spaceflight_news: "航天聚合",
  serpapi: "SerpApi",
  brave_news: "Brave",
  newsapi: "NewsAPI",
  search_api: "搜索补充",
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
const eventTypeLabels = {
  all: "全部事件",
  launch: "发射与试验",
  financing: "融资",
  order: "订单与合同",
  regulation: "监管与政策",
  market: "股价与资本市场",
  partnership: "合作",
  product: "产品与产能",
  corporate: "公司治理",
  other: "其他动态",
};
const eventTypeColors = {
  launch: "#2878d0",
  financing: "#7c5ce7",
  order: "#d88a1d",
  regulation: "#ce4d68",
  market: "#d45f43",
  partnership: "#2f9b88",
  product: "#3d8f5b",
  corporate: "#68788f",
  other: "#9aa6b7",
};
const sectorColors = {
  satellite_platform: "#3178c6",
  launch_services: "#7b61d1",
  satellite_internet: "#18a18b",
  global_majors: "#e0893d",
  uncategorized: "#9aa6b7",
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
  eventVisibleLimit: 40,
  eventType: "all",
  workspaceView: initialWorkspaceView(),
  result: null,
  items: [],
  events: [],
  archiveIndex: null,
  dailyIndex: null,
  dailyReport: null,
  indexSnapshot: null,
  versionToken: "",
  deferredDataLoaded: false,
  deferredDataLoading: null,
  deferredDataError: false,
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
  qualityGateSummary: document.querySelector("#quality-gate-summary"),
  eventSummary: document.querySelector("#event-summary"),
  eventCompanyFilter: document.querySelector("#event-company-filter"),
  eventTypeTabs: document.querySelector("#event-type-tabs"),
  eventTimeline: document.querySelector("#event-timeline"),
  indexAsOf: document.querySelector("#index-as-of"),
  indexSourceStatus: document.querySelector("#index-source-status"),
  newsIndexValue: document.querySelector("#news-index-value"),
  newsIndexGauge: document.querySelector("#news-index-gauge"),
  newsIndexHistory: document.querySelector("#news-index-history"),
  newsIndexLabel: document.querySelector("#news-index-label"),
  newsIndexMethod: document.querySelector("#news-index-method"),
  newsIndexMetrics: document.querySelector("#news-index-metrics"),
  chinaIndexName: document.querySelector("#china-index-name"),
  chinaIndexValue: document.querySelector("#china-index-value"),
  chinaIndexChange: document.querySelector("#china-index-change"),
  chinaIndexMeta: document.querySelector("#china-index-meta"),
  chinaMarketBreadth: document.querySelector("#china-market-breadth"),
  chinaStockList: document.querySelector("#china-stock-list"),
  usIndexName: document.querySelector("#us-index-name"),
  usIndexValue: document.querySelector("#us-index-value"),
  usIndexChange: document.querySelector("#us-index-change"),
  usIndexMeta: document.querySelector("#us-index-meta"),
  usMarketBreadth: document.querySelector("#us-market-breadth"),
  usStockList: document.querySelector("#us-stock-list"),
  indexDisclaimer: document.querySelector("#index-disclaimer"),
  signalAsOf: document.querySelector("#signal-as-of"),
  sectorSignalTotal: document.querySelector("#sector-signal-total"),
  sectorDonut: document.querySelector("#sector-donut"),
  sectorLegend: document.querySelector("#sector-legend"),
  sourceSignalTotal: document.querySelector("#source-signal-total"),
  sourceSignalBars: document.querySelector("#source-signal-bars"),
  companyHeatmap: document.querySelector("#company-heatmap"),
  eventVisualTotal: document.querySelector("#event-visual-total"),
  eventTypeChart: document.querySelector("#event-type-chart"),
  eventCompanyChart: document.querySelector("#event-company-chart"),
  eventHighImportance: document.querySelector("#event-high-importance"),
  eventImportanceChart: document.querySelector("#event-importance-chart"),
  workspaceTabs: [...document.querySelectorAll("[data-workspace-tab]")],
  workspaceSections: [...document.querySelectorAll("[data-workspace-view]")],
  workspaceOverviewCount: document.querySelector("#workspace-overview-count"),
  workspaceCompanyCount: document.querySelector("#workspace-company-count"),
  workspaceEventCount: document.querySelector("#workspace-event-count"),
  workspaceNewsCount: document.querySelector("#workspace-news-count"),
  workspaceDiagnosticCount: document.querySelector("#workspace-diagnostic-count"),
  workspaceContextLabel: document.querySelector("#workspace-context-label"),
  workspaceContextMeta: document.querySelector("#workspace-context-meta"),
};

bootstrap();

async function bootstrap() {
  try {
    const dashboard = await loadDashboardData();
    state.result = dashboard.result;
    state.items = mergeNewsItems(state.result.items ?? [], []);
    state.archiveIndex = dashboard.archiveIndex;
    state.dailyIndex = dashboard.dailyIndex;
    state.dailyReport = dashboard.dailyReport;
    state.indexSnapshot = dashboard.indexSnapshot;
    state.versionToken = dashboard.versionToken;
    state.selectedDate = latestNewsDate(state.items);
    populateFilters();
    bindEvents();
    activateWorkspaceView(state.workspaceView, { updateHash: false, render: false });
    render();
    scheduleDeferredDataLoad();
  } catch (error) {
    renderDataLoadError(error);
  }
}

function scheduleDeferredDataLoad() {
  const load = () => {
    void ensureDeferredDataLoaded();
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(load, { timeout: 1800 });
  } else {
    window.setTimeout(load, 350);
  }
}

async function ensureDeferredDataLoaded() {
  if (state.deferredDataLoaded) return;
  if (state.deferredDataLoading) return state.deferredDataLoading;
  state.deferredDataLoading = loadDeferredDashboardData({
    versionToken: state.versionToken,
  })
    .then((dashboard) => {
      state.items = mergeNewsItems(
        state.result.items ?? [],
        dashboard.archiveCatalog?.items ?? [],
      );
      state.events = Array.isArray(dashboard.eventTimeline?.events)
        ? dashboard.eventTimeline.events
        : [];
      state.deferredDataLoaded = true;
      state.deferredDataError = false;
      render();
    })
    .catch((error) => {
      console.warn("Deferred dashboard data load failed", error);
      state.deferredDataError = true;
      elements.dataSource.textContent = "最新数据可用，历史归档暂不可用";
    })
    .finally(() => {
      state.deferredDataLoading = null;
    });
  return state.deferredDataLoading;
}

function renderDataLoadError(error) {
  console.error("Dashboard data load failed", error);
  elements.dataSource.textContent = "数据暂不可用";
  elements.updatedAt.textContent = "--";
  elements.totalCount.textContent = "--";
  elements.companyCount.textContent = "--";
  elements.workspaceSections.forEach((section) => {
    section.hidden = true;
  });
  const panel = document.createElement("section");
  panel.className = "data-load-error";
  panel.innerHTML = `
    <div>
      <span>数据连接状态</span>
      <h2>当前数据暂时无法载入</h2>
      <p>页面不会使用模拟内容替代正式数据。请稍后重新加载，或检查数据文件是否已完成发布。</p>
    </div>
    <button type="button" class="btn btn-primary">重新加载</button>
  `;
  panel.querySelector("button").addEventListener("click", () => window.location.reload());
  document.querySelector(".workspace-nav")?.after(panel);
}

function bindEvents() {
  elements.workspaceTabs.forEach((button) => {
    button.addEventListener("click", () => {
      activateWorkspaceView(button.dataset.workspaceTab, { scroll: true });
    });
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const currentIndex = elements.workspaceTabs.indexOf(button);
      let nextIndex = currentIndex;
      if (event.key === "ArrowLeft") {
        nextIndex = (currentIndex - 1 + elements.workspaceTabs.length) % elements.workspaceTabs.length;
      } else if (event.key === "ArrowRight") {
        nextIndex = (currentIndex + 1) % elements.workspaceTabs.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = elements.workspaceTabs.length - 1;
      }
      const nextButton = elements.workspaceTabs[nextIndex];
      activateWorkspaceView(nextButton.dataset.workspaceTab);
      nextButton.focus();
    });
  });

  window.addEventListener("hashchange", () => {
    activateWorkspaceView(initialWorkspaceView(), { updateHash: false });
  });

  elements.companyFilter.addEventListener("change", (event) => {
    selectCompany(event.target.value);
  });

  elements.eventCompanyFilter.addEventListener("change", (event) => {
    selectCompany(event.target.value);
  });

  elements.resetFilters.addEventListener("click", () => {
    state.groupId = "all";
    state.companyId = "all";
    state.timeRange = "latest";
    state.selectedDate = latestNewsDate(state.items);
    state.visibleLimit = 120;
    state.eventVisibleLimit = 40;
    state.eventType = "all";
    elements.companyFilter.value = "all";
    elements.eventCompanyFilter.value = "all";
    render();
  });
}

function initialWorkspaceView() {
  const match = window.location.hash.match(/(?:^#|&)view=([a-z-]+)/);
  const candidate = match?.[1] ?? "overview";
  return ["overview", "companies", "events", "news", "diagnostics"].includes(candidate)
    ? candidate
    : "overview";
}

function activateWorkspaceView(view, options = {}) {
  const resolved = ["overview", "companies", "events", "news", "diagnostics"].includes(view)
    ? view
    : "overview";
  state.workspaceView = resolved;
  elements.workspaceTabs.forEach((button) => {
    const active = button.dataset.workspaceTab === resolved;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  elements.workspaceSections.forEach((section) => {
    section.hidden = section.dataset.workspaceView !== resolved;
  });
  if (options.updateHash !== false) {
    history.replaceState(null, "", `#view=${resolved}`);
  }
  renderWorkspaceContext();
  if (["companies", "events", "news"].includes(resolved)) {
    void ensureDeferredDataLoaded();
  }
  if (state.result && options.render !== false) {
    render();
  }
  if (options.scroll) {
    document.querySelector(".workspace-nav")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }
}

function renderWorkspaceContext() {
  const labels = {
    overview: ["今日概览", "日报、新闻趋势、产业结构与市场表现"],
    companies: ["公司动态", "按产业链查看公司覆盖与近期活跃度"],
    events: ["公司事件", "把零散报道聚合成连续事件"],
    news: ["新闻资料", "按日期、分类和公司检索全部新闻"],
    diagnostics: ["数据说明", "来源覆盖、质量筛选与运行记录"],
  };
  const [label, meta] = labels[state.workspaceView] ?? labels.overview;
  elements.workspaceContextLabel.textContent = label;
  elements.workspaceContextMeta.textContent = meta;
}

function selectCompany(companyId) {
  state.companyId = companyId;
  state.eventType = "all";
  if (state.companyId !== "all") {
    state.groupId = companyToGroup.get(state.companyId) ?? "all";
  }
  state.visibleLimit = 120;
  state.eventVisibleLimit = 40;
  elements.companyFilter.value = companyId;
  elements.eventCompanyFilter.value = companyId;
  render();
}

function populateFilters() {
  const companies = companiesFromItems(state.items);
  [elements.companyFilter, elements.eventCompanyFilter].forEach((select) => {
    const knownIds = new Set();
    industryGroups.forEach((group) => {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.name;
      group.companies.forEach((company) => {
        knownIds.add(company.id);
        optgroup.append(option(company.id, company.name));
      });
      select.append(optgroup);
    });
    const extraCompanies = companies.filter((company) => !knownIds.has(company.id));
    if (extraCompanies.length) {
      const optgroup = document.createElement("optgroup");
      optgroup.label = "未分类公司";
      extraCompanies.forEach((company) => optgroup.append(option(company.id, company.name)));
      select.append(optgroup);
    }
  });
}

function render() {
  const items = sortedItems(state.items);
  const companies = companiesFromItems(items);
  const coveredCompanies = companies.filter((company) => company.total > 0);
  const filteredItems = filterItems(items);

  elements.dataSource.textContent =
    state.result.__dataSource === "json" ? "数据更新完成" : "演示数据（非正式）";
  elements.updatedAt.textContent = formatFullDate(
    state.result.generated_at ?? state.result.finished_at ?? state.result.started_at,
  );
  elements.totalCount.textContent = String(items.length);
  elements.companyCount.textContent = String(coveredCompanies.length);
  elements.newsPanelTitle.textContent = newsPanelTitle();
  const issueCount = (state.result.fetch_statuses ?? []).filter((status) => {
    const label = status.provider_status ?? status.final_status ?? status.status ?? "";
    return label !== "success" || status.reason || status.error_message;
  }).length;
  elements.workspaceCompanyCount.textContent = String(coveredCompanies.length);
  elements.workspaceOverviewCount.textContent = "4";
  elements.workspaceEventCount.textContent = String(state.events.length);
  elements.workspaceNewsCount.textContent = String(items.length);
  elements.workspaceDiagnosticCount.textContent = String(issueCount);
  renderWorkspaceContext();

  if (state.workspaceView === "overview") {
    renderDailyBriefing(items);
    renderIndexOverview();
    renderSignalOverview(items);
    renderVolumeIndex(items);
  } else if (state.workspaceView === "companies") {
    renderIndustrySections(items);
  } else if (state.workspaceView === "events") {
    renderEventTimeline();
  } else if (state.workspaceView === "news") {
    renderTimeTabs();
    renderCategoryTabs();
    renderNewsList(filteredItems);
  } else if (state.workspaceView === "diagnostics") {
    renderProviderTable(companies, state.result.fetch_statuses ?? []);
    renderQualityGate();
    renderDiagnostics(state.result.fetch_statuses ?? [], items);
  }
}

function renderIndexOverview() {
  const snapshot = state.indexSnapshot;
  if (!snapshot) {
    elements.indexAsOf.textContent = "指数数据尚未生成";
    elements.indexSourceStatus.textContent = "等待刷新";
    elements.newsIndexValue.textContent = "--";
    elements.newsIndexGauge.style.setProperty("--gauge-progress", "0%");
    elements.newsIndexGauge.setAttribute("aria-label", "新闻活跃度指数暂不可用");
    elements.newsIndexHistory.replaceChildren();
    renderMarketIndex(null, "china");
    renderMarketIndex(null, "united_states");
    return;
  }

  const news = snapshot.news_activity ?? {};
  const source = snapshot.market_data_source ?? {};
  elements.indexAsOf.textContent =
    `${formatDateLabel(snapshot.as_of_date)} · ${news.is_partial_day ? "当日持续累计" : "当日已归档"}`;
  elements.indexSourceStatus.textContent =
    source.status === "current"
      ? `${source.source_name ?? "行情源"} · ${source.quoted_instruments ?? 0}/${source.expected_instruments ?? 0}`
      : "行情数据更新稍有延迟";
  elements.indexSourceStatus.className =
    `index-source-status ${source.status === "current" ? "is-current" : "is-stale"}`;
  const newsIndexValue = Number(news.index_value);
  const hasNewsIndex = Number.isFinite(newsIndexValue);
  elements.newsIndexValue.textContent = hasNewsIndex ? newsIndexValue.toFixed(1) : "--";
  elements.newsIndexGauge.style.setProperty(
    "--gauge-progress",
    `${hasNewsIndex ? Math.min(100, Math.max(0, newsIndexValue / 2)) : 0}%`,
  );
  elements.newsIndexGauge.style.setProperty("--gauge-color", newsIndexColor(newsIndexValue));
  elements.newsIndexGauge.setAttribute(
    "aria-label",
    hasNewsIndex
      ? `新闻活跃度指数 ${newsIndexValue.toFixed(1)}，${news.heat_label ?? "暂无评级"}`
      : "新闻活跃度指数暂不可用",
  );
  elements.newsIndexLabel.textContent = news.heat_label ?? "基线不足";
  elements.newsIndexLabel.className = `index-change ${newsIndexClass(news.index_value)}`;
  elements.newsIndexMethod.textContent =
    `${news.methodology ?? "过去 30 个自然日日均为 100"}${news.is_partial_day ? "；今日尚未结束" : ""}`;
  const newsMetrics = [
    ["今日新闻", `${news.news_count ?? 0} 条`],
    ["30 日日均", `${news.baseline_average ?? 0} 条`],
    ["基准", String(news.base_value ?? 100)],
  ];
  elements.newsIndexMetrics.replaceChildren(
    ...newsMetrics.map(([label, value]) => {
      const block = document.createElement("div");
      block.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
      return block;
    }),
  );
  renderNewsIndexHistory(news);

  renderMarketIndex(snapshot.markets?.china, "china");
  renderMarketIndex(snapshot.markets?.united_states, "united_states");
  elements.indexDisclaimer.textContent =
    source.delay_notice ??
    "中国航天航空指数来自东方财富；美国板块为等权篮子。行情可能延迟，不构成投资建议。";
}

function renderMarketIndex(market, sectorId) {
  const isChina = sectorId === "china";
  const nameElement = isChina ? elements.chinaIndexName : elements.usIndexName;
  const valueElement = isChina ? elements.chinaIndexValue : elements.usIndexValue;
  const changeElement = isChina ? elements.chinaIndexChange : elements.usIndexChange;
  const metaElement = isChina ? elements.chinaIndexMeta : elements.usIndexMeta;
  const breadthElement = isChina ? elements.chinaMarketBreadth : elements.usMarketBreadth;
  const listElement = isChina ? elements.chinaStockList : elements.usStockList;
  if (!market) {
    nameElement.textContent = isChina ? "东方财富航天航空指数" : "美国航空航天篮子";
    valueElement.textContent = "--";
    valueElement.className = "";
    changeElement.textContent = "--";
    changeElement.className = "index-change is-flat";
    metaElement.textContent = "等待行情数据";
    breadthElement.innerHTML = '<div class="market-breadth-empty">涨跌分布暂不可用</div>';
    listElement.innerHTML = '<div class="stock-list-empty">暂无股票行情</div>';
    return;
  }

  const basketChange = market.basket_change_pct ?? market.change_pct;
  const quoteTimes = (market.members ?? [])
    .map((member) => member.source_timestamp)
    .filter(Boolean)
    .sort();
  if (isChina) {
    const indexIsAvailable =
      market.index_value != null &&
      ["current", "stale_previous"].includes(market.index_status);
    nameElement.textContent = market.index_name
      ? `东方财富${market.index_name}`
      : "东方财富航天航空指数";
    valueElement.textContent = indexIsAvailable
      ? formatMarketPrice(market.index_value)
      : "--";
    valueElement.className = "";
    changeElement.textContent = indexIsAvailable
      ? formatSignedPct(market.index_change_pct)
      : "指数暂不可用";
    changeElement.className = `index-change ${
      indexIsAvailable ? changeClass(market.index_change_pct) : "is-flat"
    }`;
    const indexTime = market.index_source_timestamp
      ? ` · ${market.index_source_timestamp}`
      : "";
    const staleLabel = market.index_status === "stale_previous" ? " · 上次可用" : "";
    metaElement.textContent =
      `${market.index_source_name ?? "东方财富"} · ` +
      `${market.index_code ?? "BK0480"}${indexTime}${staleLabel}`;
  } else {
    nameElement.textContent = market.basket_name ?? "美国航空航天篮子";
    valueElement.textContent = formatSignedPct(basketChange);
    valueElement.className = changeClass(basketChange);
    changeElement.textContent =
      `${market.advancers ?? 0} 涨 / ${market.decliners ?? 0} 跌`;
    changeElement.className = "index-change is-flat";
    metaElement.textContent =
      `当日等权涨跌 · 行情 ${market.quoted_member_count ?? 0}/${market.member_count ?? 0} 只` +
      `${quoteTimes.length ? ` · ${quoteTimes.at(-1)}` : ""}`;
  }
  const advancers = Number(market.advancers ?? 0);
  const decliners = Number(market.decliners ?? 0);
  const unchanged = Number(market.unchanged ?? 0);
  breadthElement.innerHTML = `
    <div class="market-breadth-labels">
      <span><i class="is-up"></i><strong>${advancers}</strong> 上涨</span>
      <span><i class="is-flat"></i><strong>${unchanged}</strong> 平盘</span>
      <span><i class="is-down"></i><strong>${decliners}</strong> 下跌</span>
    </div>
    <div class="market-breadth-track" role="img" aria-label="上涨 ${advancers} 只，平盘 ${unchanged} 只，下跌 ${decliners} 只">
      <i class="is-up"></i><i class="is-flat"></i><i class="is-down"></i>
    </div>
  `;
  const breadthSegments = [...breadthElement.querySelectorAll(".market-breadth-track i")];
  [advancers, unchanged, decliners].forEach((value, index) => {
    breadthSegments[index].style.flexGrow = String(value);
    breadthSegments[index].hidden = value === 0;
  });
  const members = Array.isArray(market.members) ? market.members : [];
  const maxMove = Math.max(
    1,
    ...members.map((member) => Math.abs(Number(member.change_pct) || 0)),
  );
  listElement.replaceChildren(
    ...members.map((member) => {
      const row = document.createElement("div");
      row.className = "stock-row";
      const price = member.price == null ? "--" : formatMarketPrice(member.price);
      const move = Number(member.change_pct);
      const moveWidth = Number.isFinite(move) ? Math.max(2, Math.abs(move) / maxMove * 100) : 0;
      row.innerHTML = `
        <div class="stock-identity"><strong>${escapeHtml(member.name)}</strong><span>${escapeHtml(member.ticker)}</span></div>
        <span class="stock-price">${escapeHtml(price)}</span>
        <div class="stock-move">
          <span class="stock-change ${changeClass(member.change_pct)}">${escapeHtml(formatSignedPct(member.change_pct))}</span>
          <i aria-hidden="true"><b class="${changeClass(member.change_pct)}" style="width:${moveWidth}%"></b></i>
        </div>
      `;
      return row;
    }),
  );
}

function renderNewsIndexHistory(news) {
  const history = Array.isArray(news.history) ? news.history.slice(-60) : [];
  if (!history.length) {
    elements.newsIndexHistory.innerHTML = '<span class="visual-empty">暂无历史指数</span>';
    return;
  }
  const maxObserved = Math.max(
    0,
    ...history.map((row) => Number(row.index_value) || 0),
  );
  const scaleMax = Math.max(200, Math.min(400, Math.ceil(maxObserved / 50) * 50));
  elements.newsIndexHistory.style.setProperty(
    "--baseline-position",
    `${Math.min(100, 100 / scaleMax * 100)}%`,
  );
  elements.newsIndexHistory.replaceChildren(
    ...history.map((row) => {
      const value = Number(row.index_value) || 0;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `mini-index-bar ${newsIndexClass(value)}`;
      button.style.setProperty(
        "--bar-height",
        `${Math.max(2, Math.min(100, value / scaleMax * 100))}%`,
      );
      button.title =
        `${formatDateLabel(row.date)}：指数 ${value.toFixed(1)}，${row.news_count ?? 0} 条新闻`;
      button.setAttribute("aria-label", button.title);
      button.innerHTML = "<i></i>";
      button.addEventListener("click", () => selectArchiveDate(row.date));
      return button;
    }),
  );
}

function newsIndexClass(value) {
  if (value == null) return "is-flat";
  if (value >= 120) return "is-positive";
  if (value < 80) return "is-negative";
  return "is-flat";
}

function newsIndexColor(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "#8b98aa";
  if (number >= 180) return "#e66f3d";
  if (number >= 120) return "#8a63d2";
  if (number < 80) return "#71839b";
  return "#2878d0";
}

function changeClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "is-flat";
  return number > 0 ? "is-positive" : "is-negative";
}

function formatSignedPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatMarketPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number >= 1000
    ? number.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : number.toFixed(2);
}

function renderQualityGate() {
  const gate = state.result.metadata?.quality_gate;
  if (!gate) {
    elements.qualityGateSummary.innerHTML = `
      <div><span>质量门控</span><strong>等待下一轮数据刷新</strong></div>
    `;
    return;
  }
  const rows = [
    ["候选", gate.input_count ?? 0],
    ["已发布", gate.published_count ?? 0],
    ["观察区", gate.watchlist_count ?? 0],
    ["已拒绝", gate.rejected_count ?? 0],
    ["重复项", gate.duplicate_count ?? 0],
    ["中国宽松纳入", gate.china_relaxed_published_count ?? 0],
  ];
  elements.qualityGateSummary.replaceChildren(
    ...rows.map(([label, value]) => {
      const row = document.createElement("div");
      row.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
      return row;
    }),
  );
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
        state.eventVisibleLimit = 40;
        render();
      });
      return button;
    }),
  );
}

function renderDailyBriefing(items) {
  const report = state.dailyReport;
  const reportDate = report?.report_date ?? dateKey(report?.generated_at);
  const latestDate = latestNewsDate(items);
  const reportMatchesCurrentRun =
    Boolean(report?.executive_summary?.trim()) &&
    report?.source_run_id === state.result.run_id &&
    reportDate === latestDate;
  const reportIsAi =
    reportMatchesCurrentRun && report?.generation_status === "completed";
  const briefingDate = latestDate || reportDate;
  const dayItems = items.filter((item) => dateKey(item.published_at) === briefingDate);
  const companies = new Set(dayItems.map((item) => item.company_id).filter(Boolean));
  const previousDate = addDays(briefingDate, -1);
  const previousCount = items.filter((item) => dateKey(item.published_at) === previousDate).length;
  const change = dayItems.length - previousCount;
  const comparison = previousCount
    ? `，较前一日${change >= 0 ? "增加" : "减少"} ${Math.abs(change)} 条`
    : "";

  elements.briefingTitle.textContent = `${formatDateLabel(briefingDate)}产业动态日报`;
  elements.briefingStatus.textContent = reportIsAi
    ? "内容已更新"
    : reportMatchesCurrentRun
      ? "自动汇总"
      : "实时汇总";
  elements.briefingStatus.className = `briefing-status ${reportIsAi ? "is-ai" : "is-rules"}`;
  elements.briefingSummary.textContent = reportMatchesCurrentRun
    ? report.executive_summary
    : dayItems.length
      ? `当日收录 ${dayItems.length} 条新闻，覆盖 ${companies.size} 家公司${comparison}。日报按新闻发布时间生成，并保留完整历史记录。`
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

  const reportHighlights = reportMatchesCurrentRun
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

function renderSignalOverview(items) {
  const latestDate = state.dailyIndex?.days?.[0]?.date ?? latestNewsDate(items);
  const recentItems = items.filter((item) => {
    const age = daysBetween(dateKey(item.published_at), latestDate);
    return age >= 0 && age < 30;
  });
  elements.signalAsOf.textContent = latestDate
    ? `截至 ${formatDateLabel(latestDate)} · 基于近 30 日已收录新闻`
    : "暂无可分析的新闻记录";

  const sectorRows = industryGroups
    .map((group) => ({
      id: group.id,
      name: group.name,
      count: recentItems.filter((item) => companyToGroup.get(item.company_id) === group.id).length,
      color: sectorColors[group.id],
    }))
    .filter((row) => row.count > 0);
  const categorizedTotal = sectorRows.reduce((sum, row) => sum + row.count, 0);
  const uncategorizedCount = Math.max(0, recentItems.length - categorizedTotal);
  if (uncategorizedCount) {
    sectorRows.push({
      id: "uncategorized",
      name: "其他",
      count: uncategorizedCount,
      color: sectorColors.uncategorized,
    });
  }
  elements.sectorSignalTotal.textContent = `${recentItems.length} 篇`;
  const gradientSegments = [];
  let cursor = 0;
  sectorRows.forEach((row) => {
    const start = cursor;
    cursor += recentItems.length ? row.count / recentItems.length * 100 : 0;
    gradientSegments.push(`${row.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`);
  });
  elements.sectorDonut.style.background = gradientSegments.length
    ? `conic-gradient(${gradientSegments.join(",")})`
    : "#e7edf5";
  elements.sectorDonut.setAttribute(
    "aria-label",
    sectorRows.length
      ? sectorRows.map((row) => `${row.name} ${row.count} 篇`).join("，")
      : "近 30 日暂无新闻",
  );
  elements.sectorDonut.innerHTML = `
    <div><strong>${recentItems.length}</strong><span>篇新闻</span></div>
  `;
  elements.sectorLegend.replaceChildren(
    ...sectorRows.map((row) => {
      const item = document.createElement("div");
      const share = recentItems.length ? row.count / recentItems.length * 100 : 0;
      item.innerHTML = `
        <span><i style="background:${row.color}"></i>${escapeHtml(row.name)}</span>
        <strong>${row.count}<small>${share.toFixed(0)}%</small></strong>
      `;
      return item;
    }),
  );

  const sourceRows = countBy(recentItems, (item) => itemProvider(item))
    .slice(0, 6)
    .map(([provider, count]) => ({
      label: providerLabel(provider),
      value: count,
    }));
  const sourceTotal = sourceRows.reduce((sum, row) => sum + row.value, 0);
  const sourceMax = Math.max(1, ...sourceRows.map((row) => row.value));
  elements.sourceSignalTotal.textContent = `${sourceRows.length} 类`;
  elements.sourceSignalBars.replaceChildren(
    ...sourceRows.map((row) => createRankBar(
      row.label,
      row.value,
      sourceMax,
      {
        color: "#2f8f83",
        suffix: sourceTotal ? `${(row.value / sourceTotal * 100).toFixed(0)}%` : "0%",
      },
    )),
  );
  if (!sourceRows.length) {
    elements.sourceSignalBars.innerHTML = '<div class="visual-empty">暂无来源数据</div>';
  }

  const heatmapDays = latestDate
    ? Array.from({ length: 14 }, (_, index) => addDays(latestDate, index - 13))
    : [];
  const companies = industryGroups.flatMap((group) => group.companies);
  const companyRows = companies
    .map((company) => {
      const counts = heatmapDays.map((date) =>
        items.filter((item) => item.company_id === company.id && dateKey(item.published_at) === date)
          .length
      );
      return { ...company, counts, total: counts.reduce((sum, count) => sum + count, 0) };
    })
    .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name, "zh-CN"));
  const maxHeat = Math.max(1, ...companyRows.flatMap((row) => row.counts));
  elements.companyHeatmap.style.setProperty("--heatmap-days", String(heatmapDays.length));
  const heatmapHeader = document.createElement("div");
  heatmapHeader.className = "heatmap-row heatmap-header";
  heatmapHeader.innerHTML = `
    <span>公司</span>
    ${heatmapDays.map((date, index) => `<span>${index % 2 === 0 || index === heatmapDays.length - 1 ? date.slice(5).replace("-", "/") : ""}</span>`).join("")}
    <strong>合计</strong>
  `;
  const heatmapRows = companyRows.map((company) => {
    const row = document.createElement("div");
    row.className = "heatmap-row";
    const companyButton = document.createElement("button");
    companyButton.type = "button";
    companyButton.className = "heatmap-company";
    companyButton.textContent = company.name;
    companyButton.title = `查看 ${company.name} 的事件时间线`;
    companyButton.addEventListener("click", () => {
      selectCompany(company.id);
      activateWorkspaceView("events", { scroll: true });
    });
    row.append(companyButton);
    company.counts.forEach((count, index) => {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "heatmap-cell";
      const level = count
        ? Math.max(1, Math.ceil(Math.log1p(count) / Math.log1p(maxHeat) * 5))
        : 0;
      cell.dataset.level = String(level);
      cell.title = `${company.name} · ${formatDateLabel(heatmapDays[index])} · ${count} 条`;
      cell.setAttribute("aria-label", cell.title);
      cell.disabled = count === 0;
      cell.addEventListener("click", () => {
        state.companyId = company.id;
        state.groupId = companyToGroup.get(company.id) ?? "all";
        state.selectedDate = heatmapDays[index];
        state.timeRange = "date";
        state.visibleLimit = 120;
        elements.companyFilter.value = company.id;
        elements.eventCompanyFilter.value = company.id;
        activateWorkspaceView("news", { scroll: true });
        render();
      });
      row.append(cell);
    });
    const total = document.createElement("strong");
    total.textContent = String(company.total);
    row.append(total);
    return row;
  });
  elements.companyHeatmap.replaceChildren(heatmapHeader, ...heatmapRows);
}

function createRankBar(label, value, maxValue, options = {}) {
  const element = options.onClick
    ? document.createElement("button")
    : document.createElement("div");
  if (options.onClick) {
    element.type = "button";
    element.addEventListener("click", options.onClick);
  }
  element.className = `rank-bar-row${options.active ? " is-active" : ""}`;
  const width = maxValue ? Math.max(2, Number(value) / maxValue * 100) : 0;
  element.innerHTML = `
    <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
    <i><b style="width:${width}%;background:${options.color ?? "#2878d0"}"></b></i>
    ${options.suffix ? `<small>${escapeHtml(options.suffix)}</small>` : ""}
  `;
  return element;
}

function renderVolumeIndex(items) {
  const dailyRows = Array.isArray(state.dailyIndex?.days) ? state.dailyIndex.days : [];
  const latestDate = dailyRows[0]?.date ?? latestNewsDate(items);
  const counts = dailyRows.length
    ? new Map(dailyRows.map((row) => [row.date, Number(row.count) || 0]))
    : new Map(countBy(items, (item) => dateKey(item.published_at)));
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
  elements.archiveSummary.textContent = `${populatedDays.length} 个新闻日期 · ${runs.length} 次采集记录`;

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
  activateWorkspaceView("news");
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
        state.eventType = "all";
        state.visibleLimit = 120;
        state.eventVisibleLimit = 40;
        elements.companyFilter.value = "all";
        elements.eventCompanyFilter.value = "all";
        render();
      });
      return button;
    }),
  );
}

function renderIndustrySections(items) {
  const heading = document.createElement("div");
  heading.className = "workspace-view-heading";
  heading.innerHTML = `
    <div>
      <div class="section-kicker">公司雷达</div>
      <h2>按产业链浏览关注公司</h2>
      <p>点击公司进入其事件时间线；点击分类进入对应新闻档案。</p>
    </div>
    <strong>${industryGroups.reduce((sum, group) => sum + group.companies.length, 0)} 家</strong>
  `;
  elements.industrySections.replaceChildren(
    heading,
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
        state.eventType = "all";
        state.visibleLimit = 120;
        elements.companyFilter.value = "all";
        elements.eventCompanyFilter.value = "all";
        activateWorkspaceView("news", { scroll: true });
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
  const latestDate = latestNewsDate(items);
  const activityDays = latestDate
    ? Array.from({ length: 14 }, (_, index) => addDays(latestDate, index - 13))
    : [];
  const activityCounts = activityDays.map((date) =>
    companyItems.filter((item) => dateKey(item.published_at) === date).length
  );
  const sparkMax = Math.max(1, ...activityCounts);
  const currentWeek = activityCounts.slice(-7).reduce((sum, count) => sum + count, 0);
  const previousWeek = activityCounts.slice(0, 7).reduce((sum, count) => sum + count, 0);
  const weeklyChange = currentWeek - previousWeek;
  const card = document.createElement("article");
  card.className = "company-card";
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `查看 ${company.name} 的事件时间线`);
  card.innerHTML = `
    <div class="company-card-top">
      <div>
        <span>${escapeHtml(company.region)}</span>
        <h3>${escapeHtml(company.name)}</h3>
      </div>
      <strong>${companyItems.length}</strong>
    </div>
    <p>${latest ? escapeHtml(latest.title) : "暂无新闻"}</p>
    <div class="company-sparkline" aria-label="${escapeHtml(company.name)}近 14 日新闻数量">
      ${activityCounts.map((count) => `<i style="height:${Math.max(8, count / sparkMax * 100)}%" title="${count} 条"></i>`).join("")}
    </div>
    <div class="company-card-foot">
      <span>近 7 日 ${currentWeek} 条</span>
      <span class="${weeklyChange > 0 ? "is-rising" : weeklyChange < 0 ? "is-falling" : ""}">
        环比 ${weeklyChange > 0 ? "+" : ""}${weeklyChange}
      </span>
      <span>${issues ? `${issues} 个来源需检查` : "来源运行正常"}</span>
    </div>
  `;
  const openCompanyEvents = () => {
    selectCompany(company.id);
    state.eventVisibleLimit = 40;
    activateWorkspaceView("events", { scroll: true });
  };
  card.addEventListener("click", openCompanyEvents);
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openCompanyEvents();
    }
  });
  return card;
}

function renderEventTimeline() {
  const scopedEvents = state.events.filter((event) => eventMatchesCurrentScope(event));
  const filteredEvents = state.eventType === "all"
    ? scopedEvents
    : scopedEvents.filter((event) => event.event_type === state.eventType);
  renderEventVisuals(scopedEvents, filteredEvents);
  const typeRows = Object.keys(eventTypeLabels).filter((type) =>
    type === "all" || scopedEvents.some((event) => event.event_type === type)
  );
  elements.eventTypeTabs.replaceChildren(
    ...typeRows.map((type) => {
      const count = type === "all"
        ? scopedEvents.length
        : scopedEvents.filter((event) => event.event_type === type).length;
      const button = document.createElement("button");
      button.type = "button";
      button.className = state.eventType === type ? "active" : "";
      button.textContent = `${eventTypeLabels[type]} ${count}`;
      button.addEventListener("click", () => {
        state.eventType = type;
        state.eventVisibleLimit = 40;
        renderEventTimeline();
      });
      return button;
    }),
  );
  elements.eventSummary.textContent = state.events.length
    ? `完整历史 ${formatFullDate(filteredEvents.at(-1)?.started_at)}—${formatFullDate(filteredEvents[0]?.latest_at)} · 当前范围 ${filteredEvents.length} 个事件 · 聚合 ${filteredEvents.reduce((sum, event) => sum + (event.article_count ?? 0), 0)} 篇报道`
    : "等待事件时间线数据生成";

  if (!filteredEvents.length) {
    elements.eventTimeline.innerHTML = `
      <div class="empty">
        <div class="empty-title">当前范围暂无可聚合事件</div>
        <p class="empty-subtitle text-muted">可切换公司或事件类型。</p>
      </div>
    `;
    return;
  }
  const visibleEvents = filteredEvents.slice(0, state.eventVisibleLimit);
  const cards = visibleEvents.map((event) => eventCard(event));
  if (visibleEvents.length < filteredEvents.length) {
    const footer = document.createElement("div");
    footer.className = "event-load-more";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-outline-secondary";
    button.textContent = `继续加载事件（剩余 ${filteredEvents.length - visibleEvents.length} 个）`;
    button.addEventListener("click", () => {
      state.eventVisibleLimit += 40;
      renderEventTimeline();
    });
    footer.append(button);
    cards.push(footer);
  }
  elements.eventTimeline.replaceChildren(...cards);
}

function renderEventVisuals(scopedEvents, filteredEvents) {
  elements.eventVisualTotal.textContent = `${scopedEvents.length} 个`;
  const typeRows = countBy(scopedEvents, (event) => event.event_type ?? "other")
    .slice(0, 7)
    .map(([type, count]) => ({
      type,
      label: eventTypeLabels[type] ?? "其他动态",
      count,
    }));
  const typeMax = Math.max(1, ...typeRows.map((row) => row.count));
  elements.eventTypeChart.replaceChildren(
    ...typeRows.map((row) => createRankBar(
      row.label,
      row.count,
      typeMax,
      {
        color: eventTypeColors[row.type] ?? eventTypeColors.other,
        active: state.eventType === row.type,
        suffix: scopedEvents.length ? `${(row.count / scopedEvents.length * 100).toFixed(0)}%` : "0%",
        onClick: () => {
          state.eventType = state.eventType === row.type ? "all" : row.type;
          state.eventVisibleLimit = 40;
          renderEventTimeline();
        },
      },
    )),
  );
  if (!typeRows.length) {
    elements.eventTypeChart.innerHTML = '<div class="visual-empty">暂无事件数据</div>';
  }

  const companyRows = countBy(
    filteredEvents,
    (event) => event.company_id ?? "unknown",
  )
    .slice(0, 6)
    .map(([companyId, count]) => ({
      companyId,
      label: companyName(companyId),
      count,
    }));
  const companyMax = Math.max(1, ...companyRows.map((row) => row.count));
  elements.eventCompanyChart.replaceChildren(
    ...companyRows.map((row) => createRankBar(
      row.label,
      row.count,
      companyMax,
      {
        color: "#2878d0",
        suffix: "事件",
        active: state.companyId === row.companyId,
        onClick: () => {
          selectCompany(row.companyId);
          state.eventVisibleLimit = 40;
          activateWorkspaceView("events");
        },
      },
    )),
  );
  if (!companyRows.length) {
    elements.eventCompanyChart.innerHTML = '<div class="visual-empty">暂无公司数据</div>';
  }

  const importanceRows = [
    {
      id: "high",
      label: "高重要度",
      count: filteredEvents.filter((event) => Number(event.importance_score) >= 70).length,
    },
    {
      id: "medium",
      label: "中重要度",
      count: filteredEvents.filter((event) => {
        const value = Number(event.importance_score);
        return value >= 55 && value < 70;
      }).length,
    },
    {
      id: "normal",
      label: "一般",
      count: filteredEvents.filter((event) => Number(event.importance_score) < 55).length,
    },
  ];
  elements.eventHighImportance.textContent = `${importanceRows[0].count} 个`;
  elements.eventImportanceChart.innerHTML = `
    <div
      class="importance-track"
      role="img"
      aria-label="${importanceRows.map((row) => `${row.label} ${row.count} 个`).join("，")}"
    >
      ${importanceRows.map((row) => `<i class="is-${row.id}" style="flex-grow:${row.count}" ${row.count ? "" : "hidden"}></i>`).join("")}
    </div>
    <div class="importance-legend">
      ${importanceRows.map((row) => `
        <div><span><i class="is-${row.id}"></i>${row.label}</span><strong>${row.count}</strong></div>
      `).join("")}
    </div>
    <p>重要度综合事件类型、报道数量、来源覆盖与时间跨度计算。</p>
  `;
}

function eventMatchesCurrentScope(event) {
  const groupMatches = state.groupId === "all"
    || companyToGroup.get(event.company_id) === state.groupId;
  const companyMatches = state.companyId === "all" || event.company_id === state.companyId;
  return groupMatches && companyMatches;
}

function eventCard(event) {
  const card = document.createElement("article");
  card.className = `event-card event-${event.event_type ?? "other"}`;
  card.style.setProperty(
    "--event-color",
    eventTypeColors[event.event_type] ?? eventTypeColors.other,
  );
  const sourceNames = Array.isArray(event.source_names) ? event.source_names : [];
  const articles = Array.isArray(event.articles) ? event.articles : [];
  card.innerHTML = `
    <div class="event-rail"><span></span></div>
    <div class="event-card-body">
      <div class="event-badges">
        <span class="news-company">${escapeHtml(companyName(event.company_id, event.company_name))}</span>
        <span class="event-type-badge">${escapeHtml(event.event_label ?? eventTypeLabels[event.event_type] ?? "其他动态")}</span>
        ${event.event_type === "market" ? '<span class="market-badge">市场信息</span>' : ""}
      </div>
      <a class="event-headline" href="${escapeHtml(event.latest_url)}" target="_blank" rel="noopener noreferrer">
        ${escapeHtml(event.headline)}
      </a>
      <p>${escapeHtml(event.summary)}</p>
      <div class="event-meta">
        <span>${formatEventDateRange(event)}</span>
        <span>${event.article_count ?? 0} 篇报道</span>
        <span>${event.source_count ?? 0} 个来源</span>
        <span>重要度 ${event.importance_score ?? 0}</span>
      </div>
      <div class="event-sources">${sourceNames.slice(0, 5).map((source) => `<span>${escapeHtml(source)}</span>`).join("")}</div>
      ${articles.length ? `
        <details class="event-articles">
          <summary>查看组成该事件的报道</summary>
          <ul></ul>
        </details>
      ` : ""}
    </div>
  `;
  const details = card.querySelector(".event-articles");
  if (details) {
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.loaded === "true") return;
      const list = details.querySelector("ul");
      list.replaceChildren(
        ...articles.map((article) => {
          const item = document.createElement("li");
          item.innerHTML = `
            <a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
              ${escapeHtml(article.title)}
            </a>
            <span>${escapeHtml(article.source_name)} · ${formatFullDate(article.published_at)}</span>
          `;
          return item;
        }),
      );
      details.dataset.loaded = "true";
    });
  }
  return card;
}

function formatEventDateRange(event) {
  const start = formatFullDate(event.started_at);
  const latest = formatFullDate(event.latest_at);
  return start === latest ? latest : `${start}—${latest}`;
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
            (row) => row.company_id === company.id && normalizeProvider(
              row.provider_id ?? row.provider_type ?? row.source_type,
            ) === provider,
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
  const gate = state.result.metadata?.quality_gate;
  const filteredCount = (gate?.watchlist_count ?? 0) + (gate?.rejected_count ?? 0);
  elements.diagnosticsSummary.textContent =
    `${issueRows.length} 个数据源异常，${archivedCount} 条归档新闻，门控过滤 ${filteredCount} 条`;

  if (!issueRows.length) {
    elements.errorAccordion.innerHTML = `
      <div class="diagnostic-empty">本轮未发现数据源访问异常。</div>
    `;
    return;
  }

  elements.errorAccordion.innerHTML = issueRows
    .map((status) => {
      const label = status.provider_status ?? status.final_status ?? status.status ?? "unknown";
      const provider = normalizeProvider(
        status.provider_id ?? status.provider_type ?? status.source_type,
      );
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
  const aliases = {
    rss_provider: "rss",
    official_site_provider: "official_site",
    official_page: "official_site",
    spaceflight_news_provider: "spaceflight_news",
    gdelt_provider: "gdelt",
    serpapi_provider: "serpapi",
    brave_news_provider: "brave_news",
    newsapi_provider: "newsapi",
  };
  return aliases[provider] ?? provider;
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
