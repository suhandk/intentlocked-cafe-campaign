CREATE TABLE strategy_plans(
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    campaign_revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(campaign_id,campaign_revision)
);
CREATE TABLE generation_runs(
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(campaign_id,idempotency_key)
);
CREATE INDEX generation_campaign ON generation_runs(campaign_id);
CREATE TABLE baseline_variants(
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES generation_runs(id),
    audience_id TEXT NOT NULL,
    language TEXT NOT NULL,
    channel TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(run_id,audience_id,language,channel)
);
