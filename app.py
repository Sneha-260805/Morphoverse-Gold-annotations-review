from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.io_utils import (
    append_audit_log,
    ensure_app_dirs,
    load_raw_poems,
    load_reviews_for_poem,
    load_reviewed_index,
    make_review_zip,
    next_review_number,
    now_iso,
    review_id,
    reviewer_id_from_number,
    review_number_from_reviewer_id,
    reviewed_output_path,
    save_json,
    resolve_data_dir,
)
from utils.review_utils import (
    cleaned_records,
    get_agreement,
    get_original_poem,
    get_poem_id,
    get_stanza_rows,
    get_status,
    get_title,
    get_translation,
    normalize_culture_entities,
    normalize_emotions,
    normalize_metaphors,
    normalize_visual_motifs,
)
from utils.schema_utils import (
    ALLOWED_CULTURE_CATEGORIES,
    ALLOWED_EMOTIONS,
    REVIEW_ACTIONS,
    REVIEW_CONFIDENCE,
    REVIEW_DECISIONS,
    REVIEW_STATUS_FILTERS,
)
from utils.storage_utils import load_remote_review_ids, persistent_storage_label, save_review_to_persistent_storage


st.set_page_config(
    page_title="MorphoVerse++ Human Review",
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
.mv-card {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1rem;
    background: #ffffff;
    color: #111827;
    margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(36, 39, 47, 0.05);
}
.mv-hero {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 1.15rem 1.25rem;
    background: #ffffff;
    color: #111827;
    margin-bottom: 1rem;
}
.mv-hero h1 {
    margin: 0 0 0.35rem 0;
    font-size: 2rem;
    color: #111827;
}
.mv-section-title {
    margin-bottom: 0.45rem;
    color: #111827;
}
.mv-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 0.22rem 0.7rem;
    font-size: 0.78rem;
    font-weight: 700;
    margin: 0 0.35rem 0.35rem 0;
    border: 1px solid rgba(49, 51, 63, 0.15);
}
.badge-green { background: #eaf7ef; color: #176b3a; }
.badge-blue { background: #edf4ff; color: #174a8b; }
.badge-yellow { background: #fff7db; color: #7a5200; }
.badge-red { background: #ffecec; color: #9d1c1c; }
.badge-gray { background: #f2f2f2; color: #444; }
.poem-box {
    white-space: pre-wrap;
    line-height: 1.85;
    font-size: 1.08rem;
    padding: 1.1rem 1.2rem;
    border-radius: 8px;
    border: 1px solid rgba(31, 41, 55, 0.22);
    background: #fffdf7;
    color: #111827;
    min-height: 220px;
    max-height: 480px;
    overflow-y: auto;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
}
.poem-label {
    color: inherit;
    font-size: 0.9rem;
    font-weight: 700;
    margin: 0.35rem 0 0.4rem 0;
}
.quick-review-band {
    border-top: 1px solid rgba(36, 39, 47, 0.12);
    padding-top: 0.85rem;
    margin-top: 0.35rem;
}
.small-muted {
    color: #4b5563;
    font-size: 0.88rem;
}
.metric-note {
    font-size: 0.78rem;
    color: #4b5563;
}
.attention-list {
    margin: 0.2rem 0 0 1rem;
    padding: 0;
    color: #111827;
}
.attention-list li {
    margin-bottom: 0.25rem;
}
.review-steps {
    margin: 0.35rem 0 0 1.2rem;
    padding: 0;
    color: #111827;
}
.review-steps li {
    margin-bottom: 0.45rem;
}
.review-steps strong {
    color: #0f5132;
}
.field-guide {
    margin: 0.35rem 0 0 0;
    color: #111827;
}
.field-guide p {
    margin: 0 0 0.45rem 0;
}
.field-guide code,
.review-steps code {
    color: #7c2d12;
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 4px;
    padding: 0.05rem 0.25rem;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def badge(text: str, kind: str = "gray") -> str:
    return f'<span class="mv-badge badge-{kind}">{text}</span>'


def status_badge_kind(status: str) -> str:
    status = (status or "").lower()
    if status in {"approved", "completed"}:
        return "green"
    if status in {"approved_with_corrections", "in_progress"}:
        return "blue"
    if status in {"pending_review", "needs_major_revision", "pending"}:
        return "yellow"
    if status in {"rejected", "failed", "load_error"}:
        return "red"
    return "gray"


def agreement_badge_kind(agreement: str) -> str:
    agreement = (agreement or "").lower()
    if agreement == "high":
        return "green"
    if agreement == "medium":
        return "yellow"
    if agreement == "low":
        return "red"
    return "gray"


def get_current_review_status(raw: Dict[str, Any], reviewed_index: Dict[str, Dict[str, Any]]) -> str:
    poem_id = get_poem_id(raw)
    if poem_id in reviewed_index:
        return str(reviewed_index[poem_id].get("review_status") or "reviewed")
    raw_status = get_status(raw).lower()
    if raw_status in {"failed", "pending"}:
        return raw_status
    return "pending_review"


def filter_poems(poems: List[Dict[str, Any]], language: str, status_filter: str, reviewed_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered = [p for p in poems if p.get("language") == language or p.get("_language_folder") == language]
    if status_filter != "all":
        filtered = [p for p in filtered if get_current_review_status(p, reviewed_index) == status_filter]
    return filtered


def load_initial_tables(raw: Dict[str, Any], reviewed: Dict[str, Any] | None):
    """Load edited tables from reviewed JSON when available; otherwise raw normalized tables."""
    if reviewed and reviewed.get("final_annotations"):
        final = reviewed["final_annotations"]
        culture_df = pd.DataFrame(final.get("culture_entities", []))
        metaphor_df = pd.DataFrame(final.get("metaphor_spans", []))
        emotion_df = pd.DataFrame(final.get("stanza_emotions", []))
        motif_df = pd.DataFrame(final.get("visual_motifs", []))

        # Ensure columns remain stable even if old reviewed files are incomplete.
        if culture_df.empty:
            culture_df = normalize_culture_entities(raw)
        if metaphor_df.empty:
            metaphor_df = normalize_metaphors(raw)
        if emotion_df.empty:
            emotion_df = normalize_emotions(raw)
        if motif_df.empty:
            motif_df = normalize_visual_motifs(raw)
        return culture_df, metaphor_df, emotion_df, motif_df

    return (
        normalize_culture_entities(raw),
        normalize_metaphors(raw),
        normalize_emotions(raw),
        normalize_visual_motifs(raw),
    )


def safe_text(value: Any) -> str:
    return escape(str(value or ""))


def row_count(df: pd.DataFrame) -> int:
    return 0 if df is None or df.empty else len(df)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return isinstance(value, str) and not value.strip()


def review_records(df: pd.DataFrame, key_col: str) -> List[Dict[str, Any]]:
    """Return non-empty rows for validation and saving."""
    if df is None or df.empty:
        return []

    records: List[Dict[str, Any]] = []
    for rec in df.fillna("").to_dict(orient="records"):
        if str(rec.get(key_col, "")).strip():
            records.append(rec)
    return records


def validate_review_table(
    df: pd.DataFrame,
    section: str,
    key_col: str,
    required_when_kept: List[str],
) -> List[str]:
    errors: List[str] = []
    for idx, rec in enumerate(review_records(df, key_col), start=1):
        action = str(rec.get("review_action", "")).strip()
        row_name = str(rec.get(key_col, "")).strip()

        if action not in REVIEW_ACTIONS:
            errors.append(f"{section} row {idx} ({row_name}): choose a review_action from the dropdown.")
            continue

        if action in {"modify", "remove", "add"} and is_blank(rec.get("reviewer_comment")):
            errors.append(f"{section} row {idx} ({row_name}): add a reviewer_comment for {action}.")

        if action != "remove":
            for col in required_when_kept:
                if is_blank(rec.get(col)):
                    errors.append(f"{section} row {idx} ({row_name}): fill `{col}` or mark the row as remove.")

    return errors


def has_review_edits(*tables: pd.DataFrame) -> bool:
    for df in tables:
        for rec in review_records(df, "review_action"):
            if str(rec.get("review_action", "")).strip() in {"modify", "remove", "add"}:
                return True
    return False


def table_preview(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    available = [col for col in columns if col in df.columns]
    return df[available].copy()


def get_low_agreement_notes(raw: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if str(get_agreement(raw)).lower() == "low":
        notes.append("Overall model agreement is low.")

    annotation = raw.get("annotation", {})
    stats = annotation.get("agreement_stats", {}) if isinstance(annotation, dict) else {}
    low_stanzas = int(stats.get("low_stanza_count") or 0)
    low_entities = int(stats.get("low_entity_count") or 0)
    review_items = raw.get("review_items", []) or []

    if low_stanzas:
        notes.append(f"{low_stanzas} stanza-level item(s) have low agreement.")
    if low_entities:
        notes.append(f"{low_entities} cultural entity item(s) have low agreement.")
    if review_items:
        notes.append(f"{len(review_items)} model disagreement item(s) are queued for checking.")
    if not notes:
        notes.append("No urgent disagreement flags were found for this poem.")
    return notes


def poem_option_label(raw: Dict[str, Any], reviewed_index: Dict[str, Dict[str, Any]]) -> str:
    poem_id = get_poem_id(raw)
    title = get_title(raw)
    status = get_current_review_status(raw, reviewed_index).replace("_", " ")
    agreement = get_agreement(raw) or "n/a"
    return f"{poem_id} | {title} | {status} | agreement: {agreement}"


def review_action_column() -> st.column_config.SelectboxColumn:
    return st.column_config.SelectboxColumn(
        "review_action (dropdown)",
        help="Click this cell and choose: keep, modify, remove, or add.",
        options=REVIEW_ACTIONS,
        required=True,
    )


def metrics_block(poems: List[Dict[str, Any]], reviewed_index: Dict[str, Dict[str, Any]]):
    total = len(poems)
    reviewed = len([p for p in poems if get_poem_id(p) in reviewed_index])
    pending = total - reviewed

    reviews = [
        review
        for poem_review_summary in reviewed_index.values()
        for review in poem_review_summary.get("reviews", [])
    ]
    decisions = [str(v.get("review_status") or "") for v in reviews]
    approved = decisions.count("approved")
    corrected = decisions.count("approved_with_corrections")
    major = decisions.count("needs_major_revision")
    rejected = decisions.count("rejected")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total loaded", total)
    c2.metric("Poems with review", reviewed)
    c3.metric("Pending", pending)
    if total:
        st.progress(reviewed / total, text=f"{reviewed} of {total} poems reviewed")

    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Approved reviews", approved)
    c5.metric("Approved + corrections", corrected)
    c6.metric("Major revision", major)
    c7.metric("Rejected", rejected)


def df_editor_culture(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "category": st.column_config.SelectboxColumn("category (dropdown)", options=ALLOWED_CULTURE_CATEGORIES),
            "review_action": review_action_column(),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
        },
    )


def df_editor_metaphor(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "review_action": review_action_column(),
            "abstract_meaning": st.column_config.TextColumn("abstract_meaning", width="large"),
            "visual_hint": st.column_config.TextColumn("visual_hint", width="large"),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
        },
    )


def df_editor_emotion(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "emotion": st.column_config.SelectboxColumn("emotion (dropdown)", options=ALLOWED_EMOTIONS),
            "review_action": review_action_column(),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
        },
    )


def df_editor_motif(df: pd.DataFrame, key: str) -> pd.DataFrame:
    return st.data_editor(
        df,
        key=key,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "keep_for_image_generation": st.column_config.CheckboxColumn("keep_for_image_generation"),
            "review_action": review_action_column(),
            "reviewer_comment": st.column_config.TextColumn("reviewer_comment", width="large"),
        },
    )


ensure_app_dirs()
data_dir = resolve_data_dir()
poems = load_raw_poems(data_dir)
reviewed_index = load_reviewed_index()

st.markdown(
    """
    <div class="mv-hero">
        <h1>MorphoVerse++ Human Review</h1>
        <div class="small-muted">
            Inspect poem text, compare translations, correct annotation tables, and save reviewer-approved gold JSON files.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not data_dir.exists():
    st.error(
        f"Raw data folder not found: `{data_dir}`. Put `outputs_new_4` under `review_app/data/outputs_new_4` "
        "or run the app from a directory containing `outputs_new_4`."
    )
    st.stop()

if not poems:
    st.warning("No poem JSON files found after exclusions. Bodo and MV++_1443 are intentionally skipped.")
    st.stop()

with st.sidebar:
    st.header("Reviewer")
    st.caption("No reviewer ID is needed. The app assigns the next review number for the selected poem.")

    st.divider()

    languages = sorted({str(p.get("language") or p.get("_language_folder") or "Unknown") for p in poems})
    language = st.selectbox("Language", languages)

    status_filter = st.selectbox("Review status filter", REVIEW_STATUS_FILTERS, index=0)

    language_poems = filter_poems(poems, language, status_filter, reviewed_index)
    search_query = st.text_input("Search poem", placeholder="ID or title").strip().lower()
    if search_query:
        language_poems = [
            p
            for p in language_poems
            if search_query in get_poem_id(p).lower() or search_query in get_title(p).lower()
        ]
    if not language_poems:
        st.warning("No poems match this language/status filter.")
        st.stop()

    poem_options = {
        poem_option_label(p, reviewed_index): get_poem_id(p) for p in language_poems
    }
    selected_label = st.selectbox("Poem", list(poem_options.keys()))
    selected_poem_id = poem_options[selected_label]

    st.divider()
    st.subheader("Progress")
    metrics_block(poems, reviewed_index)

    st.divider()
    st.caption(f"Submission storage: {persistent_storage_label()}")
    zip_path = make_review_zip()
    if zip_path and zip_path.exists():
        with zip_path.open("rb") as f:
            st.download_button(
                "Download reviewed JSON ZIP",
                data=f,
                file_name="reviewed_outputs.zip",
                mime="application/zip",
                use_container_width=True,
            )

raw = next(p for p in language_poems if get_poem_id(p) == selected_poem_id)
poem_id = get_poem_id(raw)
poem_language = str(raw.get("language") or raw.get("_language_folder") or language)
title = get_title(raw)
reviewed = None
all_poem_reviews = load_reviews_for_poem(poem_language, poem_id)
remote_reviewer_ids = load_remote_review_ids(poem_id)
remote_reviews = [{"reviewer_id": reviewer_id} for reviewer_id in remote_reviewer_ids]
assigned_review_number = next_review_number(all_poem_reviews + remote_reviews)
assigned_reviewer_id = reviewer_id_from_number(assigned_review_number)
current_review_status = get_current_review_status(raw, reviewed_index)

st.subheader(title)
st.markdown(
    badge(poem_id, "blue")
    + badge(poem_language, "gray")
    + badge(f"Review: {current_review_status}", status_badge_kind(current_review_status))
    + badge(f"Agreement: {get_agreement(raw) or 'n/a'}", agreement_badge_kind(get_agreement(raw))),
    unsafe_allow_html=True,
)
if all_poem_reviews:
    reviewers = ", ".join(sorted({str(r.get("reviewer_id") or "unknown") for r in all_poem_reviews}))
    st.info(f"Existing local reviews for this poem: {len(all_poem_reviews)} submission(s): {reviewers}.")
if remote_reviewer_ids:
    st.info(f"Existing Supabase reviews for this poem: {len(remote_reviewer_ids)} submission(s).")
st.success(f"This submission will be saved as `{assigned_reviewer_id}` for this poem.")

if poem_id == "MV++_1443" or poem_language == "Bodo":
    st.error("This poem is excluded from the review workflow.")
    st.stop()

culture_df, metaphor_df, emotion_df, motif_df = load_initial_tables(raw, reviewed)
stanza_df = get_stanza_rows(raw)

summary_cols = st.columns(5)
summary_cols[0].metric("Stanzas", row_count(stanza_df))
summary_cols[1].metric("Culture", row_count(culture_df))
summary_cols[2].metric("Metaphors", row_count(metaphor_df))
summary_cols[3].metric("Emotions", row_count(emotion_df))
summary_cols[4].metric("Visual motifs", row_count(motif_df))

attention_items = "".join(f"<li>{safe_text(note)}</li>" for note in get_low_agreement_notes(raw))
st.markdown(
    f"""
    <div class="mv-card">
        <div class="mv-section-title"><strong>Review focus</strong></div>
        <ul class="attention-list">{attention_items}</ul>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="mv-card">
        <div class="mv-section-title"><strong>Reviewer steps</strong></div>
        <ol class="review-steps">
            <li><strong>Your job:</strong> correct the annotation tables below. The current values were generated automatically and may be wrong or incomplete.</li>
            <li><strong>Read</strong> the original poem and English translation first, then review each open annotation box.</li>
            <li><strong>Edit only what is needed:</strong> click a wrong cell to fix it, add a row if an important annotation is missing, or mark a bad row as remove.</li>
            <li><strong>Use <code>review_action</code>:</strong> keep = correct as-is, modify = you corrected it, remove = wrong/not useful, add = new row added by you.</li>
            <li><strong>Submit</strong> the final decision at the bottom after checking the annotation boxes.</li>
        </ol>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="mv-card">
        <div class="mv-section-title"><strong>Blank or missing values</strong></div>
        <div class="field-guide">
            <p>Blank cells are expected in some columns. They usually mean one of three things: the automatic annotation did not provide that detail, the field is optional, or the field does not apply to that row.</p>
            <p>You do not need to fill every blank. Fill a blank only when the missing value is important for the final corrected annotation.</p>
            <p>Examples: <code>literal_meaning</code>, <code>visual_hint</code>, <code>importance</code>, and <code>loss_note</code> can stay blank when there is nothing useful to add. Important fields such as the term/metaphor/motif text, emotion, category, preserved value, and review action should not be blank.</p>
            <p>Always fill <code>reviewer_comment</code> when you mark a row as <code>modify</code>, <code>remove</code>, or <code>add</code>.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("### Quick Review")
st.markdown('<div class="quick-review-band"></div>', unsafe_allow_html=True)

poem_left, poem_right = st.columns(2)
with poem_left:
    st.markdown('<div class="poem-label">Original poem</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="poem-box">{safe_text(get_original_poem(raw))}</div>', unsafe_allow_html=True)
with poem_right:
    st.markdown('<div class="poem-label">English translation</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="poem-box">{safe_text(get_translation(raw))}</div>', unsafe_allow_html=True)

st.markdown("### Review annotations")
st.info(
    "Edit directly in the tables below. In the `review_action (dropdown)` column, click the cell and choose: "
    "`keep` for correct rows, `modify` for corrected rows, `remove` for wrong rows, and `add` for new rows."
)

with st.expander(f"Culture entities ({row_count(culture_df)})", expanded=row_count(culture_df) > 0):
    st.info(
        "What to do: keep real cultural terms, correct wrong terms/categories, add missed important terms, "
        "and mark irrelevant rows as `remove`. `preserved` means whether the cultural term or its meaning is "
        "still clear in the English translation. Use true/yes if preserved; false/no if the meaning is lost, "
        "softened, mistranslated, or omitted. Blank gloss/romanization/translation notes can stay blank unless "
        "you know the missing value and it helps the annotation."
    )
    edited_culture_df = df_editor_culture(culture_df, key=f"culture_{poem_id}")

with st.expander(f"Metaphors ({row_count(metaphor_df)})", expanded=row_count(metaphor_df) > 0):
    st.info(
        "What to do: keep only phrases that are truly figurative. `source_text` should be the metaphor phrase "
        "from the poem. `literal_meaning` is optional and may be blank. `abstract_meaning` should explain what "
        "the metaphor suggests emotionally or conceptually. `visual_hint` is optional; fill it only if a clear "
        "visual image would help. Remove literal phrases, duplicates, or invented metaphors."
    )
    edited_metaphor_df = df_editor_metaphor(metaphor_df, key=f"metaphor_{poem_id}")

with st.expander(f"Stanza emotions ({row_count(emotion_df)})", expanded=row_count(emotion_df) > 0):
    st.info(
        "What to do: check each stanza's main emotion and tone against the poem. Change `emotion` if the label "
        "is wrong. `translation_quality` should describe whether the English translation is faithful enough. "
        "`loss_note` can be blank when nothing important is lost; fill it if cultural meaning, imagery, emotion, "
        "wordplay, or tone is missing in translation."
    )
    edited_emotion_df = df_editor_emotion(emotion_df, key=f"emotion_{poem_id}")

with st.expander(f"Visual motifs ({row_count(motif_df)})", expanded=row_count(motif_df) > 0):
    st.info(
        "What to do: keep motifs that are concrete, visual, and actually present in the poem. "
        "`keep_for_image_generation` should be checked only when the motif would help create a faithful image. "
        "`importance` may be blank; fill it only if you want to mark a motif as central, supporting, or minor. "
        "Remove vague, repeated, generic, or invented motifs."
    )
    edited_motif_df = df_editor_motif(motif_df, key=f"motif_{poem_id}")

with st.container():
    st.markdown("### Final Human Decision")
    st.info(
        "Choose the final status after editing. Use `approved` only if the annotations were already good. "
        "Use `approved_with_corrections` if you fixed anything. Use `needs_major_revision` or `rejected` "
        "only when the annotation is too poor to trust; include a reason in the comment box."
    )

    previous_decision = reviewed.get("reviewer_decision", {}) if reviewed else {}
    previous_status = reviewed.get("review_status", "approved_with_corrections") if reviewed else "approved_with_corrections"
    previous_confidence = reviewed.get("reviewer_confidence", "medium") if reviewed else "medium"
    if reviewed:
        st.info("You already have a saved review for this poem. Submitting again will update only your own review file.")

    with st.form(key=f"decision_form_{poem_id}", clear_on_submit=False):
        form_reviewer_id = st.text_input("Submission number", value=assigned_reviewer_id, disabled=True)
        decision = st.selectbox(
            "Overall decision",
            REVIEW_DECISIONS,
            index=REVIEW_DECISIONS.index(previous_status) if previous_status in REVIEW_DECISIONS else 1,
        )
        confidence = st.selectbox(
            "Reviewer confidence",
            REVIEW_CONFIDENCE,
            index=REVIEW_CONFIDENCE.index(previous_confidence) if previous_confidence in REVIEW_CONFIDENCE else 1,
        )
        reason = st.text_area(
            "Final reviewer reason/comment",
            value=str(previous_decision.get("reason", "")),
            height=130,
            placeholder="Mention what you corrected, approved, rejected, or why this needs revision.",
        )
        confirm = st.checkbox("I confirm that I have reviewed this poem and its annotations.")
        submitted = st.form_submit_button("Submit reviewed annotation", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if decision in {"needs_major_revision", "rejected"} and not reason.strip():
            errors.append("Reason/comment is mandatory for needs_major_revision or rejected.")
        if not confirm:
            errors.append("Please confirm that you reviewed this poem.")
        errors.extend(validate_review_table(edited_culture_df, "Culture entities", "text", ["category", "preserved"]))
        errors.extend(validate_review_table(edited_metaphor_df, "Metaphors", "source_text", ["abstract_meaning"]))
        errors.extend(validate_review_table(edited_emotion_df, "Stanza emotions", "stanza_index", ["emotion"]))
        errors.extend(validate_review_table(edited_motif_df, "Visual motifs", "motif", ["keep_for_image_generation"]))
        if decision == "approved" and has_review_edits(edited_culture_df, edited_metaphor_df, edited_emotion_df, edited_motif_df):
            errors.append("Use approved_with_corrections because at least one row is marked modify, remove, or add.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            latest_local_reviews = load_reviews_for_poem(poem_language, poem_id)
            latest_remote_ids = load_remote_review_ids(poem_id)
            latest_remote_reviews = [{"reviewer_id": reviewer_id} for reviewer_id in latest_remote_ids]
            submitted_reviewer_id = reviewer_id_from_number(next_review_number(latest_local_reviews + latest_remote_reviews))
            while reviewed_output_path(poem_language, poem_id, submitted_reviewer_id).exists():
                submitted_reviewer_id = reviewer_id_from_number(review_number_from_reviewer_id(submitted_reviewer_id) + 1)
            output_path = reviewed_output_path(poem_language, poem_id, submitted_reviewer_id)
            reviewed_at = now_iso()

            payload = {
                "review_id": review_id(poem_id, submitted_reviewer_id),
                "poem_id": poem_id,
                "language": poem_language,
                "title": title,
                "review_status": decision,
                "reviewer_id": submitted_reviewer_id,
                "reviewer_confidence": confidence,
                "reviewed_at": reviewed_at,
                "original_poem": get_original_poem(raw),
                "english_translation": get_translation(raw),
                "source_annotation_file": raw.get("_source_file", ""),
                "final_annotations": {
                    "culture_entities": cleaned_records(edited_culture_df, "text"),
                    "metaphor_spans": cleaned_records(edited_metaphor_df, "source_text"),
                    "stanza_emotions": cleaned_records(edited_emotion_df, "stanza_index"),
                    "visual_motifs": cleaned_records(edited_motif_df, "motif"),
                },
                "reviewer_decision": {
                    "decision": decision,
                    "reason": reason.strip(),
                },
                "raw_llm_annotation_snapshot": raw,
            }

            save_json(output_path, payload)

            audit_entry = {
                "event": "review_submitted",
                "review_id": payload["review_id"],
                "poem_id": poem_id,
                "language": poem_language,
                "reviewer_id": submitted_reviewer_id,
                "decision": decision,
                "reviewer_confidence": confidence,
                "reviewed_at": reviewed_at,
                "output_file": str(output_path),
            }
            append_audit_log(audit_entry)

            persistent_ok, persistent_message = save_review_to_persistent_storage(payload, audit_entry)

            st.success(f"Review saved successfully: `{output_path}`")
            if persistent_ok:
                st.success(persistent_message)
            else:
                st.warning(persistent_message)
            st.info("Refresh the page to update sidebar metrics immediately.")
