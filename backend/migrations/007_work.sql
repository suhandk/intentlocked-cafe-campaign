CREATE TABLE work_jobs (
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 status TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(campaign_id,idempotency_key)
);
CREATE TABLE workflow_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(campaign_id,fingerprint)
);
