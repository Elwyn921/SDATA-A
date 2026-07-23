"""Generate an LLM-backed daily intelligence report from PipelineResult JSON."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid5, NAMESPACE_URL


REPORT_SCHEMA_VERSION = "daily_report.v1"
DEFAULT_INPUT_PATH = Path("docs/data/news/latest/pipeline_result.json")
DEFAULT_LATEST_DIR = Path("data/reports/latest")
DEFAULT_PUBLISH_DIR = Path("docs/data/reports/latest")
DEFAULT_ARCHIVE_ROOT = Path("data/reports/archive")
DEFAULT_PROVIDER = "openai"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_DAILY_REPORT_MODEL"
OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
REPORT_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
INDUSTRY_CHAIN_SECTIONS = (
    ("satellite_platforms", "卫星平台与整星制造"),
    ("launch_services", "运载火箭与发射服务"),
    ("satellite_internet", "卫星互联网服务"),
    ("foreign_majors", "国外大厂"),
)
FOREIGN_MAJOR_COMPANY_IDS = {"spacex", "blue_origin"}
LAUNCH_COMPANY_HINTS = {
    "spacex",
    "blue_origin",
    "cas_space",
    "galactic_energy",
    "i_space",
    "landspace",
    "space_pioneer",
    "yushi_space",
}
SATELLITE_INTERNET_HINTS = {
    "spacex",
    "china_satnet",
    "yuanxin_satellite",
    "galaxyspace",
    "hongqing_technology",
}


class MissingSecret(RuntimeError):
    """Raised when the configured LLM provider has no API key."""


@dataclass(frozen=True)
class ReportOutputs:
    latest_json: Path
    latest_markdown: Path
    published_json: Path
    archived_json: Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def item_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    published = item.get("published_at") or ""
    fresh = 1 if item.get("fresh", True) and not item.get("stale", False) else 0
    return (fresh, published, item.get("id", ""))


def company_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item.get("company_id") or "unknown"].append(item)
    rows = []
    for company_id, company_items in grouped.items():
        latest = sorted(company_items, key=item_sort_key, reverse=True)[:5]
        rows.append(
            {
                "company_id": company_id,
                "company_name": latest[0].get("company_name") or company_id,
                "item_count": len(company_items),
                "fresh_count": sum(1 for item in company_items if item.get("fresh", True)),
                "stale_count": sum(1 for item in company_items if item.get("stale", False)),
                "latest_titles": [item.get("title", "") for item in latest if item.get("title")],
            }
        )
    return sorted(rows, key=lambda row: (-row["item_count"], row["company_name"]))


def section_for_item(item: dict[str, Any]) -> str:
    company_id = item.get("company_id") or ""
    haystack = f"{item.get('title', '')} {item.get('normalized_text', '')}".lower()
    if company_id in FOREIGN_MAJOR_COMPANY_IDS:
        return "foreign_majors"
    if company_id in LAUNCH_COMPANY_HINTS or any(
        keyword in haystack for keyword in ("launch", "rocket", "falcon", "new glenn", "starship", "发射", "火箭")
    ):
        return "launch_services"
    if company_id in SATELLITE_INTERNET_HINTS or any(
        keyword in haystack for keyword in ("starlink", "satellite internet", "broadband", "星座", "卫星互联网")
    ):
        return "satellite_internet"
    return "satellite_platforms"


def select_top_news(items: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    seen_companies = Counter()
    selected = []
    for item in sorted(items, key=item_sort_key, reverse=True):
        company_id = item.get("company_id") or "unknown"
        if seen_companies[company_id] >= 3 and len(selected) < 12:
            continue
        selected.append(item)
        seen_companies[company_id] += 1
        if len(selected) >= limit:
            break
    return selected


def citation_for_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    source = item.get("source") or {}
    return {
        "citation_id": f"C{index:03d}",
        "item_id": item.get("id"),
        "company_id": item.get("company_id"),
        "company_name": item.get("company_name"),
        "title": item.get("title"),
        "url": item.get("url"),
        "published_at": item.get("published_at"),
        "source_name": source.get("source_name") or source.get("source_id"),
        "source_type": source.get("source_type"),
    }


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source") or {}
    return {
        "item_id": item.get("id"),
        "company_id": item.get("company_id"),
        "company_name": item.get("company_name"),
        "title": item.get("title"),
        "url": item.get("url"),
        "published_at": item.get("published_at"),
        "source_name": source.get("source_name") or source.get("source_id"),
        "source_type": source.get("source_type"),
        "section_hint": section_for_item(item),
        "text": clean_text(item.get("normalized_text") or item.get("raw_text"))[:600],
    }


def source_health(fetch_statuses: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(status.get("final_status") or status.get("status") for status in fetch_statuses)
    failed = [
        status
        for status in fetch_statuses
        if (status.get("final_status") or status.get("status")) not in ("success", "ok")
    ]
    return {
        "overall_status": "healthy" if not failed else "degraded",
        "total_sources": len(fetch_statuses),
        "successful_sources": status_counts.get("success", 0) + status_counts.get("ok", 0),
        "failed_sources": len(failed),
        "status_counts": dict(status_counts),
        "source_statuses": [
            {
                "company_id": status.get("company_id") or status.get("scheduled_company_id"),
                "company_name": status.get("company_name"),
                "provider_id": status.get("provider_id"),
                "source_type": status.get("source_type"),
                "final_status": status.get("final_status") or status.get("status"),
                "item_count": status.get("item_count") or status.get("article_count") or 0,
                "error_type": status.get("error_type"),
                "error_message": status.get("error_message"),
            }
            for status in fetch_statuses
        ],
    }


def daily_report_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "executive_summary",
            "industry_chain_sections",
            "company_updates",
            "top_news",
            "risks_and_watchpoints",
            "recommended_followups",
        ],
        "properties": {
            "executive_summary": {"type": "string"},
            "industry_chain_sections": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "company_updates": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "top_news": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "risks_and_watchpoints": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "recommended_followups": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
    }


def publication_date(item: dict[str, Any]) -> str | None:
    published_at = parse_datetime(item.get("published_at"))
    if published_at is None:
        return None
    return published_at.astimezone(REPORT_TIMEZONE).date().isoformat()


def build_prompt_input(pipeline_result: dict[str, Any], *, max_items: int = 80) -> dict[str, Any]:
    all_items = pipeline_result.get("items") or []
    source_generated_at = parse_datetime(
        pipeline_result.get("generated_at") or pipeline_result.get("finished_at")
    )
    report_date = (
        source_generated_at.astimezone(REPORT_TIMEZONE).date().isoformat()
        if source_generated_at
        else None
    )
    items = [item for item in all_items if publication_date(item) == report_date]
    if not items:
        available_dates = [date for item in all_items if (date := publication_date(item))]
        report_date = max(available_dates, default=report_date or utc_now().date().isoformat())
        items = [item for item in all_items if publication_date(item) == report_date]
    top_items = select_top_news(items, limit=max_items)
    return {
        "source_run_id": pipeline_result.get("run_id"),
        "generated_at": pipeline_result.get("generated_at") or pipeline_result.get("finished_at"),
        "report_date": report_date,
        "total_items": len(items),
        "all_total_items": len(all_items),
        "companies_covered": company_rows(items),
        "source_health_summary": source_health(pipeline_result.get("fetch_statuses") or []),
        "required_sections": [
            {"section_id": section_id, "title": title} for section_id, title in INDUSTRY_CHAIN_SECTIONS
        ],
        "items": [compact_item(item) for item in top_items],
    }


def daily_report_prompt(prompt_input: dict[str, Any]) -> tuple[str, str]:
    system = (
        "你是 A6 LLM Enrichment Agent，负责把卫星产业新闻 PipelineResult 汇总成每日情报日报。"
        "只做每日归纳汇总，不做复杂预测，不做估值，不编造未在输入 URL 支撑的信息。"
        "必须使用中文输出，保留公司英文名和专有名词。返回严格 JSON，不要 Markdown 包裹。"
    )
    user = (
        "请基于以下 PipelineResult 摘要生成 DailyReport 的 LLM 生成部分。"
        "必须覆盖四个 industry_chain_sections：卫星平台与整星制造、运载火箭与发射服务、"
        "卫星互联网服务、国外大厂。每条重要判断要保留 source_urls。\n\n"
        "JSON 输入：\n"
        f"{json.dumps(prompt_input, ensure_ascii=False, indent=2)}"
    )
    return system, user


class OpenAIReportProvider:
    """Minimal OpenAI Responses API client using only stdlib urllib."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(OPENAI_API_KEY_ENV)
        self.model = model or os.environ.get(OPENAI_MODEL_ENV) or DEFAULT_OPENAI_MODEL
        self.base_url = (base_url or os.environ.get(OPENAI_BASE_URL_ENV) or "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return DEFAULT_PROVIDER

    def generate(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise MissingSecret(f"{OPENAI_API_KEY_ENV} is not set")

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "DailyReportLLMFields",
                    "strict": True,
                    "schema": daily_report_json_schema(),
                }
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = extract_openai_output_text(raw)
        return json.loads(text)


def extract_openai_output_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return str(response["output_text"])
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in ("output_text", "text") and content.get("text"):
                return str(content["text"])
    raise ValueError("OpenAI response did not include output text")


def skipped_llm_payload(prompt_input: dict[str, Any]) -> dict[str, Any]:
    sections = []
    items_by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in prompt_input["items"]:
        items_by_section[item["section_hint"]].append(item)
    for section_id, title in INDUSTRY_CHAIN_SECTIONS:
        section_items = items_by_section.get(section_id, [])[:6]
        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "summary": "",
                "key_updates": [
                    {
                        "title": item["title"],
                        "company_id": item["company_id"],
                        "company_name": item["company_name"],
                        "source_urls": [item["url"]] if item.get("url") else [],
                    }
                    for item in section_items
                ],
                "source_urls": [item["url"] for item in section_items if item.get("url")],
            }
        )
    companies = prompt_input["companies_covered"]
    leading_companies = "、".join(
        company["company_name"] for company in companies[:3]
    )
    executive_summary = (
        f"{prompt_input['report_date']} 共收录 {prompt_input['total_items']} 条新闻，"
        f"覆盖 {len(companies)} 家公司。"
    )
    if leading_companies:
        executive_summary += f"新闻量靠前的公司包括 {leading_companies}。"
    if not prompt_input["total_items"]:
        executive_summary = f"{prompt_input['report_date']} 暂无新增新闻，历史新闻已保留在归档中。"
    return {
        "executive_summary": executive_summary,
        "industry_chain_sections": sections,
        "company_updates": [
            {
                "company_id": company["company_id"],
                "company_name": company["company_name"],
                "summary": "",
                "item_count": company["item_count"],
                "key_news": company["latest_titles"][:3],
                "source_urls": [],
            }
            for company in prompt_input["companies_covered"]
        ],
        "top_news": [
            {
                "item_id": item["item_id"],
                "company_id": item["company_id"],
                "company_name": item["company_name"],
                "title": item["title"],
                "url": item["url"],
                "published_at": item["published_at"],
                "section_id": item["section_hint"],
                "why_selected": "",
            }
            for item in prompt_input["items"][:20]
        ],
        "risks_and_watchpoints": [],
        "recommended_followups": [],
    }


def merge_report(
    *,
    pipeline_result: dict[str, Any],
    prompt_input: dict[str, Any],
    llm_payload: dict[str, Any],
    generated_at: datetime,
    generation_status: str,
    provider_status: dict[str, Any],
    input_path: Path,
) -> dict[str, Any]:
    source_run_id = pipeline_result.get("run_id") or "unknown"
    report_date = prompt_input["report_date"]
    report_id = f"daily-{report_date}-{str(uuid5(NAMESPACE_URL, source_run_id))[:8]}"
    selected_items = select_top_news(pipeline_result.get("items") or [], limit=40)
    citations = [citation_for_item(item, index) for index, item in enumerate(selected_items, start=1)]
    source_urls = sorted({citation["url"] for citation in citations if citation.get("url")})

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id,
        "generated_at": isoformat_z(generated_at),
        "report_date": report_date,
        "source_run_id": source_run_id,
        "source_pipeline_result_path": str(input_path),
        "generation_status": generation_status,
        "llm_provider": provider_status,
        "companies_covered": prompt_input["companies_covered"],
        "total_items": prompt_input["total_items"],
        "executive_summary": llm_payload.get("executive_summary", ""),
        "industry_chain_sections": normalize_sections(llm_payload.get("industry_chain_sections") or []),
        "company_updates": llm_payload.get("company_updates") or [],
        "top_news": llm_payload.get("top_news") or [],
        "source_health_summary": prompt_input["source_health_summary"],
        "risks_and_watchpoints": llm_payload.get("risks_and_watchpoints") or [],
        "recommended_followups": llm_payload.get("recommended_followups") or [],
        "citations": citations,
        "source_urls": source_urls,
        "frontend": {
            "status_badge": generation_status,
            "updated_at": isoformat_z(generated_at),
            "sections_order": [section_id for section_id, _ in INDUSTRY_CHAIN_SECTIONS],
            "company_filter_options": [
                {"value": company["company_id"], "label": company["company_name"]}
                for company in prompt_input["companies_covered"]
            ],
            "cards": {
                "total_items": prompt_input["total_items"],
                "companies": len(prompt_input["companies_covered"]),
                "top_news": len(llm_payload.get("top_news") or []),
                "source_health": prompt_input["source_health_summary"]["overall_status"],
            },
        },
    }


def normalize_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {section.get("section_id"): section for section in sections}
    normalized = []
    for section_id, title in INDUSTRY_CHAIN_SECTIONS:
        section = dict(by_id.get(section_id) or {})
        section.setdefault("section_id", section_id)
        section.setdefault("title", title)
        section.setdefault("summary", "")
        section.setdefault("key_updates", [])
        section.setdefault("source_urls", [])
        normalized.append(section)
    return normalized


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 每日新闻情报日报 - {report['generated_at'][:10]}",
        "",
        f"- Report ID: {report['report_id']}",
        f"- Source run: {report['source_run_id']}",
        f"- Generation status: {report['generation_status']}",
        f"- Companies covered: {len(report['companies_covered'])}",
        f"- Total items: {report['total_items']}",
        "",
        "## Executive Summary",
        "",
        report.get("executive_summary") or "LLM summary skipped or unavailable.",
        "",
        "## Industry Chain Sections",
        "",
    ]
    for section in report["industry_chain_sections"]:
        lines.extend([f"### {section['title']}", "", section.get("summary") or "No LLM summary.", ""])
        for update in section.get("key_updates", [])[:8]:
            title = update.get("title") or update.get("headline") or "Untitled"
            urls = update.get("source_urls") or []
            url = urls[0] if urls else "#"
            company = update.get("company_name") or update.get("company_id") or ""
            lines.append(f"- [{title}]({url}) {company}".strip())
        lines.append("")
    lines.extend(["## Top News", ""])
    for item in report.get("top_news", [])[:20]:
        title = item.get("title") or item.get("headline") or "Untitled"
        url = item.get("url") or (item.get("source_urls") or ["#"])[0]
        company = item.get("company_name") or item.get("company_id") or ""
        lines.append(f"- [{title}]({url}) {company}".strip())
    lines.extend(["", "## Risks And Watchpoints", ""])
    for risk in report.get("risks_and_watchpoints", []):
        if isinstance(risk, str):
            lines.append(f"- {risk}")
        else:
            lines.append(f"- {risk.get('title') or risk.get('summary') or risk}")
    lines.extend(["", "## Recommended Followups", ""])
    for followup in report.get("recommended_followups", []):
        if isinstance(followup, str):
            lines.append(f"- {followup}")
        else:
            lines.append(f"- {followup.get('action') or followup.get('title') or followup}")
    lines.extend(["", "## Source Health", ""])
    health = report["source_health_summary"]
    lines.append(
        f"{health['overall_status']}: {health['successful_sources']}/{health['total_sources']} sources succeeded."
    )
    lines.append("")
    return "\n".join(lines)


def write_report_outputs(
    *,
    report: dict[str, Any],
    latest_dir: Path,
    publish_dir: Path,
    archive_root: Path,
    report_date: datetime,
) -> ReportOutputs:
    latest_json = latest_dir / "daily_report.json"
    latest_markdown = latest_dir / "daily_report.md"
    published_json = publish_dir / "daily_report.json"
    archive_json = archive_root / report_date.strftime("%Y/%m/%d") / "daily_report.json"

    write_json(latest_json, report)
    latest_markdown.parent.mkdir(parents=True, exist_ok=True)
    latest_markdown.write_text(render_markdown(report), encoding="utf-8")
    write_json(published_json, report)
    archive_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest_json, archive_json)
    return ReportOutputs(latest_json, latest_markdown, published_json, archive_json)


def build_daily_report(
    *,
    pipeline_result_path: Path = DEFAULT_INPUT_PATH,
    provider_id: str = DEFAULT_PROVIDER,
    latest_dir: Path = DEFAULT_LATEST_DIR,
    publish_dir: Path = DEFAULT_PUBLISH_DIR,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
) -> tuple[dict[str, Any], ReportOutputs]:
    generated_at = utc_now()
    pipeline_result = load_json(pipeline_result_path)
    prompt_input = build_prompt_input(pipeline_result)
    system_prompt, user_prompt = daily_report_prompt(prompt_input)

    if provider_id != DEFAULT_PROVIDER:
        raise ValueError(f"Unsupported LLM provider: {provider_id}")

    provider = OpenAIReportProvider()
    provider_status = {
        "provider_id": provider.provider_id,
        "model": provider.model,
        "status": "pending",
        "api_key_env": OPENAI_API_KEY_ENV,
    }
    try:
        llm_payload = provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        generation_status = "completed"
        provider_status["status"] = "completed"
    except MissingSecret as exc:
        llm_payload = skipped_llm_payload(prompt_input)
        generation_status = "skipped_no_secret"
        provider_status.update({"status": "skipped_no_secret", "reason": str(exc)})
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        llm_payload = skipped_llm_payload(prompt_input)
        generation_status = "skipped_provider_error"
        provider_status.update({"status": "skipped_provider_error", "reason": str(exc)})

    report = merge_report(
        pipeline_result=pipeline_result,
        prompt_input=prompt_input,
        llm_payload=llm_payload,
        generated_at=generated_at,
        generation_status=generation_status,
        provider_status=provider_status,
        input_path=pipeline_result_path,
    )
    outputs = write_report_outputs(
        report=report,
        latest_dir=latest_dir,
        publish_dir=publish_dir,
        archive_root=archive_root,
        report_date=datetime.fromisoformat(prompt_input["report_date"]).replace(
            tzinfo=REPORT_TIMEZONE
        ),
    )
    return report, outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--latest-dir", type=Path, default=DEFAULT_LATEST_DIR)
    parser.add_argument("--publish-dir", type=Path, default=DEFAULT_PUBLISH_DIR)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    args = parser.parse_args(argv)

    report, outputs = build_daily_report(
        pipeline_result_path=args.input,
        provider_id=args.provider,
        latest_dir=args.latest_dir,
        publish_dir=args.publish_dir,
        archive_root=args.archive_root,
    )
    print(
        "Generated daily report "
        f"status={report['generation_status']} json={outputs.latest_json} archive={outputs.archived_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
