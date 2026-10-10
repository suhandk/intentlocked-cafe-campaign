CREATE TABLE social_profiles (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    version INTEGER NOT NULL,
    payload TEXT NOT NULL
);
