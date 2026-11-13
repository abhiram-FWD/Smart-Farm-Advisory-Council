
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
