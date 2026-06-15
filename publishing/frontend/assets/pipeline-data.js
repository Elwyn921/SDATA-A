import { samplePipelineResult } from "./mock-pipeline-result.js";

export const DATA_ENDPOINTS = {
  latestPipelineResult: "../../data/news/latest/pipeline_result.json",
  archiveIndex: "../../data/news/archive/index.json",
};

export async function loadPipelineResult(options = {}) {
  const mode = options.mode ?? "mock";

  if (mode === "json") {
    const response = await fetch(options.url ?? DATA_ENDPOINTS.latestPipelineResult, {
      headers: { accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Unable to load PipelineResult JSON: ${response.status}`);
    }
    return response.json();
  }

  return samplePipelineResult;
}
