-- QUERY 1: one canonical lead per observed CRM hash; not duplicate CRM entries.
-- conversion_rate is a fraction from 0 to 1 (multiply by 100 for percent).
SELECT source,
       count(*) AS total_lead_count,
       sum(converted) AS converted_lead_count,
       round(avg(converted::numeric), 6) AS conversion_rate
FROM leads
GROUP BY source
HAVING count(*) >= 200
ORDER BY avg(converted::numeric) DESC, source;

-- QUERY 2: audit the raw history, where duplicates have not been discarded.
-- All 9,160 lead_id values are unique, but 160 CRM hashes each appear twice.
-- Each pair is identical apart from lead_id (the extra ID has a -B suffix).
-- This supports hash-based deduplication for THIS export; no phone/email exists.
-- Return record IDs and a corroboration flag, not just a repeated hash.
SELECT crm_record_hash,
       count(*) AS record_count,
       array_agg(lead_id ORDER BY lead_id) AS lead_ids,
       count(DISTINCT (to_jsonb(r) - 'lead_id')) = 1 AS identical_except_lead_id
FROM leads_raw AS r
GROUP BY crm_record_hash
HAVING count(*) > 1
ORDER BY record_count DESC, crm_record_hash;

-- Prevention: UNIQUE(crm_record_hash) on canonical leads rejects repeated hashes.
-- import_leads() checks payload agreement before choosing the smallest lead_id.
-- Keep raw history for auditing and never apply the canonical UNIQUE constraint there.
-- The hash algorithm/identity semantics are unknown. A new hash for the same person
-- would evade this rule. In a real CRM, validate normalized phone (E.164) / email
-- and a documented business identity rule before adding corresponding unique keys;
-- shared contacts and repeat enquiries must not be merged blindly. Neither a
-- source/city/budget composite nor stripping -B alone proves person identity.
