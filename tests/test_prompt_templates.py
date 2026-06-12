from pathlib import Path

import yaml


def test_a6_prompt_templates_are_placeholder_contracts_only():
    config = yaml.safe_load(Path("config/prompt_templates.yaml").read_text(encoding="utf-8"))

    assert config["schema_version"] == "prompt_templates.a6.v1"
    assert config["agent"]["id"] == "A6"
    assert config["agent"]["status"] == "placeholder_only"

    policy = config["execution_policy"]
    assert policy["call_llm"] is False
    assert policy["generate_real_summary"] is False
    assert policy["templates_are_contracts_only"] is True

    contract = config["output_contract"]
    assert contract["strict_json"] is True
    assert contract["additional_properties"] is False
    for field in (
        "llm_summary",
        "event_category",
        "importance_score",
        "why_it_matters",
        "recommended_action",
    ):
        assert field in contract["required"]

    for template in config["templates"].values():
        assert template["status"] == "placeholder_only"
        assert "PLACEHOLDER ONLY" in template["system_placeholder"]

    assert config["guardrails"]["no_real_generation_in_current_phase"] is True
