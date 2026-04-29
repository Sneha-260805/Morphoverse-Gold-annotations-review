# MorphoVerse++ Human Review Dashboard

This Streamlit app lets human reviewers inspect LLM-generated poem annotations and save clean human-reviewed gold annotation JSON files.

## What it does

Reviewers can:

- select a language
- select a poem
- view original poem and English translation side by side
- edit culture entities, metaphors, emotions, and visual motifs
- approve, approve with corrections, reject, or mark a poem as needing major revision
- submit a final decision with reason
- save one reviewed JSON per poem
- maintain an audit log

## Important exclusions

This version intentionally excludes:

- the full `Bodo` folder
- the failed Telugu poem `MV++_1443`

These exclusions are defined in:

```text
utils/schema_utils.py
```

## Expected input folder

Place the annotation output folder here:

```text
review_app/data/outputs_new_4/
```

Expected structure:

```text
outputs_new_4/
├── annotation_summary.csv
├── human_review_queue.csv
├── Assamese/
├── Bengali/
├── Hindi/
├── Marathi/
└── Telugu/
```

The app also auto-detects `outputs_new_4` if it exists beside `app.py`.

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
streamlit run app.py
```

Run the admin dashboard:

```bash
streamlit run admin_dashboard.py
```

## Output files

Reviewed JSON files are saved to:

```text
reviewed_outputs/<Language>/<poem_id>/<submission_number>_reviewed.json
```

Audit logs are saved to:

```text
audit_logs/review_audit_log.jsonl
```

## Admin dashboard

Use `admin_dashboard.py` to inspect what reviewers submitted.

It shows:

- total reviewed poems
- total review submissions
- submissions by language and poem
- each submission number, status, confidence, timestamp, and final comment
- corrected culture entities, metaphors, emotions, and visual motifs
- side-by-side poem and translation for each submitted review

The dashboard reads local files from:

```text
reviewed_outputs/<Language>/<poem_id>/<submission_number>_reviewed.json
```

## Recommended reviewer workflow

1. Open the shared review link.
2. Select language.
3. Select poem.
4. Confirm the submission number shown for that poem.
5. Read original poem and translation.
6. Edit annotation tables.
7. Select final decision.
8. Add reason/comment.
9. Confirm and submit.

Raw LLM annotation files are never overwritten. Reviews from different reviewers are saved separately.

## Shared review link

For deployment, share one app link with all reviewers:

```text
https://your-streamlit-app-url.streamlit.app/
```

Reviewers do not need reviewer IDs. For each poem, the app automatically assigns the next submission number:

```text
review_01
review_02
review_03
```

For example, the first person who submits a review for `MV++_0001` is saved as `review_01`. The next submission for that same poem is saved as `review_02`.

## Deployment checklist

For a small local review, the app saves reviewed JSON files under `reviewed_outputs/`.
For deployed review with multiple reviewers, configure persistent storage so submissions are not lost when the app restarts.

### Optional Supabase storage

Create these tables in Supabase SQL editor:

```sql
create table if not exists reviewed_annotations (
  review_id text primary key,
  poem_id text not null,
  language text not null,
  title text,
  review_status text not null,
  reviewer_id text not null,
  reviewer_confidence text,
  reviewed_at timestamptz not null,
  payload jsonb not null
);

create table if not exists review_audit_log (
  id bigint generated always as identity primary key,
  event text not null,
  review_id text,
  poem_id text not null,
  language text not null,
  reviewer_id text not null,
  decision text not null,
  reviewer_confidence text,
  reviewed_at timestamptz not null,
  output_file text
);
```

Add these secrets in Streamlit Cloud:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

When these secrets are present, every submission is saved both locally and to Supabase.
When they are missing, the app still runs and saves locally only.

Each submission gets a separate review row using:

```text
<poem_id>__<submission_number>
```

This means multiple people can review the same poem without replacing each other's submissions.

## Review safeguards

The app now checks before submission that:

- required annotation fields are not blank
- `review_action` is selected
- reviewer comments are added for modified, removed, or added rows
- reviews from different reviewers are saved separately
- `approved` is not used when rows are marked `modify`, `remove`, or `add`
