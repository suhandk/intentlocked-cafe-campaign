CREATE TABLE campaigns (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    status TEXT NOT NULL CHECK(status IN ('draft','canonical_confirmed','forms_review','locked')),
    payload TEXT NOT NULL
);
CREATE TABLE fact_versions (
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    fact_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version >= 1),
    payload TEXT NOT NULL,
    PRIMARY KEY(campaign_id, fact_key, version)
);
CREATE TABLE brand_kits (
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(campaign_id, version)
);
CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    revision INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind = 'fact_lock'),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    fact_hash TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    UNIQUE(campaign_id, idempotency_key)
);
CREATE INDEX approval_campaign ON approvals(campaign_id, revision);
CREATE TRIGGER facts_no_update BEFORE UPDATE ON fact_versions BEGIN
    SELECT RAISE(ABORT, 'fact versions are append-only');
END;
CREATE TRIGGER facts_no_delete BEFORE DELETE ON fact_versions BEGIN
    SELECT RAISE(ABORT, 'fact versions are append-only');
END;
CREATE TRIGGER approval_no_update BEFORE UPDATE ON approvals BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable');
END;
CREATE TRIGGER approval_no_delete BEFORE DELETE ON approvals BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable');
END;
