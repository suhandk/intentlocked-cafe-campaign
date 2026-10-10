CREATE TABLE meta_operations(
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(campaign_id, idempotency_key)
);
CREATE TABLE meta_media(
    token_hash TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES meta_operations(id),
    expires_at REAL NOT NULL,
    mime TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes BLOB NOT NULL
);
CREATE TABLE meta_webhook_events(fingerprint TEXT PRIMARY KEY);
CREATE TABLE meta_message_status(provider_id TEXT PRIMARY KEY, status TEXT NOT NULL);
CREATE TABLE meta_inbound(
    recipient_hash TEXT PRIMARY KEY,
    received_at REAL NOT NULL
);
CREATE TABLE meta_attempts(
    id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES meta_operations(id),
    step TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL,
    http_status INTEGER
);
