---
title: SDATA-A Observable 新闻情报看板
toc: false
---

```js
const dataEndpoints = [
  "../data/news/latest/pipeline_result.json",
  "./data/news/latest/pipeline_result.json"
];

const companyMeta = new Map([
  ["spacex", {name: "SpaceX", region: "美国", category: "国外大厂"}],
  ["blue_origin", {name: "Blue Origin", region: "美国", category: "国外大厂"}],
  ["yuanxin_satellite", {name: "垣信卫星", region: "中国", category: "卫星互联网服务"}],
  ["china_satnet", {name: "中国星网", region: "中国", category: "卫星互联网服务"}],
  ["galaxyspace", {name: "银河航天", region: "中国", category: "卫星平台与整星制造"}],
  ["hongqing_technology", {name: "蓝箭鸿擎 / 鸿擎科技", region: "中国", category: "卫星平台与整星制造"}],
  ["minospace", {name: "微纳星空", region: "中国", category: "卫星平台与整星制造"}],
  ["landspace", {name: "蓝箭航天 / LandSpace", region: "中国", category: "运载火箭与发射服务"}],
  ["cas_space", {name: "中科宇航 / CAS Space", region: "中国", category: "运载火箭与发射服务"}],
  ["space_pioneer", {name: "天兵科技 / Space Pioneer", region: "中国", category: "运载火箭与发射服务"}],
  ["i_space", {name: "星际荣耀 / i-Space", region: "中国", category: "运载火箭与发射服务"}],
  ["galactic_energy", {name: "星河动力 / Galactic Energy", region: "中国", category: "运载火箭与发射服务"}],
  ["yushi_space", {name: "宇石空间", region: "中国", category: "运载火箭与发射服务"}]
]);

const providerOrder = ["rss", "official_site", "gdelt", "serpapi", "newsapi"];
const providerLabels = new Map([
  ["rss", "RSS"],
  ["official_site", "官网页面"],
  ["official_page", "官网页面"],
  ["gdelt", "GDELT"],
  ["serpapi", "SerpApi"],
  ["newsapi", "NewsAPI"],
  ["media", "媒体"],
  ["search", "搜索"]
]);

const statusLabels = new Map([
  ["success", "成功"],
  ["rate_limited", "限流"],
  ["failed", "失败"],
  ["skipped_no_secret", "跳过：未配置密钥"],
  ["missing", "无记录"],
  ["unknown", "未知"]
]);

const staleReasonLabels = new Map([
  ["partial_run_not_updated", "等待下一轮刷新"],
  ["partial_run_company_empty", "本轮暂无新增"],
  ["current_run_company_empty", "等待新数据"]
]);

async function loadPipelineResult() {
  const errors = [];
  for (const url of dataEndpoints) {
    try {
      const response = await fetch(url, {cache: "no-store", headers: {accept: "application/json"}});
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const result = await response.json();
      return {result, sourceUrl: url};
    } catch (error) {
      errors.push(`${url}: ${error.message}`);
    }
  }
  throw new Error(`无法读取 pipeline_result.json：${errors.join("; ")}`);
}

const {result: pipeline, sourceUrl} = await loadPipelineResult();
const items = Array.isArray(pipeline.items) ? pipeline.items : [];
const statuses = Array.isArray(pipeline.fetch_statuses) ? pipeline.fetch_statuses : [];
const staleFallback = pipeline.metadata?.stale_fallback ?? {};

function normalizeProvider(value) {
  const provider = String(value ?? "unknown");
  return provider === "official_page" ? "official_site" : provider;
}

function providerLabel(provider) {
  return providerLabels.get(normalizeProvider(provider)) ?? String(provider).replaceAll("_", " ");
}

function statusLabel(status) {
  return statusLabels.get(String(status)) ?? String(status).replaceAll("_", " ");
}

function statusClass(status) {
  const value = String(status);
  if (value === "success") return "status-success";
  if (value === "rate_limited") return "status-rate";
  if (value === "failed") return "status-failed";
  if (value.startsWith("skipped")) return "status-skipped";
  return "status-missing";
}

function isStale(item) {
  return item.stale === true;
}

function itemProvider(item) {
  return normalizeProvider(item.source?.source_type ?? item.source?.rank_group ?? "unknown");
}

function companyName(companyId, fallback) {
  return companyMeta.get(companyId)?.name ?? fallback ?? companyId ?? "未知公司";
}

function formatFullDate(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatShortDate(value) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function staleReason(reason) {
  return staleReasonLabels.get(reason) ?? "保留展示";
}

function shortRunId(value) {
  return value ? String(value).slice(0, 8) : "--";
}

function companyRowsFrom(items) {
  const rows = new Map([...companyMeta].map(([id, meta]) => [id, {
    company_id: id,
    company: meta.name,
    region: meta.region,
    category: meta.category,
    total: 0,
    fresh: 0,
    stale: 0
  }]));
  for (const item of items) {
    const id = item.company_id ?? "unknown";
    if (!rows.has(id)) rows.set(id, {
      company_id: id,
      company: companyName(id, item.company_name),
      region: "未知",
      category: "未分类",
      total: 0,
      fresh: 0,
      stale: 0
    });
    const row = rows.get(id);
    row.total += 1;
    if (isStale(item)) row.stale += 1;
    else row.fresh += 1;
  }
  return [...rows.values()];
}

const companyRows = companyRowsFrom(items);
const categoryRows = Array.from(companyRows.reduce((rows, row) => {
  const key = row.category ?? "未分类";
  if (!rows.has(key)) rows.set(key, {category: key, companies: 0, total: 0});
  const current = rows.get(key);
  current.companies += 1;
  current.total += row.total;
  return rows;
}, new Map()).values());
const totalNews = items.length;
const freshNews = items.filter((item) => !isStale(item)).length;
const staleNews = totalNews - freshNews;
const providerIssues = statuses.filter((status) => {
  const label = status.provider_status ?? status.final_status ?? status.status ?? "";
  return label !== "success";
}).length;
const sortedItems = [...items].sort((a, b) => new Date(b.published_at ?? 0) - new Date(a.published_at ?? 0));
```

```js
display(html`
  <section class="of-hero">
    <div>
      <div class="of-eyebrow">Observable Framework 原型</div>
      <h1>SDATA-A 新闻情报数据看板</h1>
      <p>从现有 <code>docs/data/news/latest/pipeline_result.json</code> 读取数据，验证 Observable Framework 是否适合替代手写前端。</p>
    </div>
    <div class="of-source">
      <span class="of-dot"></span>
      <strong>实时 JSON</strong>
      <span>${sourceUrl}</span>
    </div>
  </section>
`);
```

```js
display(html`
  <section class="of-kpis">
    ${[
      ["新闻总数", totalNews, "本轮可展示新闻"],
      ["覆盖公司", companyRows.length, "固定监测对象"],
      ["最新新闻", freshNews, "本轮实时结果"],
      ["待刷新项", staleNews, "保留展示连续性"],
      ["数据源异常", providerIssues, "非成功状态"]
    ].map(([label, value, caption]) => html`
      <article class="of-kpi">
        <span>${label}</span>
        <strong>${value}</strong>
        <em>${caption}</em>
      </article>
    `)}
  </section>
`);
```

```js
display(html`
  <section class="of-grid">
    <article class="of-card of-span-7">
      <header>
        <h2>公司新闻数量</h2>
        <p>按公司统计新闻覆盖与刷新状态。</p>
      </header>
      ${Plot.plot({
        height: 290,
        marginLeft: 88,
        marginRight: 34,
        x: {grid: true, label: "新闻数"},
        y: {domain: companyRows.map((d) => d.company), label: null},
        color: {legend: true, domain: ["最新", "待刷新"], range: ["#16a34a", "#9333ea"]},
        marks: [
          Plot.barX(companyRows, {y: "company", x: "fresh", fill: "最新"}),
          Plot.barX(companyRows, {y: "company", x: "stale", x1: "fresh", fill: "待刷新"}),
          Plot.text(companyRows, {y: "company", x: "total", text: "total", dx: 8, textAnchor: "start", fill: "#475467"})
        ]
      })}
    </article>

    <article class="of-card of-span-5">
      <header>
        <h2>刷新状态</h2>
        <p>判断当前页面可见情报的新鲜度。</p>
      </header>
      ${Plot.plot({
        height: 290,
        y: {grid: true, label: "新闻数"},
        x: {label: null},
        color: {domain: ["最新", "待刷新"], range: ["#16a34a", "#9333ea"]},
        marks: [
          Plot.barY([
            {state: "最新", count: freshNews},
            {state: "待刷新", count: staleNews}
          ], {x: "state", y: "count", fill: "state"}),
          Plot.text([
            {state: "最新", count: freshNews},
            {state: "待刷新", count: staleNews}
          ], {x: "state", y: "count", text: "count", dy: -8, fill: "#172033"})
        ]
      })}
    </article>
  </section>
`);
```

```js
display(html`
  <section class="of-card">
    <header>
      <h2>产业分类覆盖</h2>
      <p>13 家公司按当前监测分组聚合。</p>
    </header>
    <div class="of-table-wrap">
      <table class="of-table">
        <thead>
          <tr>
            <th>分类</th>
            <th>公司数</th>
            <th>新闻数</th>
          </tr>
        </thead>
        <tbody>
          ${categoryRows.map((row) => html`
            <tr>
              <td><strong>${row.category}</strong></td>
              <td>${row.companies}</td>
              <td>${row.total}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  </section>
`);
```

```js
display(html`
  <section class="of-card">
    <header>
      <h2>本轮运行信息</h2>
      <p>保留 run_id、generated_at 与 stale_fallback 摘要。</p>
    </header>
    <div class="of-run-grid">
      <div><span>运行 ID</span><strong>${pipeline.run_id ?? "--"}</strong></div>
      <div><span>生成时间</span><strong>${formatFullDate(pipeline.generated_at ?? pipeline.finished_at)}</strong></div>
      <div><span>保留展示</span><strong>${staleFallback.enabled === false ? "关闭" : "开启"}</strong></div>
      <div><span>最新 / 待刷新</span><strong>${staleFallback.fresh_item_count ?? freshNews} / ${staleFallback.stale_item_count ?? staleNews}</strong></div>
    </div>
  </section>
`);
```

```js
display(html`
  <section class="of-card">
    <header>
      <h2>新闻列表</h2>
      <p>展示最近 60 条新闻，新闻内容保持原始标题与来源，不做 LLM 改写。</p>
    </header>
    <div class="of-news-list">
      ${sortedItems.slice(0, 60).map((item) => html`
        <a class="of-news-row" href=${item.url} target="_blank" rel="noreferrer">
          <div>
            <div class="of-news-badges">
              <span>${companyName(item.company_id, item.company_name)}</span>
              <span>${providerLabel(itemProvider(item))}</span>
              ${isStale(item)
                ? html`<span class="of-stale" title=${`${staleReason(item.stale_reason)}；来源运行 ID：${shortRunId(item.stale_from_run_id)}`}>待刷新</span>`
                : html`<span class="of-fresh">最新</span>`}
            </div>
            <h3>${item.title}</h3>
            <p>${item.source?.source_name ?? item.source?.source_id ?? "未知来源"} · ${formatShortDate(item.published_at)}</p>
          </div>
          <span class="of-open">打开</span>
        </a>
      `)}
    </div>
  </section>
`);
```

```js
display(html`
  <section class="of-card">
    <header>
      <h2>数据源健康状态</h2>
      <p>对齐现有 provider_status / fetch_statuses，不改变后端数据结构。</p>
    </header>
    <div class="of-table-wrap">
      <table class="of-table">
        <thead>
          <tr>
            <th>公司</th>
            ${providerOrder.map((provider) => html`<th>${providerLabel(provider)}</th>`)}
          </tr>
        </thead>
        <tbody>
          ${companyRows.map((company) => html`
            <tr>
              <td><strong>${company.company}</strong></td>
              ${providerOrder.map((provider) => {
                const status = statuses.find((row) => row.company_id === company.company_id && normalizeProvider(row.provider_type ?? row.source_type) === provider);
                const label = status?.provider_status ?? status?.final_status ?? status?.status ?? "missing";
                return html`<td><span class="of-status ${statusClass(label)}">${statusLabel(label)}</span></td>`;
              })}
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  </section>
`);
```
