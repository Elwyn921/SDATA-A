import { samplePipelineResult } from "./mock-pipeline-result.js";

export const DATA_ENDPOINTS = {
  latestPipelineResult: "./data/news/latest/pipeline_result.json",
  archiveIndex: "./data/news/archive/index.json",
  archiveCatalog: "./data/news/archive/catalog.json",
  eventTimeline: "./data/news/latest/event_timeline.json",
  dailyReport: "./data/reports/latest/daily_report.json",
  indexSnapshot: "./data/indices/latest/aerospace_index.json",
};

export async function loadDashboardData(options = {}) {
  const result = await loadPipelineResult(options);
  const [archiveIndex, archiveCatalog, eventTimeline, dailyReport, indexSnapshot] = await Promise.all([
    loadOptionalJson(options.archiveUrl ?? DATA_ENDPOINTS.archiveIndex),
    loadOptionalJson(options.catalogUrl ?? DATA_ENDPOINTS.archiveCatalog),
    loadOptionalJson(options.eventTimelineUrl ?? DATA_ENDPOINTS.eventTimeline),
    loadOptionalJson(options.reportUrl ?? DATA_ENDPOINTS.dailyReport),
    loadOptionalJson(options.indexUrl ?? DATA_ENDPOINTS.indexSnapshot),
  ]);
  return { result, archiveIndex, archiveCatalog, eventTimeline, dailyReport, indexSnapshot };
}

export async function loadPipelineResult(options = {}) {
  const mode = options.mode ?? "auto";

  if (mode === "json") {
    return loadJsonPipelineResult(options.url ?? DATA_ENDPOINTS.latestPipelineResult);
  }

  if (mode === "auto") {
    try {
      return await loadJsonPipelineResult(options.url ?? DATA_ENDPOINTS.latestPipelineResult);
    } catch (error) {
      console.info(`Using mock PipelineResult fallback: ${error.message}`);
      return withDataSource(samplePipelineResult, "mock");
    }
  }

  return withDataSource(samplePipelineResult, "mock");
}

async function loadJsonPipelineResult(url) {
  const resolvedUrl = resolveDataUrl(url);

  if (resolvedUrl.protocol === "file:") {
    return withDataSource(await loadLocalJson(resolvedUrl), "json");
  }

  const response = await fetch(resolvedUrl.href, {
    cache: "no-store",
    headers: { accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Unable to load PipelineResult JSON: ${response.status}`);
  }

  return withDataSource(normalizePipelineResult(await response.json()), "json");
}

async function loadOptionalJson(url) {
  try {
    const resolvedUrl = resolveDataUrl(url);
    if (resolvedUrl.protocol === "file:") return await loadLocalJsonValue(resolvedUrl);
    const response = await fetch(resolvedUrl.href, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function normalizePipelineResult(result) {
  return {
    schema_version: result?.schema_version,
    artifact_version: result?.artifact_version,
    run_id: result?.run_id ?? "unknown-run",
    started_at: result?.started_at,
    finished_at: result?.finished_at,
    generated_at: result?.generated_at,
    dry_run: result?.dry_run,
    items: Array.isArray(result?.items) ? result.items : [],
    summaries: Array.isArray(result?.summaries) ? result.summaries : [],
    exports: Array.isArray(result?.exports) ? result.exports : [],
    fetch_statuses: Array.isArray(result?.fetch_statuses) ? result.fetch_statuses : [],
    warnings: Array.isArray(result?.warnings) ? result.warnings : [],
    metadata: result?.metadata && typeof result.metadata === "object" ? result.metadata : {},
  };
}

function withDataSource(result, source) {
  return Object.defineProperty(result, "__dataSource", {
    configurable: true,
    enumerable: false,
    value: source,
  });
}

function resolveDataUrl(url) {
  const base =
    typeof document !== "undefined" && document.baseURI
      ? document.baseURI
      : new URL("../", import.meta.url).href;
  return new URL(url, base);
}

async function loadLocalJson(fileUrl) {
  const value = await loadLocalJsonValue(fileUrl);
  return normalizePipelineResult(value);
}

async function loadLocalJsonValue(fileUrl) {
  const { readFile } = await import("node:fs/promises");
  const text = await readFile(fileUrl, "utf8");
  return JSON.parse(text);
}
