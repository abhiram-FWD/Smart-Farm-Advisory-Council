"""Run the deterministic, isolated Agri Vision evaluation scenarios."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from agents.crop_health_agent import crop_health_agent
from agents.irrigation_agent import irrigation_agent
from agents.soil_agent import soil_agent
from evaluation.dependencies import make_evaluation_dependencies
from evaluation.scenarios import get_all_scenarios
from memory.farm_history import format_farm_history


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "evaluation_results_current.txt"
REPORT_LIMITATIONS = [
    "LLM outputs and RAG matches are deterministic evaluation fixtures, not live Groq responses, real retrieval results, diagnoses, or agricultural advice.",
    "The evaluation does not establish real-world model accuracy, agricultural validity, or the quality of external provider data.",
    "Weather APIs and full Semantic Kernel orchestration are not evaluated.",
]


class UnsafeEvaluationDependencies(RuntimeError):
    """Raised when dependencies cannot prove they are isolated fixtures."""


def evaluate_irrigation(scenario):
    data = scenario["input"]
    expected = scenario["expected"]
    result = irrigation_agent(
        soil_moisture=data["moisture"],
        expected_rainfall=data["expected_rainfall"],
        crop_name=data["crop_name"],
    )
    expected_actions = {
        "irrigation": "consider irrigation",
        "recheck_before_irrigation": "recheck before irrigating",
        "postpone_irrigation": "consider postponing irrigation",
        "no_immediate_irrigation": "no immediate irrigation indicated",
    }
    expected_action = expected_actions[expected["action"]]
    actual_action = result["recommended_action"]
    return {
        "passed": actual_action.casefold() == expected_action,
        "check_type": "deterministic rule check",
        "actual": {"recommended_action": actual_action},
        "expected": {"recommended_action": expected_action},
    }


def evaluate_soil(scenario, dependencies):
    data = scenario["input"]
    result = soil_agent(
        moisture=data["moisture"],
        ph=data["ph"],
        nitrogen=data["nitrogen"],
        phosphorus=data["phosphorus"],
        potassium=data["potassium"],
        knowledge_searcher=dependencies.search_knowledge,
        llm_json=dependencies.llm_json_fixture,
    )
    expected = set(scenario["expected"]["risks"])
    actual = set(result.get("preliminary_rule_indicators", []))
    return {
        "passed": expected == actual,
        "check_type": "deterministic soil rule check; non-evidence retrieval fixture rejected and model skipped",
        "actual": {"preliminary_rule_indicators": sorted(actual)},
        "expected": {"preliminary_rule_indicators": sorted(expected)},
    }


def evaluate_crop_health(scenario, dependencies):
    data = scenario["input"]
    expected = scenario["expected"]
    llm_calls_before = dependencies.llm_fixture_calls
    result = crop_health_agent(
        crop_name=data["crop_name"],
        growth_stage=data["growth_stage"],
        symptoms=data["symptoms"],
        knowledge_searcher=dependencies.search_knowledge,
        llm_json=dependencies.llm_json_fixture,
    )
    sources = result.get("retrieved_sources", [])
    checks = []
    if expected.get("rag_required"):
        checks.append(bool(sources))
    if expected.get("expert_inspection"):
        checks.append(result.get("expert_inspection_required") is True)
    return {
        "passed": all(checks),
        "check_type": "isolated retrieval-fixture and insufficient-evidence safety check; not retrieval or model accuracy",
        "actual": {
            "fixture_source_count": len(sources),
            "relevant_evidence_source_count": len(result.get("evidence_sources", [])),
            "llm_fixture_called": dependencies.llm_fixture_calls > llm_calls_before,
            "possible_pest_risks": result.get("possible_pest_risks", []),
            "possible_disease_risks": result.get("possible_disease_risks", []),
            "expert_inspection_required": result.get("expert_inspection_required", False),
        },
        "expected": expected,
    }


def evaluate_farm_memory(scenario, dependencies):
    data = scenario["input"]
    persistence = dependencies.persistence
    farm_id = f"evaluation-{scenario['id'].lower()}"

    for previous in scenario["previous_observations"]:
        persistence.save_farm_observation(farm_id, {
            "soil_moisture": previous["moisture"],
            "soil_ph": previous["ph"],
            "nitrogen": previous["nitrogen"],
            "phosphorus": previous["phosphorus"],
            "potassium": previous["potassium"],
            "crop_name": previous["crop_name"],
            "growth_stage": previous["growth_stage"],
            "symptoms": previous["symptoms"],
        })

    history = persistence.get_farm_history(farm_id, limit=10)
    historical_context = format_farm_history(history)
    history_retrieved = (
        len(history) >= len(scenario["previous_observations"])
        and bool(historical_context)
        and "wilting" in historical_context
    )
    soil_result = soil_agent(
        moisture=data["moisture"],
        ph=data["ph"],
        nitrogen=data["nitrogen"],
        phosphorus=data["phosphorus"],
        potassium=data["potassium"],
        historical_context=historical_context,
        knowledge_searcher=dependencies.search_knowledge,
        llm_json=dependencies.llm_json_fixture,
    )
    crop_result = crop_health_agent(
        crop_name=data["crop_name"],
        growth_stage=data["growth_stage"],
        symptoms=data["symptoms"],
        historical_context=historical_context,
        knowledge_searcher=dependencies.search_knowledge,
        llm_json=dependencies.llm_json_fixture,
    )
    soil_received_history = soil_result.get("historical_context_used") is True
    crop_received_history = crop_result.get("historical_context_used") is True
    passed = history_retrieved and soil_received_history and crop_received_history
    return {
        "passed": passed,
        "check_type": "isolated in-memory persistence and context-formatting check; non-evidence retrieval rejected",
        "actual": {
            "observations_retrieved": len(history),
            "historical_context_created": bool(historical_context),
            "previous_symptom_found": "wilting" in historical_context,
            "soil_agent_received_history": soil_received_history,
            "crop_agent_received_history": crop_received_history,
        },
        "expected": scenario["expected"],
    }


def _scenario_dependencies(category):
    if category == "irrigation":
        return ["local deterministic irrigation rule"]
    if category == "soil":
        return ["local deterministic soil rules", "RAG fixture", "LLM response fixture"]
    if category == "crop_health":
        return ["RAG fixture", "LLM response fixture"]
    if category == "farm_memory":
        return ["in-memory persistence fixture", "RAG fixture", "LLM response fixture"]
    return ["none; unsupported category"]


def _run_scenario(scenario, dependencies):
    category = scenario.get("category")
    if category == "irrigation":
        return evaluate_irrigation(scenario)
    if category == "soil":
        return evaluate_soil(scenario, dependencies)
    if category == "crop_health":
        return evaluate_crop_health(scenario, dependencies)
    if category == "farm_memory":
        return evaluate_farm_memory(scenario, dependencies)
    return {
        "status": "BLOCKED",
        "check_type": "unsupported scenario category",
        "actual": None,
        "expected": scenario.get("expected"),
        "error": "Scenario category is not supported by the isolated runner.",
    }


def evaluate_all_scenarios(dependencies=None, scenarios=None):
    dependencies = dependencies or make_evaluation_dependencies()
    scenarios = get_all_scenarios() if scenarios is None else scenarios
    try:
        isolated = dependencies.validate_isolated()
    except Exception:
        isolated = False
    if not isolated:
        return [
            {
                "id": scenario.get("id"),
                "name": scenario.get("name"),
                "inputs": scenario.get("input", {}),
                "expected": scenario.get("expected"),
                "scenario_expected": scenario.get("expected"),
                "status": "BLOCKED",
                "check_type": "isolation validation",
                "dependencies": _scenario_dependencies(scenario.get("category")),
                "actual": None,
                "error": "Evaluation dependencies did not pass isolation validation.",
            }
            for scenario in scenarios
        ]

    results = []
    for scenario in scenarios:
        try:
            outcome = _run_scenario(scenario, dependencies)
            status = outcome.get("status") or ("PASS" if outcome["passed"] else "FAIL")
            error = outcome.get("error")
        except Exception:
            # Deliberately omit exception strings, provider details, paths and credentials.
            outcome = {
                "check_type": "scenario execution",
                "actual": None,
                "expected": scenario.get("expected"),
            }
            status = "FAIL"
            error = "Scenario execution failed; internal details are redacted."

        results.append({
            "id": scenario.get("id"),
            "name": scenario.get("name"),
            "inputs": scenario.get("input", {}),
            "scenario_expected": scenario.get("expected"),
            "expected": outcome.get("expected", scenario.get("expected")),
            "actual": outcome.get("actual"),
            "status": status,
            "check_type": outcome.get("check_type", "unspecified"),
            "dependencies": _scenario_dependencies(scenario.get("category")),
            **({"error": error} if error else {}),
        })
    return results


def get_code_version():
    configured = os.getenv("AGRIVISION_CODE_VERSION")
    if configured:
        # The value's format cannot prove it is a commit ID rather than a
        # secret-shaped token, so never reflect an environment value.
        return "unavailable"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        version = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", version):
            return "unavailable"
        working_tree = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return f"{version}-working-tree" if working_tree.stdout.strip() else version
    except Exception:
        return "unavailable"


def build_report(results, timestamp=None, code_version=None):
    totals = {
        status.lower(): sum(item["status"] == status for item in results)
        for status in ("PASS", "FAIL", "BLOCKED")
    }
    report = {
        "title": "Agri Vision Isolated Evaluation Report",
        "execution_timestamp_utc": (
            timestamp or datetime.now(timezone.utc)
        ).isoformat(),
        "code_version": code_version if code_version is not None else get_code_version(),
        "execution_mode": "deterministic isolated evaluation fixtures",
        "dependencies": {
            "persistence": "in-memory only",
            "rag": "fixture-backed; production retrieval uses local sparse TF-IDF; no embedding model",
            "llm": "fixture-backed; no Groq or other live LLM called",
            "weather": "not called; rainfall supplied by scenario inputs",
            "network": "not used by the evaluation runner",
        },
        "limitations": REPORT_LIMITATIONS,
        "scenarios": results,
        "totals": {
            "scenario_count": len(results),
            **totals,
        },
    }
    return report


def render_report(report):
    lines = [
        report["title"],
        "=" * len(report["title"]),
        f"Execution timestamp (UTC): {report['execution_timestamp_utc']}",
        f"Code version: {report['code_version']}",
        f"Execution mode: {report['execution_mode']}",
        "",
        "Dependency isolation:",
        json.dumps(report["dependencies"], indent=2, ensure_ascii=False),
        "",
        "Limitations:",
    ]
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    for scenario in report["scenarios"]:
        lines.extend([
            "",
            f"{scenario['id']} | {scenario['status']} | {scenario['name']}",
            f"Check type: {scenario['check_type']}",
            f"Dependencies: {', '.join(scenario['dependencies'])}",
            f"Inputs: {json.dumps(scenario['inputs'], ensure_ascii=False, sort_keys=True)}",
            f"Expected: {json.dumps(scenario['expected'], ensure_ascii=False, sort_keys=True)}",
            f"Scenario declared expectation: {json.dumps(scenario['scenario_expected'], ensure_ascii=False, sort_keys=True)}",
            f"Actual: {json.dumps(scenario['actual'], ensure_ascii=False, sort_keys=True)}",
        ])
        if scenario.get("error"):
            lines.append(f"Error: {scenario['error']}")
    lines.extend([
        "",
        "Totals:",
        json.dumps(report["totals"], sort_keys=True),
        "",
        "Scenario pass totals are not measures of model accuracy or agricultural reliability.",
    ])
    return "\n".join(lines) + "\n"


def write_report(report, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation guarantees the historical report or any prior current report is not overwritten.
    with output_path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(render_report(report))
    return output_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="new report path; existing files are never overwritten",
    )
    args = parser.parse_args(argv)

    if args.output.exists():
        print("Report destination already exists; refusing to overwrite it.", file=sys.stderr)
        return 2

    try:
        dependencies = make_evaluation_dependencies()
        results = evaluate_all_scenarios(dependencies)
        report = build_report(results)
        write_report(report, args.output)
    except FileExistsError:
        print("Report destination already exists; refusing to overwrite it.", file=sys.stderr)
        return 2
    except Exception:
        print("Evaluation could not complete; internal details are redacted.", file=sys.stderr)
        return 1

    print("Isolated evaluation report created.")
    return 0 if all(item["status"] == "PASS" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
