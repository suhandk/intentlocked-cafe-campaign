CREATE TABLE art_backgrounds(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 art_key TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX art_reuse ON art_backgrounds(campaign_id,art_key);
CREATE TABLE poster_artifacts(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 render_hash TEXT NOT NULL UNIQUE, payload TEXT NOT NULL);
CREATE TABLE campaign_logos(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 sha256 TEXT NOT NULL, payload TEXT NOT NULL);
