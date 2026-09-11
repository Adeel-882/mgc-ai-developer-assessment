# MGC take-home assessment

A local sales assistant and intake lead scorer built with Python, FastAPI, Jinja,
pandas and scikit-learn. It uses the supplied documents and CSV directly. Both
tools are on one page. No API keys, hosted database, authentication, Docker or
deployment setup is needed. The PostgreSQL exercise is independent of the app.

## Install and demonstrate

Use **Python 3.12** (the tested version), with Python and pip installed. Run these
commands from the repository root.

```sh
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or activate on macOS/Linux:

```sh
source .venv/bin/activate
```

Then:

```sh
python -m pip install -r requirements.txt
python train_model.py
python -m unittest discover -s tests -v
python -m uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**. Stop the server with Ctrl+C. If PowerShell blocks
activation, invoke `.\.venv\Scripts\python.exe` in place of `python` in the commands
above; no execution-policy change is needed. If Windows says Python was not found,
install Python 3.12 first; the Microsoft Store alias alone is not a Python runtime.

The saved `model/lead_model.joblib` is included, so retraining is optional after
installation. `python train_model.py` regenerates it and `model/metrics.json`.
Restart the app after retraining because it caches the loaded model. Only load
joblib files you trust. All paths are resolved relative to this repository.

JSON endpoints are available at `POST /api/ask` (`{"question": "What's the transfer fee?"}`)
and `POST /api/score` (intake fields); interactive API docs are at `/docs`.

## Part 1: grounded document assistant

`document_assistant.py` reads all three Markdown documents, their dates and named
sections. With only three small documents, deterministic question routing and
extractive responses are sufficient. There is no vector store or external LLM.
For price questions, it parses table values and premium percentages from the
documents and calculates with `Decimal`. Other supported topics return document
passages, sometimes from multiple sections. Every response identifies its source
files, sections and document dates. Unsupported questions explicitly say the
documents do not provide the information and list the documents checked.

Conflict policy: the newer dated authoritative document wins, while the older
conflicting value is disclosed and both sources are cited. The May 2025 booking
policy therefore supersedes the April 2025 transfer fee. If dates are missing or
tied, the assistant flags the conflict for management rather than choosing a value.
This explicit resolver covers the observed transfer-fee conflict; it is not an
automatic conflict detector for arbitrary new documents.

### Five required cases

| Exact question | Verified answer |
|---|---|
| What's the base price of a 2-bed in Block B? | **PKR 22,425,000**, 2-Bed Standard; Corner has its own base price. April price list. |
| What's the total for a Margalla-facing corner unit on floor 15, 2-bed Block B? | Corner base **26,855,000** + floor 15 **4% / 1,074,200** + corner **3% / 805,650** + Margalla **6% / 1,611,300** = **PKR 30,346,150**. April price list. |
| What's the transfer fee? | **2.5% of the current list price**, May policy; discloses April price list's **2%** and explains the newer-document rule. Both sources. |
| What's the rental yield on a 1-bed? | MGC does not publish rental yield projections; sales staff must not quote projections verbally. Direct the query to the **marketing manager**. May FAQ. |
| Who is the anchor tenant? | **No anchor tenant has been confirmed** as of the March brochure's issue date; discussions are ongoing. March brochure. |

The quoted PKR 30,346,150 is the unit price with location premiums, **before other
charges or discounts**. The response separately lists utilities, mandatory parking,
optional additional parking and maintenance advance, without treating these as
location premiums. It does not silently compound percentages. If the floor is
missing, the result is labelled a subtotal. Block B's above-floor-12 orientation
rule is read alongside the price list; unavailable configurations are not priced.

## Part 2: PostgreSQL

`schema.sql` defines two simple tables: `leads_raw` preserves the supplied history;
`leads` contains one canonical record per observed CRM hash. Both use `lead_id` as
primary key, exact numeric money columns, timestamp without timezone, nullable
fields matching the CSV and checked 0/1 outcome/flags. The canonical table also has
`UNIQUE (crm_record_hash)`. Hashes are stored as text, not numeric model features.

There are **160 repeated hashes**, each occurring twice, even though every lead ID
is unique. In each pair, **every other field is identical**; the copied record ID
has a `-B` suffix. This makes the hash the strongest duplicate key supported by
this dump. `import_leads()` validates agreement, keeps the smallest lead ID and
refuses conflicting payloads. Reimporting identical canonical hashes is harmless.
No phone/email exists; do not invent a demographic composite identity rule. The
hash's provenance is unknown, so this does not promise to identify the same person
when their records have different hashes. A real CRM needs a verified contact and
business identity policy before adding normalized phone/email uniqueness.

`queries.sql` contains:

1. Conversion rate by source on canonical leads, at least 200 leads, best first.
   The rate is a fraction between 0 and 1 and counts do not inflate repeated records.
2. Duplicate groups in raw history, their record IDs and whether all other fields
   agree, with comments explaining detection and schema-level prevention.

Optional demonstration with PostgreSQL 14+ installed, in a **new empty database**:

```sh
createdb mgc_assessment
psql -v ON_ERROR_STOP=1 -d mgc_assessment -f schema.sql
psql -v ON_ERROR_STOP=1 -d mgc_assessment -c "\copy leads_raw FROM 'leads.csv' WITH (FORMAT csv, HEADER true, NULL '')"
psql -v ON_ERROR_STOP=1 -d mgc_assessment -c "SELECT import_leads();"
psql -v ON_ERROR_STOP=1 -d mgc_assessment -f queries.sql
```

Expected table counts are 9,160 raw and 9,000 canonical rows; the duplicate query
returns 160 groups. PostgreSQL is not required to run the app or model.

## Part 3: data and model decisions

Prediction time is **intake after agent assignment, before sales follow-up**.
This is a deliberate feature-availability boundary, not a claim that all columns
in the historical dump were available before conversion.

| Decision | Columns / reasoning |
|---|---|
| Keep intake categories | `source`, `city`, `area`, `property_type`. Trim/lowercase; normalize ISB, Rwp, khi to Islamabad, Rawalpindi, Karachi. |
| Keep intake numeric features | `budget_pkr_lac`, `bedrooms`, `agent_experience_years`, `is_overseas`, `referred_by_existing_client`. Budget stays in lac PKR. |
| Drop IDs/hashes from predictors | `lead_id`, `crm_record_hash`. Hash is used only to deduplicate before splitting. |
| Drop definite downstream leakage | `token_amount_received_pkr`: every conversion has a positive token payment (plus 85 nonconversions); this reflects progress toward the outcome. |
| Exclude unavailable/unverified-at-intake fields | `first_response_minutes`, `calls_made`, `total_call_seconds`, `whatsapp_replies`, `site_visits`: accumulated follow-up. `has_financing_approved`: no timestamp proving approval existed at intake. |
| Exclude raw date | `created_at`: preserve for SQL/audit, but do not learn arbitrary timestamps or calendar trends in this quick random-split baseline. |
| Target only | `converted` is never a predictor. |

These retained values are plausible before the first call only when captured at
intake: source comes from the incoming channel; city, area/property preference,
budget, bedrooms, overseas status and referral status can come from the enquiry
form or referral record. Agent experience is known after assignment. Leave any
unknown input blank; do not fill it using information learned later in the sales
process. The CSV does not prove when individual fields were collected.

Raw null counts: area **477**, budget **284**, bedrooms **3,602**, first response
**176**, agent experience **401**; all other columns have none. All missing bedrooms
are plots or commercial shops, so those become **0 / not applicable**. For remaining
numeric missing values, fit median imputation plus missing indicators on training
data only, then `StandardScaler`. Missing categories become `unknown`, followed by
`OneHotEncoder(handle_unknown="ignore")`. This also permits unseen scoring categories.
Plausible large values are retained rather than arbitrarily clipped. Dates all parse;
numeric fields contain no negatives and flags are binary. The original CSV is unchanged.

Deduplicate identical hashes **before** the split; reject conflicting duplicates.
Use an 80/20 stratified split with `random_state=42` and a `ColumnTransformer` /
`Pipeline` feeding `LogisticRegression(max_iter=1000)`. Preprocessing statistics
come only from training. No tuning, oversampling or class weighting is used; raw
probabilities are baseline estimates, not validated customer-level forecasts.
The saved model is the same model evaluated on the held-out test set, not a refit
that silently incorporates the test rows. `lead_scoring.score_lead(details)` returns
a float from 0 to 1 using the same feature preparation as training.

### Class balance and evaluation

- Raw: **634 / 9,160 converted (6.9214%)**; 8,526 not converted.
- After removing 160 extra records: **626 / 9,000 converted (6.9556%)**; 8,374 not converted.

Measured on 1,800 held-out leads (125 converted), using 7,200 training leads:

| Metric | Actual result |
|---|---:|
| Average Precision (primary) | **0.1556549244** |
| No-skill AP / test prevalence | **0.0694444444** |
| ROC-AUC (secondary) | **0.6725779104** |

AP is about 2.24 times the prevalence baseline, a modest ranking improvement.
The full measured values and split details are saved in `model/metrics.json`.

Average Precision (AP) summarizes the precision-recall tradeoff and focuses on
finding the rare converted leads without overwhelming sales with false positives.
A model that predicts no conversions would get about 93% accuracy, so accuracy is
misleading here. The no-skill AP reference is the test-set conversion prevalence.
AP is the step-weighted summary of the precision-recall curve, not trapezoidal
interpolation of PR-AUC. ROC-AUC is included only as a secondary ranking metric.

## Validation and limitations

The tests cover the five exact questions, additive arithmetic, source dates,
ambiguous chronology, changed source prices, unavailable units, an overseas
transfer exception, unknown questions, deduplication conflicts, feature exclusion,
missing/unseen inputs, form submission, JSON endpoints and HTML escaping.

Validation performed on Windows with Python 3.12.14:

- Installed `requirements.txt`; `python -m pip check` reports no broken requirements.
- Repeated installation in a fresh Python 3.12 virtual environment, then trained,
  ran all 19 tests and checked the reload-enabled server over HTTP. Model and
  metrics files reproduced byte-for-byte. The audit server used an alternate
  local port because the earlier demo was still running.
- Trained and saved the model; actual results appear above.
- Ran `python -m unittest discover -s tests -v`: **19 tests passed**, including
  empty document submissions, optional/missing scoring fields and the phrase
  "current transfer fee" (which must not match a rental question).
- Started Uvicorn and checked the live page, all five questions through the JSON
  endpoint, the assistant HTML form and both scoring endpoints over HTTP: **passed**.
- The example Referral / ISB / Apartment lead (180 lac, 2 beds, assigned agent
  experience 5 years, domestic, existing-client referral) scores approximately
  **39.11%**; missing area is imputed.
- Reviewed the PostgreSQL schema/query syntax and corroborated the duplicate rule
  against the CSV. **SQL has not been executed against PostgreSQL**, which is not
  installed in the validation environment. The optional commands above reproduce
  that check on a machine with PostgreSQL.

- This is a rule-based assistant for the supplied small corpus. Unrecognized
  phrasing may return a related excerpt or ask for clarification; it does not
  synthesize arbitrary multi-part questions or calculate combined discounts.
- Documents date from March–May 2025. They are not live market data, current stock
  availability or a confirmation that every floor/unit combination is available.
- Historical intake fields have no separate change history. Their availability at
  intake is an assumption; obtain timestamped snapshots before real use.
- A single random holdout is only a baseline. Temporal performance, calibration,
  fairness and business impact have not been established.
- Blank numeric form fields can emit a non-fatal pandas deprecation warning;
  scoring succeeds with the pinned dependencies.
- PostgreSQL SQL is supplied for the database exercise; execution status is recorded
  above. It is not wired into the app.
- The app is a local assessment demo, not a publicly deployed service.

## With more time

Verify CRM identity semantics and feature timestamps; evaluate a temporal holdout,
calibration and precision/recall at the team's calling capacity; add paraphrase and
multi-question coverage; validate the SQL import on the target PostgreSQL version.

## File guide

- `app.py`, `templates/index.html`: both web forms and JSON endpoints.
- `document_assistant.py`: section retrieval, conflict handling and calculations.
- `train_model.py`, `lead_scoring.py`: train/evaluate/save and reusable scoring.
- `schema.sql`, `queries.sql`: independent PostgreSQL deliverables.
- `model/lead_model.joblib`, `model/metrics.json`: runnable model and measured metrics.
- `tests/`: automated checks. `WORKING_NOTES.md`: full pre-implementation inspection.
- `requirements.txt`, `.gitignore`: local dependencies and generated-file exclusions.

The original `BRIEF.md`, `docs/` and `leads.csv` are preserved. No credentials or
external service configuration are required. The brief explicitly asks for a public
GitHub submission; generated environments, logs and caches are excluded from Git.
