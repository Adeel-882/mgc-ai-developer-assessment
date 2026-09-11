# Pre-implementation inspection

Read BRIEF.md, all three documents in docs/, and profiled all 20 CSV columns before implementation. The four deliverables are a local grounded assistant, PostgreSQL schema and two queries, a conversion baseline, and one web page connecting both tools. No external service is necessary.

## Documents

- March 2025 brochure: project facts, configurations, amenities, approvals, sales office; anchor tenant explicitly unconfirmed. Block B above floor 12 faces Margalla, but studios and 1-beds cannot have that orientation.
- April 2025 price list: Block B 2-bed Standard = PKR 22,425,000; Corner = PKR 26,855,000. Floor 15 +4%, corner +3%, Margalla +6%, added on the base (not compounded). Other charges are separate. Includes payment plan and discounts.
- May 2025 FAQ: booking, refunds, transfer conditions, overseas exception, possession, bank/rental restrictions and unconfirmed gas timeline. Transfer fee 2.5% supersedes April's 2%; disclose and cite both. Rental projections must be referred to the marketing manager.
- Use document sections and parsed tables, explicit calculation rules, and conservative excerpt retrieval. Unknown answers must say so. Claims describe the supplied dated documents, not live availability or prices.

## CSV audit

- 9,160 rows, 20 columns; 0 exact duplicate rows; all lead_id values unique.
- 9,000 distinct crm_record_hash values. 160 groups of two records (320 rows), identical in every column except lead_id; extra IDs end in -B. Hash is the strongest observed duplicate key; its provenance is unknown, so it is not proof of permanent person identity. No phone or email fields exist.
- Raw outcome: 634 converted, 8,526 not converted (6.9214% converted). Retaining one record per hash: 626 converted, 8,374 not converted (6.9556%). Deduplicate before stratified splitting.
- Text: lead_id, created_at, source, city, area, property_type. Integers: calls_made, whatsapp_replies, site_visits, is_overseas, referred_by_existing_client, has_financing_approved, crm_record_hash, converted. Decimal/numeric: budget_pkr_lac, bedrooms, first_response_minutes, total_call_seconds, agent_experience_years, token_amount_received_pkr.
- Nulls: area 477; budget 284; bedrooms 3,602; first response 176; agent experience 401. Others 0. All missing bedrooms correspond to Plot (2,553) or Commercial Shop (1,049), so they mean not applicable, not an unknown residential bedroom count.
- Dates parse successfully, ranging from 2024-01-01 00:14:03 to 2025-10-01 22:23:19; no timezone supplied. Retain SQL timestamp without timezone; exclude raw timestamp from the baseline.
- Source: 9 categories, all >=200 rows; property type: 6; area: 10 plus missing. City has 21 raw spellings: normalize case and ISB / Rwp / khi to Islamabad / Rawalpindi / Karachi (9 canonical cities).
- Numeric ranges: budget 18–1,421 lac; bedrooms 1–5 where applicable; first response 1–3,107 minutes; calls 0–10; call seconds 0–4,379; replies 0–8; visits 0–4; agent experience 0–20. No negative numeric values or nonbinary flags. Keep plausible outliers; use scaling, not arbitrary clipping.
- Token payments >0 for all 634 conversions and 85 nonconversions. This is downstream information and unsuitable as a predictor.
- Define scoring at intake after assignment: use source, city, area, property_type, budget_pkr_lac, bedrooms, agent_experience_years, is_overseas, referred_by_existing_client. Drop IDs/hash; exclude timestamp, token, engagement aggregates and financing approval (timing unverified). Later-stage scoring requires timestamped snapshots.
- Train logistic regression with train-only imputation, numeric scaling and one-hot encoding; evaluate Average Precision against test prevalence. Do not rebalance classes when returning raw baseline probabilities. Save model and actual metrics.

## Implementation decisions

Keep the original CSV untouched. SQL uses a staging table to retain the messy import, then a canonical leads table with a unique nonblank CRM hash. Queries explicitly operate on raw history for duplicate detection and canonical data for conversion rates. An import procedure in schema.sql makes this distinction runnable.

Implement both web forms with FastAPI/Jinja, no authentication, hosting, database connection, LLM key or frontend framework. Cover the five exact assistant questions, leakage/deduplication boundaries, scoring and HTTP integration. Keep limitations explicit in README.
