
from pprint import pprint

def test_multicrop_rag(isolated_knowledge_base):
    load_knowledge_base = isolated_knowledge_base.load_knowledge_base
    search_knowledge = isolated_knowledge_base.search_knowledge
    get_knowledge_base_info = isolated_knowledge_base.get_knowledge_base_info

    print("\nREBUILDING KNOWLEDGE BASE")

    total_chunks = load_knowledge_base()

    print("Indexed chunks:", total_chunks)

    print("\nKNOWLEDGE BASE INFORMATION")
    pprint(get_knowledge_base_info())

    print("\nWHEAT-SPECIFIC SEARCH")

    wheat_results = search_knowledge(
        query="wheat crop water management and yellow leaves",
        crop="wheat"
    )

    for result in wheat_results:
        print(
            result["source"],
            "|",
            result["crop"],
            "|",
            result["category"],
            "|",
            result["section"]
        )

    print("\nGENERAL SOIL SEARCH")

    soil_results = search_knowledge(
        query="soil pH and nutrient management",
        category="soil"
    )

    for result in soil_results:
        print(
            result["source"],
            "|",
            result["category"],
            "|",
            result["section"]
        )

    assert total_chunks > 0
    assert wheat_results
    assert soil_results

    print("\nMULTI-CROP RAG TEST PASSED")


if __name__ == "__main__":
    test_multicrop_rag()
