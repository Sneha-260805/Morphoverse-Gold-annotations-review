from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.io_utils import load_json, make_review_zip
from utils.storage_utils import load_reviews_from_persistent_storage, persistent_storage_label


st.set_page_config(
    page_title="MorphoVerse++ Review Admin",
    page_icon="MV",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
.block-container {
    padding-top: 1.15rem;
    padding-bottom: 2rem;
}
.admin-card {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1rem;
    background: #ffffff;
    color: #111827;
    margin-bottom: 1rem;
}
.poem-box {
    white-space: pre-wrap;
    line-height: 1.75;
    font-size: 1rem;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #d1d5db;
    background: #fffdf7;
    color: #111827;
    max-height: 360px;
    overflow-y: auto;
}
.small-muted {
    color: #4b5563;
    font-size: 0.88rem;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def load_local_reviews() -> List[Dict[str, Any]]:
    reviews: List[Dict[str, Any]] = []
    root = Path("reviewed_outputs")
    if not root.exists():
        return reviews

    paths = list(root.glob("*/*_reviewed.json"))
    paths.extend(root.glob("*/*/*_reviewed.json"))

    for path in sorted(paths):
        try:
            payload = load_json(path)
        except Exception:
            continue
        payload["_review_file"] = str(path)
        payload["_storage_source"] = "Local"
        reviews.append(payload)
    return reviews


def load_all_reviews() -> tuple[List[Dict[str, Any]], str]:
    local_reviews = load_local_reviews()
    remote_reviews, remote_message = load_reviews_from_persistent_storage()

    reviews_by_id: Dict[str, Dict[str, Any]] = {}
    for review in local_reviews + remote_reviews:
        key = str(review.get("review_id") or f"{review.get('poem_id')}__{review.get('reviewer_id')}")
        if key not in reviews_by_id or review.get("_storage_source") == "Supabase":
            reviews_by_id[key] = review

    return list(reviews_by_id.values()), remote_message


def review_summary_df(reviews: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for review in reviews:
        decision = review.get("reviewer_decision", {}) or {}
        annotations = review.get("final_annotations", {}) or {}
        rows.append(
            {
                "poem_id": review.get("poem_id", ""),
                "language": review.get("language", ""),
                "title": review.get("title", ""),
                "submission": review.get("reviewer_id", ""),
                "status": review.get("review_status", ""),
                "confidence": review.get("reviewer_confidence", ""),
                "reviewed_at": review.get("reviewed_at", ""),
                "comment": decision.get("reason", ""),
                "source": review.get("_storage_source", "Local"),
                "culture_rows": len(annotations.get("culture_entities", []) or []),
                "metaphor_rows": len(annotations.get("metaphor_spans", []) or []),
                "emotion_rows": len(annotations.get("stanza_emotions", []) or []),
                "motif_rows": len(annotations.get("visual_motifs", []) or []),
                "file": review.get("_review_file", ""),
            }
        )
    return pd.DataFrame(rows)


def records_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).fillna("")


def render_review(review: Dict[str, Any]) -> None:
    decision = review.get("reviewer_decision", {}) or {}
    annotations = review.get("final_annotations", {}) or {}
    changes = review.get("review_changes", {}) or {}

    st.markdown(
        f"""
        <div class="admin-card">
            <strong>{review.get("reviewer_id", "unknown")}</strong><br>
            <span class="small-muted">
                Status: {review.get("review_status", "")} |
                Confidence: {review.get("reviewer_confidence", "")} |
                Source: {review.get("_storage_source", "Local")} |
                Reviewed at: {review.get("reviewed_at", "")}
            </span>
            <p>{decision.get("reason", "") or "No final comment."}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Original poem")
        st.markdown(f'<div class="poem-box">{review.get("original_poem", "")}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown("#### English translation")
        st.markdown(f'<div class="poem-box">{review.get("english_translation", "")}</div>', unsafe_allow_html=True)

    with st.expander("Culture entities", expanded=True):
        st.dataframe(records_df(annotations.get("culture_entities", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Metaphors", expanded=True):
        st.dataframe(records_df(annotations.get("metaphor_spans", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Stanza emotions", expanded=True):
        st.dataframe(records_df(annotations.get("stanza_emotions", []) or []), use_container_width=True, hide_index=True)
    with st.expander("Visual motifs", expanded=True):
        st.dataframe(records_df(annotations.get("visual_motifs", []) or []), use_container_width=True, hide_index=True)

    with st.expander("Reviewer changes: modified, removed, or added rows", expanded=False):
        st.markdown("#### Culture entities")
        st.dataframe(records_df(changes.get("culture_entities", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Metaphors")
        st.dataframe(records_df(changes.get("metaphor_spans", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Stanza emotions")
        st.dataframe(records_df(changes.get("stanza_emotions", []) or []), use_container_width=True, hide_index=True)
        st.markdown("#### Visual motifs")
        st.dataframe(records_df(changes.get("visual_motifs", []) or []), use_container_width=True, hide_index=True)


reviews, storage_message = load_all_reviews()
summary_df = review_summary_df(reviews)

st.title("MorphoVerse++ Review Admin")
st.caption("Inspect submitted reviewer annotations poem by poem.")
st.caption(f"Storage mode: {persistent_storage_label()}")
if storage_message:
    st.info(storage_message)

if not reviews:
    st.warning("No submitted reviews found yet.")
    st.info("Reviews will appear here from Supabase when configured, and from local `reviewed_outputs/` files when present.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    languages = ["All"] + sorted(summary_df["language"].dropna().astype(str).unique().tolist())
    selected_language = st.selectbox("Language", languages)

    filtered = summary_df.copy()
    if selected_language != "All":
        filtered = filtered[filtered["language"] == selected_language]

    poem_labels = [
        f"{row.poem_id} | {row.title} | {row.language}"
        for row in filtered[["poem_id", "title", "language"]].drop_duplicates().itertuples(index=False)
    ]
    selected_poem_label = st.selectbox("Poem", poem_labels)
    selected_poem_id = selected_poem_label.split(" | ", 1)[0]

    st.divider()
    zip_path = make_review_zip()
    if zip_path and zip_path.exists():
        with zip_path.open("rb") as f:
            st.download_button(
                "Download all reviewed JSON",
                data=f,
                file_name="reviewed_outputs.zip",
                mime="application/zip",
                use_container_width=True,
            )

st.subheader("Review Progress")
total_poems = summary_df["poem_id"].nunique()
total_reviews = len(summary_df)
unique_languages = summary_df["language"].nunique()

m1, m2, m3 = st.columns(3)
m1.metric("Poems reviewed", total_poems)
m2.metric("Total submissions", total_reviews)
m3.metric("Languages", unique_languages)

st.markdown("### All Submissions")
st.dataframe(
    filtered.sort_values(["language", "poem_id", "submission"]),
    use_container_width=True,
    hide_index=True,
)

poem_reviews = [review for review in reviews if str(review.get("poem_id")) == selected_poem_id]
poem_reviews = sorted(poem_reviews, key=lambda r: str(r.get("reviewer_id", "")))

st.markdown("### Selected Poem")
if len(poem_reviews) > 1:
    compare_df = summary_df[summary_df["poem_id"] == selected_poem_id].sort_values("submission")
    st.dataframe(
        compare_df[
            [
                "submission",
                "source",
                "status",
                "confidence",
                "reviewed_at",
                "comment",
                "culture_rows",
                "metaphor_rows",
                "emotion_rows",
                "motif_rows",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

for review in poem_reviews:
    with st.expander(f"{review.get('reviewer_id', 'unknown')} - {review.get('review_status', '')}", expanded=True):
        render_review(review)
