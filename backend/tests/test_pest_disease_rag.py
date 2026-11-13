
import pytest


@pytest.mark.parametrize(
    "crop",
    ["wheat", "rice", "maize", "cotton", "tomato", "sugarcane"]
)
@pytest.mark.parametrize(
    "category",
    ["pests", "diseases"]
)
def test_pest_disease_rag(crop, category, isolated_knowledge_base):

    # Rebuild/load the knowledge base.
    total_chunks = isolated_knowledge_base.load_knowledge_base()

    assert total_chunks > 0, "Knowledge base contains no indexed chunks"

    results = isolated_knowledge_base.search_knowledge(
        query=f"{crop} {category} symptoms and identification",
        n_results=3,
        crop=crop,
        category=category
    )

    assert results, (
        f"No RAG documents found for {crop} - {category}"
    )

    for result in results:
        assert result["crop"] == crop, (
            f"Incorrect crop returned: {result['crop']}"
        )

        assert result["category"] == category, (
            f"Incorrect category returned: {result['category']}"
        )

        assert result.get("source"), "Retrieved source is missing"
