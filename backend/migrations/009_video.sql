CREATE TABLE campaign_videos (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX campaign_videos_campaign ON campaign_videos(campaign_id);
