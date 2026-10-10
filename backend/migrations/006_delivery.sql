CREATE TABLE change_proposals (
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 request_key TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(campaign_id,request_key)
);
CREATE TABLE owner_actions (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id), action_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(campaign_id,action_key)
);
CREATE TABLE campaign_versions (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id), revision INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(campaign_id,revision)
);
CREATE TABLE delivery_items (
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id), payload TEXT NOT NULL
);
CREATE TABLE delivery_links (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id), revision INTEGER NOT NULL,
 item_id TEXT NOT NULL REFERENCES delivery_items(id), state TEXT NOT NULL,
 PRIMARY KEY(campaign_id,revision,item_id)
);
CREATE TABLE delivery_audits (
 item_id TEXT PRIMARY KEY REFERENCES delivery_items(id),
 audit_id TEXT NOT NULL REFERENCES semantic_audits(id)
);
CREATE TABLE asset_approvals (
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id), payload TEXT NOT NULL
);
CREATE TABLE item_approvals (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id), revision INTEGER NOT NULL,
 item_id TEXT NOT NULL REFERENCES delivery_items(id),
 approval_id TEXT NOT NULL REFERENCES asset_approvals(id),
 PRIMARY KEY(campaign_id,revision,item_id)
);
CREATE TABLE ledger_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 revision INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX delivery_campaign ON delivery_links(campaign_id,revision);
CREATE TRIGGER delivery_no_update BEFORE UPDATE ON delivery_items BEGIN
 SELECT RAISE(ABORT,'delivery items are immutable'); END;
CREATE TRIGGER asset_approval_no_update BEFORE UPDATE ON asset_approvals BEGIN
 SELECT RAISE(ABORT,'asset approvals are immutable'); END;
CREATE TRIGGER version_no_update BEFORE UPDATE ON campaign_versions BEGIN
 SELECT RAISE(ABORT,'campaign versions are immutable'); END;
