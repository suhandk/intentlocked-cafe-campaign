CREATE TABLE campaign_plans (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    create_key TEXT UNIQUE NOT NULL,
    create_hash TEXT NOT NULL,
    payload TEXT NOT NULL
);
