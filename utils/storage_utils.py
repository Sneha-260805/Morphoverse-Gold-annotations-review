"""Optional persistent storage for deployed review submissions."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def get_supabase_config() -> Tuple[str, str]:
    """Return Supabase URL/key from Streamlit secrets when configured."""
    try:
        url = str(st.secrets.get("SUPABASE_URL", "") or "").rstrip("/")
        key = str(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "") or "")
    except StreamlitSecretNotFoundError:
        return "", ""
    return url, key


def persistent_storage_label() -> str:
    url, key = get_supabase_config()
    if url and key:
        return "Local JSON + Supabase"
    return "Local JSON only"


def _supabase_headers(key: str, prefer: str = "") -> Dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def save_review_to_persistent_storage(
    payload: Dict[str, Any],
    audit_entry: Dict[str, Any],
) -> Tuple[bool, str]:
    """Save review to Supabase when configured; otherwise report local-only mode."""
    url, key = get_supabase_config()
    if not url or not key:
        return False, "No Supabase secrets configured; saved locally only."

    review_row = {
        "review_id": payload["review_id"],
        "poem_id": payload["poem_id"],
        "language": payload["language"],
        "title": payload["title"],
        "review_status": payload["review_status"],
        "reviewer_id": payload["reviewer_id"],
        "reviewer_confidence": payload["reviewer_confidence"],
        "reviewed_at": payload["reviewed_at"],
        "payload": payload,
    }

    try:
        review_response = requests.post(
            f"{url}/rest/v1/reviewed_annotations?on_conflict=review_id",
            headers=_supabase_headers(key, "resolution=merge-duplicates"),
            json=[review_row],
            timeout=15,
        )
        review_response.raise_for_status()

        audit_response = requests.post(
            f"{url}/rest/v1/review_audit_log",
            headers=_supabase_headers(key),
            json=[audit_entry],
            timeout=15,
        )
        audit_response.raise_for_status()
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 404:
            return (
                False,
                "Supabase save failed because the table was not found. "
                "Check that the `reviewed_annotations` and `review_audit_log` tables exist in Supabase "
                "and that your SUPABASE_URL points to the same project.",
            )
        return False, f"Supabase save failed; local JSON was saved. Details: {exc}"

    return True, "Saved locally and to Supabase."


def load_remote_review_ids(poem_id: str) -> List[str]:
    """Return existing Supabase review IDs for a poem when configured."""
    url, key = get_supabase_config()
    if not url or not key:
        return []

    try:
        response = requests.get(
            f"{url}/rest/v1/reviewed_annotations",
            headers=_supabase_headers(key),
            params={"select": "reviewer_id", "poem_id": f"eq.{poem_id}"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException:
        return []

    rows = response.json()
    if not isinstance(rows, list):
        return []
    return [str(row.get("reviewer_id") or "") for row in rows if isinstance(row, dict)]


def load_reviews_from_persistent_storage() -> Tuple[List[Dict[str, Any]], str]:
    """Load full review payloads from Supabase when configured."""
    url, key = get_supabase_config()
    if not url or not key:
        return [], "Supabase is not configured."

    try:
        response = requests.get(
            f"{url}/rest/v1/reviewed_annotations",
            headers=_supabase_headers(key),
            params={"select": "review_id,payload", "order": "poem_id.asc,reviewer_id.asc"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return [], f"Could not load Supabase reviews: {exc}"

    rows = response.json()
    if not isinstance(rows, list):
        return [], "Supabase returned an unexpected response."

    reviews: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        payload["_review_file"] = "Supabase"
        payload["_storage_source"] = "Supabase"
        payload.setdefault("review_id", row.get("review_id", ""))
        reviews.append(payload)

    return reviews, f"Loaded {len(reviews)} review(s) from Supabase."
