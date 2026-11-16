-- Load Lore sync: one row per sync code (id = SHA-256 of the code, never the code itself)
CREATE TABLE IF NOT EXISTS sync (
  id      TEXT PRIMARY KEY,
  rev     INTEGER NOT NULL,   -- goes up by one on every save
  data    TEXT NOT NULL,      -- JSON: {v, hand, favs, prices}
  created INTEGER NOT NULL,   -- ms since 1970
  updated INTEGER NOT NULL,
  seen    INTEGER NOT NULL    -- last opened (at most once a day); idle copies are removed after 2 years
);
CREATE INDEX IF NOT EXISTS sync_seen ON sync (seen);
