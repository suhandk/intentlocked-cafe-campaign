CREATE TABLE IF NOT EXISTS social_profiles (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    version INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_videos (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS campaign_videos_campaign ON campaign_videos(campaign_id);
