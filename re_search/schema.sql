-- re-search SQLite schema (Phase 0–4 を一括定義。IF NOT EXISTS で再実行安全)

-- ───────────────────────── core: source / location / listing ─────────────────────────

CREATE TABLE IF NOT EXISTS source (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('manual','csv','api','scrape')),
  url TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS location (
  id INTEGER PRIMARY KEY,
  raw_address TEXT NOT NULL,
  lat REAL,
  lon REAL,
  pref TEXT,
  ward TEXT,
  town_code TEXT,
  nearest_station TEXT,
  walk_min_calc INTEGER,
  elevation_m REAL,
  slope_deg REAL,
  terrain_class TEXT,        -- 台地/低地/谷底/丘陵/埋立 等
  geocoded_at TEXT,
  UNIQUE(raw_address)
);

CREATE INDEX IF NOT EXISTS idx_location_town ON location(town_code);
CREATE INDEX IF NOT EXISTS idx_location_ward ON location(ward);

CREATE TABLE IF NOT EXISTS listing (
  id INTEGER PRIMARY KEY,
  address TEXT NOT NULL,
  layout TEXT,                -- ワンルーム/1K/1LDK 等
  area_m2 REAL,
  rent_jpy INTEGER,
  mgmt_fee_jpy INTEGER,
  building_year INTEGER,
  walk_min INTEGER,
  station TEXT,
  structure TEXT,             -- RC/SRC/木造 等
  earthquake_grade TEXT,      -- 旧耐震/新耐震/2000基準 等
  ownership TEXT,             -- 所有権/借地権 等
  total_units INTEGER,
  orientation TEXT,           -- 玄関方位 N/NE/E/SE/S/SW/W/NW
  source_id INTEGER REFERENCES source(id),
  location_id INTEGER REFERENCES location(id),
  first_seen_at TEXT,
  last_seen_at TEXT,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_listing_location ON listing(location_id);
CREATE INDEX IF NOT EXISTS idx_listing_status ON listing(status);

CREATE TABLE IF NOT EXISTS listing_snapshot (
  id INTEGER PRIMARY KEY,
  listing_id INTEGER NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  snapshotted_at TEXT NOT NULL,
  rent_jpy INTEGER,
  mgmt_fee_jpy INTEGER,
  raw_json TEXT
);

-- ───────────────────────── area data ─────────────────────────

CREATE TABLE IF NOT EXISTS area_stats (
  town_code TEXT NOT NULL,
  year INTEGER NOT NULL,
  population INTEGER,
  koji_chika_jpy INTEGER,     -- 地価公示 円/m^2
  crime_per_1k REAL,          -- 人口千人あたり
  redevelopment_flag INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  PRIMARY KEY(town_code, year)
);

CREATE TABLE IF NOT EXISTS area_history (
  id INTEGER PRIMARY KEY,
  town_code TEXT NOT NULL,
  era TEXT NOT NULL,          -- edo/meiji/taisho/showa_pre/showa_post
  old_name TEXT,
  old_use TEXT,               -- 武家屋敷/寺社/田畑/湿地/工場/遊郭/軍施設/河川敷 等
  old_terrain TEXT,
  source TEXT,
  citation TEXT,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_area_history_town ON area_history(town_code);

CREATE TABLE IF NOT EXISTS waterway (
  id INTEGER PRIMARY KEY,
  name TEXT,
  kind TEXT NOT NULL,         -- river/old_river/spring/pond
  geom_wkt TEXT,
  source TEXT
);

-- ───────────────────────── poi ─────────────────────────

CREATE TABLE IF NOT EXISTS poi (
  id INTEGER PRIMARY KEY,
  location_id INTEGER REFERENCES location(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,         -- super/gym/busstop/station/...
  name TEXT,
  brand TEXT,
  distance_m REAL,
  lat REAL,
  lon REAL,
  osm_type TEXT,
  osm_id INTEGER,
  fetched_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_poi_location ON poi(location_id);
CREATE INDEX IF NOT EXISTS idx_poi_kind ON poi(kind);

-- ───────────────────────── redevelopment ─────────────────────────

CREATE TABLE IF NOT EXISTS redevelopment_project (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN (
    'mansion_rebuild','urban_redev1','urban_redev2','lot_adjust',
    'disaster_zone','private_plan'
  )),
  status TEXT NOT NULL CHECK(status IN (
    'planned','announced','approved','under_construction','completed'
  )),
  announced_at TEXT,
  approved_at TEXT,
  expected_completion_year INTEGER,
  scope_kind TEXT CHECK(scope_kind IN ('address_list','town_codes','geojson')),
  scope_data TEXT,            -- JSON / 住所列挙テキスト / GeoJSON
  summary TEXT,
  source_url TEXT,
  source_name TEXT,
  fetched_at TEXT,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_redev_status ON redevelopment_project(status);

CREATE TABLE IF NOT EXISTS listing_redev (
  listing_id INTEGER NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES redevelopment_project(id) ON DELETE CASCADE,
  link_kind TEXT CHECK(link_kind IN ('auto','manual')),
  confidence TEXT CHECK(confidence IN ('high','medium','low')),
  confirmed_by_user INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  linked_at TEXT,
  PRIMARY KEY(listing_id, project_id)
);

-- ───────────────────────── scoring ─────────────────────────

CREATE TABLE IF NOT EXISTS score (
  listing_id INTEGER NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK(kind IN ('livability','locality','fengshui')),
  value REAL,
  breakdown_json TEXT,
  scored_at TEXT,
  PRIMARY KEY(listing_id, kind)
);

CREATE TABLE IF NOT EXISTS fengshui_eval (
  id INTEGER PRIMARY KEY,
  listing_id INTEGER NOT NULL REFERENCES listing(id) ON DELETE CASCADE,
  rule_id TEXT NOT NULL,
  verdict TEXT CHECK(verdict IN ('吉','凶','中立')),
  score_delta REAL,
  note TEXT,
  evaluated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fengshui_eval_listing ON fengshui_eval(listing_id);

-- ───────────────────────── user collections ─────────────────────────

CREATE TABLE IF NOT EXISTS favorite (
  listing_id INTEGER PRIMARY KEY REFERENCES listing(id) ON DELETE CASCADE,
  added_at TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS compare_set (
  id INTEGER PRIMARY KEY,
  name TEXT,
  listing_ids_json TEXT
);

-- ───────────────────────── schema versioning ─────────────────────────

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
