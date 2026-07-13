from pathlib import Path

import yaml


def test_a6_daily_report_prompt_contract():
    config = yaml.safe_load(Path("config/prompt_templates.yaml").read_text(encoding="utf-8"))

    assert config["schema_version"] == "prompt_templates.a6_daily_report.v1"
    assert config["agent"]["id"] == "A6"
    assert config["agent"]["stage"] == "report"
    assert config["agent"]["status"] == "first_implementation"

    policy = config["execution_policy"]
    assert policy["call_llm"] == "true_when_secret_available"
    assert policy["missing_secret_status"] == "skipped_no_secret"
    assert policy["missing_secret_must_fail_workflow"] is False
    assert policy["api_key_env"] == "OPENAI_API_KEY"

    contract = config["daily_report_schema"]
    assert contract["strict_json"] is True
    for field in (
        "report_id",
        "source_run_id",
        "executive_summary",
        "industry_chain_sections",
        "company_updates",
        "top_news",
        "citations",
        "frontend",
    ):
        assert field in contract["required"]

    template = config["templates"]["daily_report"]
    assert template["input_schema"] == "PipelineResult"
    assert template["output_schema_ref"] == "DailyReport"
    assert "严格 JSON" in template["system"]

    assert config["guardrails"]["require_source_url"] is True
    assert config["guardrails"]["no_unsourced_claims"] is True
