
from pathlib import Path
import hashlib
import re
import threading

from agents.evidence import normalize_crop_id

# --------------------------------------------------
# 1. PATH CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
DB_DIR = BASE_DIR.parent / "chroma_db"


# --------------------------------------------------
# 2. CHROMADB INITIALIZATION
# --------------------------------------------------

client = None
collection = None
_index_lock = threading.RLock()
_INDEX_SCHEMA_VERSION = "2"


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


def _get_collection():
    """Open the production Chroma collection only when retrieval is requested."""
    global client, collection
    if collection is not None:
        return collection
    if client is None:
        import chromadb
        client = chromadb.PersistentClient(path=str(DB_DIR))
    from chromadb.utils import embedding_functions
    collection = client.get_or_create_collection(
        name="farm_knowledge_v2",
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
    )
    return collection


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
# 5. LOAD DOCUMENTS INTO CHROMADB
# --------------------------------------------------

def load_knowledge_base():

    knowledge_collection = _get_collection()

    documents = []
    ids = []
    metadatas = []

    document_paths = sorted(
        DOCUMENTS_DIR.rglob("*.txt")
    )
    source_fingerprint = _source_fingerprint()

    for file_path in document_paths:

        content = file_path.read_text(encoding="utf-8")

        if not content.strip():
            continue

        chunks = split_into_chunks(content)

        document_metadata = extract_document_metadata(file_path, content)

        for index, chunk in enumerate(chunks):

            documents.append(chunk["content"])

            relative_path = document_metadata["relative_path"]

            safe_id = re.sub(
                r"[^a-zA-Z0-9_-]",
                "_",
                relative_path
            )

            ids.append(f"{safe_id}_{index}")

            metadatas.append({
                **document_metadata,
                "chunk": index,
                "section": chunk["section"]
            })

    # Rebuild the collection to remove stale chunks
    existing_ids = knowledge_collection.get()["ids"]

    if existing_ids:
        knowledge_collection.delete(ids=existing_ids)

    if documents:
        knowledge_collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )

    # Chroma stores this marker with the collection so a non-empty but stale
    # index is refreshed when documents or the chunking schema changes.
    metadata = dict(getattr(knowledge_collection, "metadata", None) or {})
    metadata.update({
        "source_fingerprint": source_fingerprint,
        "index_schema_version": _INDEX_SCHEMA_VERSION,
    })
    knowledge_collection.modify(metadata=metadata)

    return knowledge_collection.count()


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
    Search agricultural knowledge using semantic similarity.

    Optional filters:
        crop: wheat, rice, maize, etc.
        category: crop, pests, diseases, soil, irrigation

    Crop-specific searches also include general knowledge.
    """

    knowledge_collection = _get_collection()
    with _index_lock:
        metadata = dict(getattr(knowledge_collection, "metadata", None) or {})
        current_fingerprint = _source_fingerprint()
        if (
            knowledge_collection.count() == 0
            or metadata.get("source_fingerprint") != current_fingerprint
            or metadata.get("index_schema_version") != _INDEX_SCHEMA_VERSION
        ):
            load_knowledge_base()

    total_chunks = knowledge_collection.count()

    if total_chunks == 0:
        return []

    filters = []

    if crop:
        crop_name = normalize_crop_id(crop)

        filters.append({
            "$or": [
                {"crop": crop_name},
                {"crop": "general"}
            ]
        })

    if category:
        filters.append({
            "category": category.strip().lower()
        })

    where = None

    if len(filters) == 1:
        where = filters[0]

    elif len(filters) > 1:
        where = {"$and": filters}

    available = knowledge_collection.get(
        where=where,
        include=["metadatas"]
    )

    available_count = len(available["ids"])

    if available_count == 0:
        return []

    results = knowledge_collection.query(
        query_texts=[query],
        n_results=min(n_results, available_count),
        where=where
    )

    matches = []

    for document, metadata in zip(
        results["documents"][0],
        results["metadatas"][0]
    ):

        metadata = dict(metadata or {})
        relative_path = metadata.get("relative_path")
        source_path = (DOCUMENTS_DIR / relative_path).resolve() if relative_path else None
        try:
            source_path.relative_to(DOCUMENTS_DIR.resolve())
            source_text = source_path.read_text(encoding="utf-8")
            local_title = next(
                (line.strip() for line in source_text.splitlines() if line.strip()),
                "Unavailable",
            )
            normalized_source = re.sub(r"\s+", " ", source_text).strip()
            normalized_chunk = re.sub(r"\s+", " ", document).strip()
            if not normalized_chunk or normalized_chunk not in normalized_source:
                continue
        except (AttributeError, OSError, ValueError):
            local_title = "Unavailable"
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

    knowledge_collection = _get_collection()

    documents = sorted(
        DOCUMENTS_DIR.rglob("*.txt")
    )

    return {
        "total_chunks": knowledge_collection.count(),
        "total_documents": len(documents),
        "collection_name": knowledge_collection.name,
        "document_directory": str(DOCUMENTS_DIR)
    }
