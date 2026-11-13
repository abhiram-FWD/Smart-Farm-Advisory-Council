import builtins
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.dependencies import (
    EvaluationFixtureDependencies,
    make_evaluation_dependencies,
)
from evaluation.run_evaluation import (
    build_report,
    evaluate_all_scenarios,
    evaluate_farm_memory,
    get_code_version,
    render_report,
    write_report,
)
from evaluation import run_evaluation as runner
from evaluation.scenarios import get_all_scenarios


FORBIDDEN_IMPORTS = {
    "chromadb",
    "llm_service",
    "memory.mongodb_memory",
    "openai",
    "pymongo",
    "rag.knowledge_base",
    "requests",
    "httpx",
    "aiohttp",
    "socket",
    "urllib.request",
    "tools.weather_tool",
}


def test_default_runner_uses_fixtures_and_does_not_import_live_services(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in FORBIDDEN_IMPORTS or any(
            name.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORTS
        ):
            raise AssertionError(f"Forbidden evaluation dependency import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    dependencies = make_evaluation_dependencies()

    results = evaluate_all_scenarios(dependencies)

    assert len(results) == 10
    assert all(item["status"] == "PASS" for item in results)
    # Fixture retrieval is explicitly non-evidence and must not reach the model.
    assert dependencies.llm_fixture_calls == 0
    assert dependencies.rag_fixture_calls > 0
    assert dependencies.persistence._observations
    assert dependencies.persistence._farms
    assert all(
        farm_id.startswith("evaluation-")
        for farm_id in dependencies.persistence._observations
    )


def test_default_scenarios_are_all_accounted_for():
    results = evaluate_all_scenarios()

    assert [item["id"] for item in results] == [
        scenario["id"] for scenario in get_all_scenarios()
    ]
    assert len({item["id"] for item in results}) == 10
    assert all(item["status"] in {"PASS", "FAIL", "BLOCKED"} for item in results)


def test_s10_runs_save_retrieve_and_format_with_in_memory_persistence():
    dependencies = make_evaluation_dependencies()
    scenario = next(item for item in get_all_scenarios() if item["id"] == "S10")

    result = evaluate_farm_memory(scenario, dependencies)

    assert result["passed"] is True
    assert result["actual"]["observations_retrieved"] == 1
    assert result["actual"]["previous_symptom_found"] is True
    assert result["actual"]["soil_agent_received_history"] is True
    assert result["actual"]["crop_agent_received_history"] is True
    assert len(dependencies.persistence._observations) == 1
    assert dependencies.persistence._farms == {"evaluation-s10"}


def test_non_isolated_dependencies_block_all_scenarios():
    class UnsafeDependencies(EvaluationFixtureDependencies):
        network_enabled = True

    results = evaluate_all_scenarios(UnsafeDependencies())

    assert len(results) == 10
    assert all(item["status"] == "BLOCKED" for item in results)


def test_valid_base_fixture_dependencies_pass_validation():
    dependencies = EvaluationFixtureDependencies()

    assert dependencies.validate_isolated() is True


def test_subclass_overriding_search_knowledge_is_blocked():
    class OverriddenSearchDependencies(EvaluationFixtureDependencies):
        def search_knowledge(self, query, n_results=3, crop=None, category=None):
            return []

    results = evaluate_all_scenarios(OverriddenSearchDependencies())

    assert len(results) == 10
    assert all(item["status"] == "BLOCKED" for item in results)


def test_subclass_overriding_llm_fixture_is_blocked():
    class OverriddenLlmDependencies(EvaluationFixtureDependencies):
        def llm_json_fixture(self, system_prompt, user_prompt):
            return {}

    results = evaluate_all_scenarios(OverriddenLlmDependencies())

    assert len(results) == 10
    assert all(item["status"] == "BLOCKED" for item in results)


def test_errors_are_sanitized_in_results_and_rendered_report(monkeypatch):
    def fail_with_sensitive_error(*args, **kwargs):
        raise RuntimeError("mongodb://private-user:secret@private-host")

    monkeypatch.setattr(runner, "soil_agent", fail_with_sensitive_error)

    results = evaluate_all_scenarios(make_evaluation_dependencies())
    report = build_report(
        results,
        timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        code_version="test-version",
    )
    rendered = render_report(report)

    assert any(item["status"] == "FAIL" for item in results)
    assert "internal details are redacted" in rendered
    assert "private-user" not in rendered
    assert "private-host" not in rendered
    assert "secret" not in rendered


def test_code_version_environment_value_is_never_exposed(monkeypatch):
    monkeypatch.setenv("AGRIVISION_CODE_VERSION", "a1b2c3d")
    assert get_code_version() == "unavailable"

    secret_shaped_values = [
        "mongodb://private-user:secret@private-host/db",
        "gsk_0123456789abcdefghijklmnopqrstuvwxyzABCDEF",
        "0123456789abcdef0123456789abcdef",  # Secret-shaped hex token.
        "release-2026.11+private",
    ]
    for value in secret_shaped_values:
        monkeypatch.setenv("AGRIVISION_CODE_VERSION", value)
        assert get_code_version() == "unavailable"


def test_report_records_metadata_scenario_data_and_dependency_modes(tmp_path):
    results = evaluate_all_scenarios()
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    report = build_report(results, timestamp=timestamp, code_version="unit-test-sha")
    report_path = write_report(report, tmp_path / "evaluation_results_current.txt")
    contents = report_path.read_text(encoding="utf-8")

    assert report["execution_timestamp_utc"] == timestamp.isoformat()
    assert report["code_version"] == "unit-test-sha"
    assert report["totals"] == {"scenario_count": 10, "pass": 10, "fail": 0, "blocked": 0}
    assert all("inputs" in item and "scenario_expected" in item for item in report["scenarios"])
    assert "no ChromaDB opened or modified" in report["dependencies"]["rag"]
    assert "real retrieval results" in " ".join(report["limitations"])
    assert "no Groq" in report["dependencies"]["llm"]
    assert "Scenario pass totals are not measures of model accuracy" in contents
    parsed_inputs = json.loads(json.dumps(report["scenarios"][0]["inputs"]))
    assert parsed_inputs == get_all_scenarios()[0]["input"]


def test_historical_report_is_unchanged_and_existing_report_is_not_overwritten(tmp_path):
    historical_path = Path(__file__).parents[1] / "evaluation" / "evaluation_results.txt"
    before = hashlib.sha256(historical_path.read_bytes()).hexdigest()
    safe_report_path = write_report(
        build_report(evaluate_all_scenarios(), code_version="test"),
        tmp_path / "evaluation_results_current.txt",
    )
    with safe_report_path.open("rb") as existing:
        original_safe_report = existing.read()

    try:
        write_report(build_report([]), safe_report_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("An existing report destination was overwritten.")

    after = hashlib.sha256(historical_path.read_bytes()).hexdigest()
    assert before == after
    assert safe_report_path.read_bytes() == original_safe_report
