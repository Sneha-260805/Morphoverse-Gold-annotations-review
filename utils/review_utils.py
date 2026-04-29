"""Helpers to normalize raw annotation JSON into editable tables."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def unwrap_value(value: Any, default: Any = "") -> Any:
    """Return field['value'] when a pipeline field uses vote metadata."""
    if isinstance(value, dict) and "value" in value:
        return value.get("value", default)
    if value is None:
        return default
    return value


def unwrap_agreement(value: Any, default: str = "") -> str:
    """Return field['agreement'] when available."""
    if isinstance(value, dict):
        return str(value.get("agreement", default) or default)
    return default


def get_poem_id(raw: Dict[str, Any]) -> str:
    return str(raw.get("poem_id") or raw.get("id") or "unknown_poem")


def get_language(raw: Dict[str, Any], fallback: str = "") -> str:
    return str(raw.get("language") or fallback or "Unknown")


def get_title(raw: Dict[str, Any]) -> str:
    return str(raw.get("poem_title") or raw.get("title") or get_poem_id(raw))


def get_original_poem(raw: Dict[str, Any]) -> str:
    return str(raw.get("original_poem") or raw.get("source_poem") or "")


def get_translation(raw: Dict[str, Any]) -> str:
    return str(raw.get("translated_poem") or raw.get("english_translation") or raw.get("translation") or "")


def get_status(raw: Dict[str, Any]) -> str:
    return str(raw.get("status") or "unknown")


def get_agreement(raw: Dict[str, Any]) -> str:
    return str(raw.get("agreement") or "")


def normalize_culture_entities(raw: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    entities = raw.get("annotation", {}).get("cultural_entities", []) or []

    for ent in entities:
        if not isinstance(ent, dict):
            continue

        rows.append(
            {
                "text": ent.get("term") or ent.get("text") or ent.get("source_text") or "",
                "english_gloss": unwrap_value(ent.get("english_gloss", "")),
                "romanization": unwrap_value(ent.get("romanization", "")),
                "category": unwrap_value(ent.get("category", "OTHER"), "OTHER"),
                "stanza_index": ent.get("stanza_index", ""),
                "preserved": unwrap_value(ent.get("preserved", "")),
                "translation_note": unwrap_value(ent.get("translation_note", "")),
                "confidence": ent.get("presence_agreement")
                or unwrap_agreement(ent.get("category"))
                or unwrap_agreement(ent.get("preserved")),
                "review_action": "keep",
                "reviewer_comment": "",
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "text",
            "english_gloss",
            "romanization",
            "category",
            "stanza_index",
            "preserved",
            "translation_note",
            "confidence",
            "review_action",
            "reviewer_comment",
        ],
    )


def normalize_metaphors(raw: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for stanza in raw.get("annotation", {}).get("stanzas", []) or []:
        if not isinstance(stanza, dict):
            continue
        stanza_index = stanza.get("stanza_index", "")
        for met in stanza.get("metaphor_spans", []) or []:
            if not isinstance(met, dict):
                continue
            rows.append(
                {
                    "source_text": met.get("source_term")
                    or met.get("source_text")
                    or met.get("text")
                    or "",
                    "literal_meaning": met.get("literal_meaning", ""),
                    "abstract_meaning": met.get("abstract_meaning", ""),
                    "visual_hint": met.get("visual_hint", ""),
                    "stanza_index": stanza_index,
                    "confidence": met.get("agreement", ""),
                    "review_action": "keep",
                    "reviewer_comment": "",
                }
            )

    return pd.DataFrame(
        rows,
        columns=[
            "source_text",
            "literal_meaning",
            "abstract_meaning",
            "visual_hint",
            "stanza_index",
            "confidence",
            "review_action",
            "reviewer_comment",
        ],
    )


def normalize_emotions(raw: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for stanza in raw.get("annotation", {}).get("stanzas", []) or []:
        if not isinstance(stanza, dict):
            continue
        rows.append(
            {
                "stanza_index": stanza.get("stanza_index", ""),
                "emotion": unwrap_value(stanza.get("emotion", ""), ""),
                "tone": unwrap_value(stanza.get("tone", ""), ""),
                "translation_quality": unwrap_value(stanza.get("translation_quality", ""), ""),
                "loss_note": unwrap_value(stanza.get("loss_note", ""), ""),
                "confidence": unwrap_agreement(stanza.get("emotion", "")),
                "review_action": "keep",
                "reviewer_comment": "",
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "stanza_index",
            "emotion",
            "tone",
            "translation_quality",
            "loss_note",
            "confidence",
            "review_action",
            "reviewer_comment",
        ],
    )


def normalize_visual_motifs(raw: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for stanza in raw.get("annotation", {}).get("stanzas", []) or []:
        if not isinstance(stanza, dict):
            continue
        stanza_index = stanza.get("stanza_index", "")
        for motif in stanza.get("visual_motifs", []) or []:
            if isinstance(motif, dict):
                rows.append(
                    {
                        "motif": motif.get("motif") or motif.get("text") or "",
                        "stanza_index": stanza_index,
                        "importance": motif.get("importance", ""),
                        "keep_for_image_generation": True,
                        "confidence": motif.get("agreement", ""),
                        "review_action": "keep",
                        "reviewer_comment": "",
                    }
                )
            elif isinstance(motif, str):
                rows.append(
                    {
                        "motif": motif,
                        "stanza_index": stanza_index,
                        "importance": "",
                        "keep_for_image_generation": True,
                        "confidence": "",
                        "review_action": "keep",
                        "reviewer_comment": "",
                    }
                )

    return pd.DataFrame(
        rows,
        columns=[
            "motif",
            "stanza_index",
            "importance",
            "keep_for_image_generation",
            "confidence",
            "review_action",
            "reviewer_comment",
        ],
    )


def get_stanza_rows(raw: Dict[str, Any]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    stanzas = raw.get("preprocessing", {}).get("stanzas") or raw.get("annotation", {}).get("stanzas") or []
    for stanza in stanzas:
        if not isinstance(stanza, dict):
            continue

        source_lines = stanza.get("source_lines", []) or []
        translated_lines = stanza.get("translated_lines", []) or []
        rows.append(
            {
                "stanza_index": stanza.get("stanza_index", ""),
                "source_text": "\n".join(source_lines) if isinstance(source_lines, list) else str(source_lines),
                "translated_text": "\n".join(translated_lines)
                if isinstance(translated_lines, list)
                else str(translated_lines),
                "line_count": stanza.get("line_count", ""),
            }
        )

    return pd.DataFrame(rows, columns=["stanza_index", "source_text", "translated_text", "line_count"])


def cleaned_records(df: pd.DataFrame, key_col: str) -> List[Dict[str, Any]]:
    """Convert edited table to records, dropping rows without the main value."""
    if df is None or df.empty:
        return []
    result: List[Dict[str, Any]] = []
    for rec in df.fillna("").to_dict(orient="records"):
        if str(rec.get(key_col, "")).strip():
            result.append(rec)
    return result
