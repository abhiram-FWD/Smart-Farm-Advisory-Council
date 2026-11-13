"""Deterministic, non-operational dependencies for evaluation only."""

from copy import deepcopy


class InMemoryEvaluationPersistence:
    """Small isolated store implementing the runner's history operations."""

    evaluation_only = True
    persistent = False

    def __init__(self):
        self._farms = set()
        self._observations = {}
        self._next_id = 1

    def save_farm_observation(self, farm_id, observation):
        if not isinstance(farm_id, str) or not farm_id.startswith("evaluation-"):
            raise ValueError("Evaluation persistence only accepts evaluation IDs.")
        if not isinstance(observation, dict):
            raise ValueError("Evaluation observations must be dictionaries.")

        self._farms.add(farm_id)
        observation_id = f"evaluation-observation-{self._next_id}"
        self._next_id += 1
        self._observations.setdefault(farm_id, []).append({
            "observation_id": observation_id,
            "farm_id": farm_id,
            "observation": deepcopy(observation),
            "created_at": None,
        })
        return observation_id

    def get_farm_history(self, farm_id, limit=10):
        if not isinstance(farm_id, str) or not farm_id.startswith("evaluation-"):
            raise ValueError("Evaluation persistence only accepts evaluation IDs.")
        return deepcopy(list(reversed(self._observations.get(farm_id, [])))[:limit])


class EvaluationFixtureDependencies:
    """Safe fixture adapters; none call the application's live services."""

    evaluation_only = True
    network_enabled = False
    persistent_storage = False
    dependency_description = {
        "persistence": "isolated in-memory fixture",
        "rag": "deterministic evaluation fixture; not real retrieval",
        "llm": "deterministic evaluation fixture; not a real AI response",
        "weather": "not called; rainfall comes from scenario inputs",
        "network": "disabled",
    }

    def __init__(self):
        self.persistence = InMemoryEvaluationPersistence()
        self.llm_fixture_calls = 0
        self.rag_fixture_calls = 0

    def search_knowledge(self, query, n_results=3, crop=None, category=None):
        self.rag_fixture_calls += 1
        fixture_category = category or "soil"
        fixture_crop = crop or "general"
        return [{
            "relative_path": f"evaluation/{fixture_category}",
            "evidence_id": f"evaluation-{fixture_category}-fixture",
            "source": f"EVALUATION_FIXTURE:{fixture_category}",
            "content": "Evaluation-only retrieval marker; not agricultural evidence.",
            "title": "Evaluation fixture",
            "filename": f"{fixture_category}.fixture",
            "category": fixture_category,
            "crop": fixture_crop,
            "section": "Evaluation fixture",
            "author": "Unavailable",
            "organization": "Unavailable",
            "publication_date": "Unavailable",
            "revision_date": "Unavailable",
            "source_url": "Unavailable",
            "evaluation_only": True,
        }]

    def llm_json_fixture(self, system_prompt, user_prompt):
        """Return neutral fixture-shaped data, never diagnoses or advice."""
        self.llm_fixture_calls += 1
        if "soil information assistant" in system_prompt:
            return {
                "interpretations": [],
                "recommendations": [],
                "expert_review_required": True,
            }
        return {
            "possible_pest_risks": [],
            "possible_disease_risks": [],
            "recommendations": [],
            "expert_inspection_required": True,
        }

    def validate_isolated(self):
        return bool(
            type(self) is EvaluationFixtureDependencies
            and type(self).search_knowledge is _TRUSTED_SEARCH_KNOWLEDGE
            and type(self).llm_json_fixture is _TRUSTED_LLM_JSON_FIXTURE
            and getattr(self.search_knowledge, "__func__", None)
            is _TRUSTED_SEARCH_KNOWLEDGE
            and getattr(self.llm_json_fixture, "__func__", None)
            is _TRUSTED_LLM_JSON_FIXTURE
            and self.evaluation_only
            and not self.network_enabled
            and not self.persistent_storage
            and type(self.persistence) is InMemoryEvaluationPersistence
            and self.persistence.evaluation_only
            and not self.persistence.persistent
        )


# Keep references to the approved implementations so runtime method replacement
# cannot make a modified implementation validate as an isolated fixture.
_TRUSTED_SEARCH_KNOWLEDGE = EvaluationFixtureDependencies.search_knowledge
_TRUSTED_LLM_JSON_FIXTURE = EvaluationFixtureDependencies.llm_json_fixture


def make_evaluation_dependencies():
    return EvaluationFixtureDependencies()
