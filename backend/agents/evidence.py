"""Small validation helpers for source-linked agent output."""

import re


UNAVAILABLE = "Unavailable"


def normalize_text(value):
    return " ".join(re.findall(r"\w+", str(value).casefold()))


def normalize_passages(results):
    """Keep only well-formed passages and give each a stable local ID."""
    passages = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        source = item.get("source")
        if not isinstance(content, str) or not content.strip() or not isinstance(source, str) or not source.strip():
            continue
        relative_path = item.get("relative_path") or item.get("filename") or source
        section = item.get("section") or UNAVAILABLE
        chunk = item.get("chunk", 0)
        evidence_id = item.get("evidence_id") or f"{relative_path}::{section}::{chunk}"
        passages.append({
            **item,
            "evidence_id": str(evidence_id),
            "content": content.strip(),
            "source": source,
            "title": item.get("title") or UNAVAILABLE,
            "filename": item.get("filename") or source,
            "relative_path": relative_path,
            "section": section,
            "crop": item.get("crop") or "general",
            "category": item.get("category") or "general",
            "author": item.get("author") or UNAVAILABLE,
            "organization": item.get("organization") or UNAVAILABLE,
            "publication_date": item.get("publication_date") or UNAVAILABLE,
            "revision_date": item.get("revision_date") or UNAVAILABLE,
            "source_url": item.get("source_url") or UNAVAILABLE,
        })
    return passages


def passage_is_relevant(passage, query, crop=None, category=None):
    if passage.get("evaluation_only") or str(passage.get("source", "")).startswith("EVALUATION_FIXTURE:"):
        return False
    if category and passage.get("category") not in {category, "general"}:
        return False
    if crop and passage.get("crop") not in {crop.casefold().replace(" ", "_"), "general"}:
        return False
    query_terms = {
        token for token in normalize_text(query).split()
        if len(token) > 2 and token not in {
            "the", "and", "for", "with", "from", "possible", "reported",
            "current", "identify", "identification", "management", "guide",
            "agent", "soil", "crop", "pest", "disease", "symptoms",
            "about", "evidence", "measurement", "measurements", "interpreting",
            "condition", "conditions", "unspecified",
        }
    }
    if crop:
        query_terms -= set(normalize_text(crop).split())
    passage_terms = set(normalize_text(passage["content"]).split())
    return bool(query_terms & passage_terms)


def find_passage(passages, evidence_id, category=None):
    if not isinstance(evidence_id, str):
        return None
    for passage in passages:
        if passage["evidence_id"] == evidence_id and (
            category is None or passage.get("category") == category
        ):
            return passage
    return None


def exact_source_text(text, passage):
    """Require model text to be a verbatim excerpt of the cited passage."""
    if not isinstance(text, str) or not text.strip():
        return False
    return normalize_text(text) in normalize_text(passage.get("content", ""))


def retrieved_passages_conflict(passages):
    """Flag a narrow, deterministic heuristic for near-identical opposite polarity.

    This does not detect semantic conflicts expressed with substantially
    different wording; callers must not treat a negative result as proof that
    retrieved sources agree.
    """
    negative = {
        "not", "never", "cannot", "can't", "avoid", "prohibit", "prohibited",
        "forbidden", "contraindicated", "without",
    }
    for index, left in enumerate(passages):
        left_terms = set(normalize_text(left["content"]).split())
        for right in passages[index + 1:]:
            right_terms = set(normalize_text(right["content"]).split())
            left_negative = bool(left_terms & negative)
            right_negative = bool(right_terms & negative)
            left_core = left_terms - negative
            right_core = right_terms - negative
            shared = left_core & right_core
            union = left_core | right_core
            if left_negative != right_negative and union and len(shared) / len(union) >= 0.75:
                return True
    return False


def supports_symptom_risk_relationship(name, symptoms, passage):
    """Require symptom and risk to be participants in one explicit relation clause.

    This intentionally narrow lexical check is not semantic entailment. It
    rejects co-occurrence, unrelated clauses, and uncertain or denied relations.
    """
    risk = _phrase_pattern(name)
    if not risk:
        return False
    denial = re.compile(
        r"\b(?:not|no|never|unlikely|possibly|potentially|uncertain|unclear|"
        r"unconfirmed|unestablished|ruled\s+out|excluded?|without|cannot|can't|does\s+not|do\s+not|"
        r"isn't|aren't)\b",
        re.I,
    )
    relationship_reference = re.compile(
        r"\b(?:(?:the|this|that|such)\s+)?(?:relationship|association|link|connection)\b",
        re.I,
    )
    anaphoric_relationship = re.compile(
        r"\b(?:their|these|those|this|that|the)\s+"
        r"(?:relationship|association|link|connection)\b",
        re.I,
    )
    content = passage.get("content", "")
    # Relationship matching is bounded to simple clauses. Coordinated clauses
    # are split even when the conjunction does not introduce a contrast.
    clauses = re.split(
        r"(?<=[.!?;])\s+|[;:]|,\s*(?=(?:and|but|or|while|whereas|although|however)\b)|"
        r"\s+\b(?:and|but|or|while|whereas|although|however)\b\s+|\n+",
        content, flags=re.I,
    )
    positive_relation = False
    for symptom in symptoms if isinstance(symptoms, (list, tuple)) else []:
        symptom_pattern = _phrase_pattern(symptom)
        if not symptom_pattern:
            continue
        symptom_to_risk = re.compile(
            rf"\b{symptom_pattern}\b\s+(?:(?:is|are|was|were|may be|can be)\s+)?"
            rf"(?:a\s+)?(?:symptoms?|signs?|indicators?)\s+of\s+\b{risk}\b|"
            rf"\b{symptom_pattern}\b\s+(?:(?:is|are|was|were|may be|can be)\s+)"
            rf"(?:associated\s+with|linked\s+to|consistent\s+with|caused\s+by|"
            rf"indicative\s+of|suggestive\s+of)\s+\b{risk}\b|"
            rf"\b{symptom_pattern}\b\s+(?:may|can)\s+(?:indicate|suggest)\s+\b{risk}\b",
            re.I,
        )
        risk_to_symptom = re.compile(
            rf"\b{risk}\b\s+(?:(?:is|are|was|were|may be|can be)\s+)?"
            rf"(?:associated\s+with|linked\s+to|consistent\s+with|characteri[sz]ed\s+by)\s+"
            rf"\b{symptom_pattern}\b|"
            rf"\b{risk}\b\s+(?:may\s+|can\s+)?(?:cause|produce|result\s+in)\s+"
            rf"\b{symptom_pattern}\b",
            re.I,
        )
        denied_relation = re.compile(
            rf"\b{symptom_pattern}\b.{{0,30}}\b{risk}\b|\b{risk}\b.{{0,30}}\b{symptom_pattern}\b",
            re.I,
        )
        for clause in clauses:
            if not symptom_to_risk.search(clause) and not risk_to_symptom.search(clause):
                if denial.search(clause) and denied_relation.search(clause):
                    return False
                continue
            if denial.search(clause):
                return False
            positive_relation = True
    if positive_relation and any(
        relationship_reference.search(clause)
        and denial.search(clause)
        and (
            any(
                _phrase_pattern(term)
                and re.search(rf"\b{_phrase_pattern(term)}\b", clause, re.I)
                for term in [name, *(symptoms if isinstance(symptoms, (list, tuple)) else [])]
            )
            or anaphoric_relationship.search(clause)
            and not re.search(r"\bbetween\b", clause, re.I)
        )
        for clause in clauses
    ):
        return False
    return positive_relation


def _phrase_pattern(value):
    if not isinstance(value, str):
        return ""
    words = normalize_text(value).split()
    return r"\W+".join(re.escape(word) for word in words)


def public_source(passage):
    return {
        key: passage.get(key, UNAVAILABLE)
        for key in (
            "evidence_id", "title", "source", "filename", "relative_path",
            "section", "crop", "crop_applicability", "category",
            "pest_or_disease_category", "author", "organization",
            "publication_date", "revision_date", "source_url",
        )
    }


def validate_excerpt_items(value, passages, *, key="text"):
    """Return only exact excerpts whose cited IDs exist in retrieved passages."""
    if not isinstance(value, list):
        return [], True
    accepted = []
    rejected = False
    for item in value:
        if not isinstance(item, dict) or set(item) != {key, "evidence_id"}:
            rejected = True
            continue
        passage = find_passage(passages, item.get("evidence_id"))
        if passage is None or not exact_source_text(item.get(key), passage):
            rejected = True
            continue
        accepted.append({
            key: item[key].strip(),
            "evidence_status": "verbatim_source_excerpt",
            "sources": [public_source(passage)],
        })
    return accepted, rejected


def is_actionable_excerpt(text):
    """Reject descriptive source sentences mislabeled as recommendations."""
    first = normalize_text(text).split(" ", 1)[0] if normalize_text(text) else ""
    return first in {
        "inspect", "monitor", "record", "seek", "consult", "use", "avoid",
        "obtain", "check", "compare", "maintain", "consider", "recommend",
        "ensure", "observe", "distinguish", "pay", "before", "apply", "spray",
        "treat", "dose", "mix", "dilute", "test",
    }


def validate_recommendations(value, passages):
    accepted, rejected = validate_excerpt_items(value, passages)
    actionable = [item for item in accepted if is_actionable_excerpt(item["text"])]
    return actionable, rejected or len(actionable) != len(accepted)

