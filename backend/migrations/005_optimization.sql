CREATE TABLE optimization_runs(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, status TEXT NOT NULL,
 payload TEXT NOT NULL, UNIQUE(campaign_id,idempotency_key));
CREATE INDEX optimization_campaign ON optimization_runs(campaign_id);
CREATE TABLE inference_cache(cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE semantic_audits(id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 content_hash TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX audits_content ON semantic_audits(campaign_id,content_hash);
CREATE TRIGGER cache_no_update BEFORE UPDATE ON inference_cache BEGIN SELECT RAISE(ABORT,'immutable cache'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON semantic_audits BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
