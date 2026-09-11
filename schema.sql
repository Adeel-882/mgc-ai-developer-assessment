-- PostgreSQL 14+. The raw import preserves all CRM records for auditing.
-- Monetary amounts are exact NUMERIC; one lac = PKR 100,000.
-- No timezone was supplied, so created_at is a timestamp WITHOUT time zone.
CREATE TABLE leads_raw (
    lead_id TEXT PRIMARY KEY CHECK (btrim(lead_id) <> ''),
    created_at TIMESTAMP NOT NULL,
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    city TEXT NOT NULL,
    area TEXT,
    property_type TEXT NOT NULL,
    budget_pkr_lac NUMERIC(12,2) CHECK (budget_pkr_lac >= 0),
    bedrooms NUMERIC(3,1) CHECK (bedrooms BETWEEN 1 AND 5 AND bedrooms = trunc(bedrooms)),
    first_response_minutes NUMERIC(12,2) CHECK (first_response_minutes >= 0),
    calls_made INTEGER NOT NULL CHECK (calls_made >= 0),
    total_call_seconds NUMERIC(14,2) NOT NULL CHECK (total_call_seconds >= 0),
    whatsapp_replies INTEGER NOT NULL CHECK (whatsapp_replies >= 0),
    site_visits INTEGER NOT NULL CHECK (site_visits >= 0),
    agent_experience_years NUMERIC(5,2) CHECK (agent_experience_years >= 0),
    is_overseas SMALLINT NOT NULL CHECK (is_overseas IN (0,1)),
    referred_by_existing_client SMALLINT NOT NULL CHECK (referred_by_existing_client IN (0,1)),
    has_financing_approved SMALLINT NOT NULL CHECK (has_financing_approved IN (0,1)),
    token_amount_received_pkr NUMERIC(16,2) NOT NULL CHECK (token_amount_received_pkr >= 0),
    crm_record_hash TEXT NOT NULL CHECK (btrim(crm_record_hash) <> ''),
    converted SMALLINT NOT NULL CHECK (converted IN (0,1))
);

-- SMALLINT flags allow the source CSV's 0/1 values to import without rewriting it.
-- Hashes are identifiers, not quantities. Keep their original text representation.
CREATE TABLE leads (LIKE leads_raw INCLUDING ALL);
ALTER TABLE leads ADD CONSTRAINT leads_crm_record_hash_unique UNIQUE (crm_record_hash);

-- In this dump, 160 hash pairs match in ALL other fields except lead_id.
-- Refuse conflicting records instead of silently merging a potential hash collision.
-- SELECT import_leads() after loading leads_raw, inside the same transaction if desired.
CREATE FUNCTION import_leads() RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT crm_record_hash
        FROM leads_raw AS r
        GROUP BY crm_record_hash
        HAVING count(DISTINCT (to_jsonb(r) - 'lead_id')) > 1
    ) THEN
        RAISE EXCEPTION 'Conflicting records share a CRM hash; review before importing';
    END IF;
    IF EXISTS (
        SELECT 1 FROM leads_raw r JOIN leads l USING (crm_record_hash)
        WHERE (to_jsonb(r) - 'lead_id') IS DISTINCT FROM (to_jsonb(l) - 'lead_id')
    ) THEN
        RAISE EXCEPTION 'Incoming record conflicts with canonical lead; review before updating';
    END IF;
    INSERT INTO leads
    SELECT DISTINCT ON (crm_record_hash) * FROM leads_raw
    ORDER BY crm_record_hash, lead_id
    ON CONFLICT (crm_record_hash) DO NOTHING;
END;
$$;
