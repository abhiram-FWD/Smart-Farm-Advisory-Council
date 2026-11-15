
import pytest


def test_general_rag_retrieval(isolated_knowledge_base):
    load_knowledge_base = isolated_knowledge_base.load_knowledge_base
    search_knowledge = isolated_knowledge_base.search_knowledge
    get_knowledge_base_info = isolated_knowledge_base.get_knowledge_base_info

    count = load_knowledge_base()

    assert count > 0, "Knowledge base contains no indexed chunks"

    info = get_knowledge_base_info()

    assert info is not None

    queries = [
        "What causes yellow leaves and wilting in wheat?",
        "How should soil pH and nutrients be managed?",
        "What factors should be considered before irrigation?"
    ]

    for query in queries:

        results = search_knowledge(query)

        assert results, f"No documents retrieved for query: {query}"

        for result in results:
            assert result.get("source"), "Retrieved source is missing"
            assert result.get("content"), "Retrieved content is missing"


def test_nonempty_stale_index_is_refreshed(isolated_knowledge_base):
    knowledge_base = isolated_knowledge_base
    knowledge_base.load_knowledge_base()
    knowledge_base._knowledge_index["fingerprint"] = "stale-source-fingerprint"

    results = knowledge_base.search_knowledge("soil pH management", category="soil")

    assert results
    assert knowledge_base._knowledge_index["fingerprint"] == knowledge_base._source_fingerprint()


def test_rag_returns_traceable_provenance_with_unavailable_fields(isolated_knowledge_base):
    isolated_knowledge_base.load_knowledge_base()
    results = isolated_knowledge_base.search_knowledge(
        "soil moisture and soil pH", category="soil"
    )

    assert results
    result = results[0]
    assert result["title"] == "SOIL MANAGEMENT AND AGRONOMY GUIDE"
    assert result["filename"] == "soil_management.txt"
    assert result["section"]
    assert result["relative_path"] == "soil_management.txt"
    assert result["author"] == "Unavailable"
    assert result["organization"] == "Unavailable"
    assert result["publication_date"] == "Unavailable"
    assert result["revision_date"] == "Unavailable"
    assert result["source_url"] == "Unavailable"
    assert result["source_document_status"] == "verified_local_document"
    assert result["provenance_status"] == "weak_or_unavailable"


def test_tfidf_retrieval_ranks_relevant_crop_guide_and_returns_citation(isolated_knowledge_base):
    isolated_knowledge_base.load_knowledge_base()
    results = isolated_knowledge_base.search_knowledge(
        "wheat aphids colonies sticky honeydew yellow curling leaves",
        n_results=3,
        crop="Wheat",
        category="pests",
    )

    assert results
    assert results[0]["relative_path"] == "pests/wheat_pests.txt"
    assert "aphids" in results[0]["content"].lower()
    assert results[0]["source"] == "wheat_pests.txt"
    assert results[0]["evidence_id"].startswith("pests/wheat_pests.txt::")
    assert results[0]["source_document_status"] == "verified_local_document"


@pytest.mark.parametrize("crop", ["Wheat", "WHEAT", "sugar-cane", "corn"])
def test_crop_filter_normalizes_supported_crop_spellings(isolated_knowledge_base, crop):
    isolated_knowledge_base.load_knowledge_base()
    results = isolated_knowledge_base.search_knowledge(
        f"{crop} pest and disease prevention", crop=crop, category="pests"
    )
    assert results
    expected = "maize" if crop.casefold() == "corn" else "sugarcane" if crop.casefold() == "sugar-cane" else "wheat"
    assert all(item["crop"] in {expected, "general"} for item in results)
    assert any(item["crop"] == expected for item in results)


@pytest.mark.parametrize("crop", ["Wheat", "Rice", "Maize", "Corn", "Cotton", "Tomato", "Sugarcane", "Sugar cane"])
def test_each_documented_crop_retrieves_its_own_pest_documents(isolated_knowledge_base, crop):
    isolated_knowledge_base.load_knowledge_base()
    results = isolated_knowledge_base.search_knowledge(
        f"{crop} pests crop damage", crop=crop, category="pests"
    )
    expected = "maize" if crop.casefold() == "corn" else "sugarcane" if crop.casefold() == "sugar cane" else crop.casefold()
    assert any(item["crop"] == expected for item in results)
