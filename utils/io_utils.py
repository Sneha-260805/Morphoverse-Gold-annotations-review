"""File I/O helpers for the MorphoVerse++ human review app."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .review_utils import get_language, get_poem_id, get_status
from .schema_utils import EXCLUDED_LANGUAGES, EXCLUDED_POEM_IDS


def resolve_data_dir() -> Path:
    """Find the raw outputs folder in common locations."""
    candidates = [
        Path("data") / "outputs_new_4",
        Path("data") / "outputs_new_4" / "outputs_new_4",
        Path("outputs_new_4"),
        Path("outputs_new_4") / "outputs_new_4",
        Path("../outputs_new_4"),
        Path("../outputs_new_4") / "outputs_new_4",
        Path("../../outputs_new_4"),
        Path("../../outputs_new_4") / "outputs_new_4",
        Path("/mnt/data/outputs_new_4"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and any(candidate.glob("*/*.json")):
            return candidate
    # Default path shown in the UI if nothing exists yet.
    return Path("data") / "outputs_new_4"


def ensure_app_dirs() -> None:
    Path("reviewed_outputs").mkdir(exist_ok=True)
    Path("audit_logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_raw_poems(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all raw poem JSON files, excluding Bodo and failed Telugu poem."""
    data_dir = data_dir or resolve_data_dir()
    poems: List[Dict[str, Any]] = []

    if not data_dir.exists():
        return poems

    for json_path in sorted(data_dir.glob("*/*.json")):
        language_folder = json_path.parent.name
        if language_folder in EXCLUDED_LANGUAGES:
            continue

        try:
            raw = load_json(json_path)
        except Exception as exc:
            poems.append(
                {
                    "poem_id": json_path.stem,
                    "language": language_folder,
                    "poem_title": json_path.stem,
                    "status": "load_error",
                    "load_error": str(exc),
                    "_source_file": str(json_path),
                }
            )
            continue

        poem_id = get_poem_id(raw)
        language = get_language(raw, fallback=language_folder)

        if language in EXCLUDED_LANGUAGES or poem_id in EXCLUDED_POEM_IDS:
            continue

        # Extra safety: skip raw failed files if accidentally present.
        if poem_id == "MV++_1443" or (language == "Telugu" and get_status(raw).lower() == "failed"):
            continue

        raw["_source_file"] = str(json_path)
        raw["_language_folder"] = language_folder
        poems.append(raw)

    return poems


def load_review_queue(data_dir: Optional[Path] = None) -> pd.DataFrame:
    data_dir = data_dir or resolve_data_dir()
    path = data_dir / "human_review_queue.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if "poem_id" in df.columns:
        df = df[~df["poem_id"].isin(EXCLUDED_POEM_IDS)]
    if "language" in df.columns:
        df = df[~df["language"].isin(EXCLUDED_LANGUAGES)]
    return df


def load_annotation_summary(data_dir: Optional[Path] = None) -> pd.DataFrame:
    data_dir = data_dir or resolve_data_dir()
    path = data_dir / "annotation_summary.csv"
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if "poem_id" in df.columns:
        df = df[~df["poem_id"].isin(EXCLUDED_POEM_IDS)]
    if "language" in df.columns:
        df = df[~df["language"].isin(EXCLUDED_LANGUAGES)]
    return df


def safe_reviewer_id(reviewer_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(reviewer_id or "").strip())
    return cleaned.strip("._-") or "unknown_reviewer"


def review_id(poem_id: str, reviewer_id: str) -> str:
    return f"{poem_id}__{safe_reviewer_id(reviewer_id)}"


def reviewer_id_from_number(review_number: int) -> str:
    return f"review_{review_number:02d}"


def review_number_from_reviewer_id(reviewer_id: str) -> int:
    match = re.search(r"review_(\d+)$", str(reviewer_id or ""))
    return int(match.group(1)) if match else 0


def next_review_number(reviews: List[Dict[str, Any]]) -> int:
    max_number = 0
    for review in reviews:
        max_number = max(max_number, review_number_from_reviewer_id(str(review.get("reviewer_id") or "")))
    return max_number + 1


def reviewed_output_path(language: str, poem_id: str, reviewer_id: str) -> Path:
    return Path("reviewed_outputs") / language / poem_id / f"{safe_reviewer_id(reviewer_id)}_reviewed.json"


def legacy_reviewed_output_path(language: str, poem_id: str) -> Path:
    return Path("reviewed_outputs") / language / f"{poem_id}_reviewed.json"


def load_reviewed_if_exists(language: str, poem_id: str, reviewer_id: str = "") -> Optional[Dict[str, Any]]:
    if not reviewer_id.strip():
        return None

    path = reviewed_output_path(language, poem_id, reviewer_id)
    if path.exists():
        return load_json(path)

    # Backward compatibility for files saved before per-reviewer outputs existed.
    legacy_path = legacy_reviewed_output_path(language, poem_id)
    if legacy_path.exists():
        payload = load_json(legacy_path)
        if str(payload.get("reviewer_id") or "") == reviewer_id:
            return payload
    return None


def load_reviews_for_poem(language: str, poem_id: str) -> List[Dict[str, Any]]:
    paths = list((Path("reviewed_outputs") / language / poem_id).glob("*_reviewed.json"))
    legacy_path = legacy_reviewed_output_path(language, poem_id)
    if legacy_path.exists():
        paths.append(legacy_path)

    reviews: List[Dict[str, Any]] = []
    for path in sorted(paths):
        try:
            payload = load_json(path)
            payload["_review_file"] = str(path)
            reviews.append(payload)
        except Exception:
            continue
    return reviews


def append_audit_log(entry: Dict[str, Any]) -> None:
    Path("audit_logs").mkdir(exist_ok=True)
    path = Path("audit_logs") / "review_audit_log.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_reviewed_index() -> Dict[str, Dict[str, Any]]:
    """Return review summary keyed by poem_id."""
    index: Dict[str, Dict[str, Any]] = {}
    paths = list(Path("reviewed_outputs").glob("*/*_reviewed.json"))
    paths.extend(Path("reviewed_outputs").glob("*/*/*_reviewed.json"))

    for path in sorted(paths):
        try:
            payload = load_json(path)
            poem_id = str(payload.get("poem_id") or path.stem.replace("_reviewed", ""))
            reviewer_id = str(payload.get("reviewer_id") or "")
            entry = index.setdefault(
                poem_id,
                {
                    "poem_id": poem_id,
                    "review_count": 0,
                    "reviewers": [],
                    "reviews": [],
                    "review_status": "reviewed",
                },
            )
            entry["review_count"] += 1
            if reviewer_id and reviewer_id not in entry["reviewers"]:
                entry["reviewers"].append(reviewer_id)
            entry["reviews"].append(payload)
            entry["review_status"] = "reviewed"
        except Exception:
            continue
    return index


def make_review_zip() -> Optional[Path]:
    root = Path("reviewed_outputs")
    if not root.exists():
        return None

    zip_path = Path("reviewed_outputs.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in root.glob("**/*.json"):
            zf.write(path, path.as_posix())
    return zip_path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
