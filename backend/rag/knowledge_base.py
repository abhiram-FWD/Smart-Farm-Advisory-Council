
from pathlib import Path
import hashlib
import math
import re
import threading
from collections import Counter

from agents.evidence import normalize_crop_id

# --------------------------------------------------
# 1. PATH CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"


# --------------------------------------------------
# 2. LIGHTWEIGHT TF-IDF INDEX
# --------------------------------------------------

_index_lock = threading.RLock()
_INDEX_SCHEMA_VERSION = "3-tfidf"
_knowledge_index = {
    "fingerprint": None,
    "chunks": [],
    "idf": {},
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "for", "from",
    "how", "in", "into", "is", "it", "of", "on", "or", "the", "this",
    "to", "what", "when", "which", "with",
}


def _source_fingerprint():
    """Return a stable fingerprint for the local documents and chunking schema."""
    digest = hashlib.sha256(_INDEX_SCHEMA_VERSION.encode("utf-8"))
    for path in sorted(DOCUMENTS_DIR.rglob("*.txt")):
        relative = path.relative_to(DOCUMENTS_DIR).as_posix()
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------
# 3. DOCUMENT METADATA
# --------------------------------------------------

def extract_document_metadata(file_path, document_text=None):
    """
    Derive document metadata from its folder and filename.
    No fixed crop list is required.
    """

    relative_path = file_path.relative_to(DOCUMENTS_DIR)
    parts = relative_path.parts

    folder = parts[0] if len(parts) > 1 else "general"
    filename = file_path.stem.lower()

    if folder == "crops":
        category = "crop"
        crop = re.sub(r"(_guide|_knowledge)$", "", filename)

    elif folder in ("pests", "diseases"):
        category = folder
        suffix = f"_{category}"

        crop = (
            filename[:-len(suffix)]
            if filename.endswith(suffix)
            else "general"
        )

    elif "soil" in filename:
        category = "soil"
        crop = "general"

    elif "irrigation" in filename or "water" in filename:
        category = "irrigation"
        crop = "general"

    else:
        category = "general"
        crop = "general"

    if document_text is None:
        document_text = file_path.read_text(encoding="utf-8")
    document_title = next(
        (line.strip() for line in document_text.splitlines() if line.strip()),
        "Unavailable",
    )

    return {
        "source": file_path.name,
        "title": document_title,
        "filename": file_path.name,
        "relative_path": relative_path.as_posix(),
        "crop": crop,
        "crop_applicability": crop,
        "category": category,
        "pest_or_disease_category": category if category in ("pests", "diseases") else "Unavailable",
        "author": "Unavailable",
        "organization": "Unavailable",
        "publication_date": "Unavailable",
        "revision_date": "Unavailable",
        "source_url": "Unavailable",
    }


# --------------------------------------------------
# 4. DOCUMENT CHUNKING
# --------------------------------------------------

def split_into_chunks(text):
    """
    Split documents using numbered headings.
    Preserve the section heading with its content.
    """

    sections = []
    current_section = []
    current_heading = "Introduction"

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        is_heading = (
            len(line) > 2
            and line[0].isdigit()
            and ". " in line[:5]
        )

        if is_heading:

            if current_section:
                sections.append({
                    "section": current_heading,
                    "content": "\n".join(current_section)
                })

            current_heading = line
            current_section = [line]

        else:
            current_section.append(line)

    if current_section:
        sections.append({
            "section": current_heading,
            "content": "\n".join(current_section)
        })

    return sections


# --------------------------------------------------
# 5. LOAD DOCUMENTS INTO THE TF-IDF INDEX
# --------------------------------------------------

def _tokens(text):
    return [token for token in _TOKEN_PATTERN.findall(text.lower()) if token not in _STOP_WORDS]


def _build_index(source_fingerprint=None):
    chunks = []
    document_frequencies = Counter()

    for file_path in sorted(DOCUMENTS_DIR.rglob("*.txt")):
        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            continue
        document_metadata = extract_document_metadata(file_path, content)
        for index, chunk in enumerate(split_into_chunks(content)):
            terms = Counter(_tokens(chunk["content"]))
            if not terms:
                continue
            document_frequencies.update(terms.keys())
            chunks.append({
                "content": chunk["content"],
                "terms": terms,
                "metadata": {
                    **document_metadata,
                    "chunk": index,
                    "section": chunk["section"],
                },
            })

    total = len(chunks)
    idf = {
        term: math.log((total + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequencies.items()
    }
    for chunk in chunks:
        weighted_terms = {
            term: (1 + math.log(count)) * idf[term]
            for term, count in chunk["terms"].items()
        }
        magnitude = math.sqrt(sum(weight * weight for weight in weighted_terms.values())) or 1
        chunk["vector"] = {term: weight / magnitude for term, weight in weighted_terms.items()}

    return {
        "fingerprint": source_fingerprint or _source_fingerprint(),
        "chunks": chunks,
        "idf": idf,
    }


def _get_index():
    global _knowledge_index
    fingerprint = _source_fingerprint()
    if _knowledge_index["fingerprint"] != fingerprint:
        with _index_lock:
            if _knowledge_index["fingerprint"] != fingerprint:
                _knowledge_index = _build_index(fingerprint)
    return _knowledge_index


def load_knowledge_base():
    """Index all local agricultural guides using sparse TF-IDF vectors."""
    global _knowledge_index
    with _index_lock:
        _knowledge_index = _build_index()
        return len(_knowledge_index["chunks"])


# --------------------------------------------------
# 6. SEARCH RELEVANT KNOWLEDGE
# --------------------------------------------------

def search_knowledge(
    query,
    n_results=3,
    crop=None,
    category=None
):
    """
    Search agricultural knowledge using lightweight TF-IDF similarity.

    Optional filters:
        crop: wheat, rice, maize, etc.
        category: crop, pests, diseases, soil, irrigation

    Crop-specific searches also include general knowledge.
    """

    index = _get_index()
    if not index["chunks"]:
        return []

    crop_name = normalize_crop_id(crop) if crop else None
    query_terms = Counter(_tokens(query or ""))
    if not query_terms:
        return []
    weighted_query = {
        term: (1 + math.log(count)) * index["idf"].get(term, 0)
        for term, count in query_terms.items()
    }
    query_magnitude = math.sqrt(sum(weight * weight for weight in weighted_query.values())) or 1
    weighted_query = {term: weight / query_magnitude for term, weight in weighted_query.items()}

    ranked = []
    for chunk in index["chunks"]:
        metadata = chunk["metadata"]
        if category and metadata["category"] != category.strip().lower():
            continue
        if crop_name and metadata["crop"] not in {crop_name, "general"}:
            continue
        score = sum(weight * chunk["vector"].get(term, 0) for term, weight in weighted_query.items())
        if score > 0:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]["metadata"]["relative_path"], item[1]["metadata"]["chunk"]))

    matches = []
    for _, chunk in ranked[:max(0, n_results)]:
        document = chunk["content"]
        metadata = dict(chunk["metadata"])
        relative_path = metadata.get("relative_path")
        source_path = (DOCUMENTS_DIR / relative_path).resolve() if relative_path else None
        try:
            source_path.relative_to(DOCUMENTS_DIR.resolve())
            source_text = source_path.read_text(encoding="utf-8")
            local_title = next((line.strip() for line in source_text.splitlines() if line.strip()), "Unavailable")
            if not re.sub(r"\s+", " ", document).strip() in re.sub(r"\s+", " ", source_text).strip():
                continue
        except (AttributeError, OSError, ValueError):
            continue

        metadata.setdefault("title", local_title)
        metadata.setdefault("filename", metadata.get("source", "Unavailable"))
        metadata.setdefault("crop_applicability", metadata.get("crop", "Unavailable"))
        metadata.setdefault(
            "pest_or_disease_category",
            metadata.get("category") if metadata.get("category") in ("pests", "diseases") else "Unavailable",
        )
        for field in (
            "author", "organization", "publication_date", "revision_date", "source_url"
        ):
            metadata.setdefault(field, "Unavailable")

        metadata["source_document_status"] = "verified_local_document"
        metadata["provenance_status"] = (
            "metadata_available" if any(
                metadata.get(field) != "Unavailable"
                for field in ("author", "organization", "publication_date", "revision_date", "source_url")
            ) else "weak_or_unavailable"
        )

        evidence_id = f"{metadata.get('relative_path', metadata.get('source', 'unknown'))}::{metadata.get('section', 'Unavailable')}::{metadata.get('chunk', 0)}"

        matches.append({
            "content": document,
            "evidence_id": evidence_id,
            "title": metadata["title"],
            "source": metadata["source"],
            "filename": metadata["filename"],
            "relative_path": metadata["relative_path"],
            "crop": metadata["crop"],
            "crop_applicability": metadata["crop_applicability"],
            "category": metadata["category"],
            "pest_or_disease_category": metadata["pest_or_disease_category"],
            "author": metadata["author"],
            "organization": metadata["organization"],
            "publication_date": metadata["publication_date"],
            "revision_date": metadata["revision_date"],
            "source_url": metadata["source_url"],
            "source_document_status": metadata["source_document_status"],
            "provenance_status": metadata["provenance_status"],
            "section": metadata["section"],
            "chunk": metadata["chunk"]
        })

    return matches


# --------------------------------------------------
# 7. KNOWLEDGE BASE INFORMATION
# --------------------------------------------------

def get_knowledge_base_info():
    index = _get_index()
    documents = sorted(DOCUMENTS_DIR.rglob("*.txt"))

    return {
        "total_chunks": len(index["chunks"]),
        "total_documents": len(documents),
        "collection_name": "agronomy_tfidf_v1",
        "document_directory": str(DOCUMENTS_DIR)
    }
