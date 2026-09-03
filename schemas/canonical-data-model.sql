-- Canonical schema draft for source normalization. SQLite-compatible.

CREATE TABLE cards (
    passcode INTEGER PRIMARY KEY,
    konami_cid INTEGER UNIQUE,
    card_type INTEGER,
    attack INTEGER,
    defense INTEGER,
    level_rank_link INTEGER,
    race INTEGER,
    attribute INTEGER,
    archetype TEXT,
    first_ocg_date TEXT,
    first_tcg_date TEXT
);

CREATE TABLE environment_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    product TEXT NOT NULL CHECK (product = 'paper'),
    regulation TEXT NOT NULL CHECK (regulation IN ('TCG', 'OCG')),
    format TEXT NOT NULL,
    region TEXT NOT NULL,
    mode TEXT NOT NULL,
    banlist_name TEXT NOT NULL,
    banlist_effective_date TEXT NOT NULL,
    card_pool_cutoff TEXT,
    core_commit TEXT NOT NULL,
    scripts_commit TEXT NOT NULL,
    cdb_commit TEXT NOT NULL,
    lflist_commit TEXT
);

CREATE TABLE card_texts (
    passcode INTEGER NOT NULL,
    locale TEXT NOT NULL,
    text_version TEXT NOT NULL,
    name TEXT NOT NULL,
    effect_text TEXT,
    pendulum_text TEXT,
    source_name TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (passcode, locale, text_version, source_name),
    FOREIGN KEY (passcode) REFERENCES cards(passcode)
);

CREATE TABLE card_prints (
    source_name TEXT NOT NULL,
    source_print_id TEXT NOT NULL,
    passcode INTEGER NOT NULL,
    locale TEXT,
    set_name TEXT,
    set_code TEXT,
    rarity TEXT,
    release_date TEXT,
    PRIMARY KEY (source_name, source_print_id, set_code),
    FOREIGN KEY (passcode) REFERENCES cards(passcode)
);

CREATE TABLE rulings (
    source_name TEXT NOT NULL,
    ruling_id TEXT NOT NULL,
    passcode INTEGER NOT NULL,
    locale TEXT,
    title TEXT,
    question TEXT,
    answer TEXT,
    published_at TEXT,
    source_url TEXT,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (source_name, ruling_id),
    FOREIGN KEY (passcode) REFERENCES cards(passcode)
);

CREATE TABLE banlists (
    snapshot_id TEXT NOT NULL,
    list_name TEXT NOT NULL,
    effective_date TEXT,
    passcode INTEGER NOT NULL,
    card_limit INTEGER NOT NULL CHECK (card_limit BETWEEN 0 AND 3),
    source_commit TEXT,
    PRIMARY KEY (snapshot_id, passcode),
    FOREIGN KEY (snapshot_id) REFERENCES environment_snapshots(snapshot_id),
    FOREIGN KEY (passcode) REFERENCES cards(passcode)
);

CREATE TABLE engine_scripts (
    passcode INTEGER PRIMARY KEY,
    script_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_commit TEXT NOT NULL,
    FOREIGN KEY (passcode) REFERENCES cards(passcode)
);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    name TEXT NOT NULL,
    event_type TEXT,
    start_date TEXT,
    end_date TEXT,
    city TEXT,
    country TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    label_confidence TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES environment_snapshots(snapshot_id)
);

CREATE TABLE decks (
    deck_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_deck_id TEXT NOT NULL,
    event_id TEXT,
    title TEXT,
    archetype TEXT,
    player_name TEXT,
    placement TEXT,
    published_at TEXT,
    source_url TEXT NOT NULL,
    label_confidence TEXT NOT NULL,
    UNIQUE (source_name, source_deck_id),
    FOREIGN KEY (snapshot_id) REFERENCES environment_snapshots(snapshot_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE TABLE deck_cards (
    deck_id TEXT NOT NULL,
    zone TEXT NOT NULL CHECK (zone IN ('main', 'extra', 'side')),
    passcode INTEGER,
    source_konami_cid INTEGER,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 3),
    PRIMARY KEY (deck_id, zone, passcode, source_konami_cid),
    FOREIGN KEY (deck_id) REFERENCES decks(deck_id),
    FOREIGN KEY (passcode) REFERENCES cards(passcode),
    CHECK (passcode IS NOT NULL OR source_konami_cid IS NOT NULL)
);

CREATE TABLE metagame_snapshots (
    meta_snapshot_id TEXT PRIMARY KEY,
    environment_snapshot_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    regions_json TEXT,
    tournament_count INTEGER,
    top_deck_count INTEGER,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    FOREIGN KEY (environment_snapshot_id) REFERENCES environment_snapshots(snapshot_id)
);

CREATE TABLE metagame_archetypes (
    meta_snapshot_id TEXT NOT NULL,
    archetype TEXT NOT NULL,
    deck_count INTEGER NOT NULL,
    variants_text TEXT,
    PRIMARY KEY (meta_snapshot_id, archetype),
    FOREIGN KEY (meta_snapshot_id) REFERENCES metagame_snapshots(meta_snapshot_id)
);

CREATE TABLE raw_records (
    raw_record_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    media_type TEXT,
    local_path TEXT NOT NULL,
    parser_version TEXT,
    license_note TEXT
);
