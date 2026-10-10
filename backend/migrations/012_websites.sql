CREATE TABLE website_drafts (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
    version INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE UNIQUE INDEX website_owner_campaign ON website_drafts(owner_id, campaign_id);
CREATE TABLE website_bundles (
    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, owner_id TEXT NOT NULL,
    draft_version INTEGER NOT NULL, facts_revision INTEGER NOT NULL,
    facts_hash TEXT NOT NULL, sha256 TEXT NOT NULL, bytes BLOB NOT NULL,
    html TEXT NOT NULL, report TEXT NOT NULL
);
CREATE TABLE website_assets (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, draft_id TEXT NOT NULL,
    mime TEXT NOT NULL, sha256 TEXT NOT NULL, bytes BLOB NOT NULL
);
CREATE TABLE website_tokens (
    owner_id TEXT NOT NULL, provider TEXT NOT NULL, nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL, suffix TEXT NOT NULL,
    PRIMARY KEY(owner_id, provider)
);
CREATE TABLE website_publish_jobs (
    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, draft_id TEXT NOT NULL,
    bundle_hash TEXT NOT NULL, payload TEXT NOT NULL
);
