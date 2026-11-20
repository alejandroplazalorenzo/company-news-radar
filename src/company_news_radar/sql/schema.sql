-- company-news-radar, local SQLite store.
--
--   capture        raw results of the sources, with the triage outcome
--   story          one event; captures point to it
--   party          watched companies named in a story
--   verdict        where each classified story stands now
--   answer         every answer of every classifier version
--   decision       pair verdicts of the judge or of a person, and the merges made
--   source_check   one row per source and fetch: new items, or the error
--   sitemap_seen   addresses already known per newsroom sitemap
--   run_log        fetch and process runs with their summaries
--
-- The store runs this file once, on an empty database (PRAGMA user_version = 0), and then
-- sets user_version to 1.

CREATE TABLE story (
    id            INTEGER PRIMARY KEY,
    origin        TEXT    NOT NULL,
    headline      TEXT    NOT NULL,
    url           TEXT    NOT NULL,
    published     TEXT,
    publisher     TEXT,
    standfirst    TEXT,
    record_type   TEXT,
    record_level  TEXT,
    opened_at     TEXT    NOT NULL
);

CREATE TABLE capture (
    id              INTEGER PRIMARY KEY,
    story_id        INTEGER REFERENCES story (id),
    ident           TEXT    NOT NULL UNIQUE,
    origin          TEXT    NOT NULL,
    channel         TEXT    NOT NULL,
    subject         TEXT,
    headline        TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    published       TEXT,
    publisher       TEXT,
    publisher_host  TEXT,
    standfirst      TEXT,
    page_read       INTEGER CHECK (page_read IN (0, 1)),
    record_type     TEXT,
    record_level    TEXT,
    amount_eur      REAL,
    tax_ids         TEXT    DEFAULT '[]',
    triage          TEXT,
    captured_at     TEXT    NOT NULL
);
CREATE INDEX capture_story ON capture (story_id, published);
CREATE INDEX capture_waiting ON capture (id) WHERE triage IS NULL;

CREATE TABLE party (
    story_id   INTEGER NOT NULL REFERENCES story (id),
    company    TEXT    NOT NULL,
    how        TEXT    NOT NULL,
    evidence   TEXT,
    tax_id     TEXT,
    confirmed  INTEGER CHECK (confirmed IN (0, 1)),
    id         INTEGER PRIMARY KEY,
    UNIQUE (story_id, company)
);

CREATE TABLE verdict (
    story_id    INTEGER PRIMARY KEY REFERENCES story (id),
    kind        TEXT    NOT NULL,
    level       TEXT    NOT NULL,
    shown       INTEGER NOT NULL CHECK (shown IN (0, 1)),
    why_hidden  TEXT,
    on_front    INTEGER CHECK (on_front IN (0, 1)),
    alerts      INTEGER CHECK (alerts IN (0, 1)),
    country     TEXT,
    fact_key    TEXT,
    gist        TEXT,
    decided_by  TEXT    NOT NULL,
    decided_at  TEXT    NOT NULL
);

CREATE VIEW story_now AS
SELECT story.*, verdict.kind, verdict.level, verdict.shown, verdict.why_hidden,
       verdict.on_front, verdict.alerts, verdict.country, verdict.fact_key, verdict.gist,
       verdict.decided_by,
       CASE WHEN verdict.story_id IS NULL THEN 'new'
            WHEN verdict.shown = 1 THEN 'shown'
            ELSE 'hidden' END AS state
FROM story LEFT JOIN verdict ON verdict.story_id = story.id;

CREATE TABLE answer (
    id          INTEGER PRIMARY KEY,
    version     TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    story_id    INTEGER NOT NULL REFERENCES story (id),
    kind        TEXT    NOT NULL,
    level       TEXT    NOT NULL,
    gist        TEXT,
    country     TEXT,
    fact_key    TEXT,
    parties     TEXT    NOT NULL,
    shown       INTEGER NOT NULL,
    why_hidden  TEXT,
    on_front    INTEGER NOT NULL,
    alerts      INTEGER NOT NULL,
    given_at    TEXT    NOT NULL
);
CREATE INDEX answer_version ON answer (version, story_id);

CREATE TABLE decision (
    id         INTEGER PRIMARY KEY,
    act        TEXT    NOT NULL CHECK (act IN ('verdict', 'merge')),
    first_id   INTEGER NOT NULL,
    second_id  INTEGER NOT NULL,
    same       INTEGER,
    author     TEXT    NOT NULL,
    kept_id    INTEGER,
    made_at    TEXT    NOT NULL
);
CREATE UNIQUE INDEX decision_pair ON decision (first_id, second_id)
    WHERE act = 'verdict';

CREATE TABLE source_check (
    id          INTEGER PRIMARY KEY,
    checked_at  TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    new_items   INTEGER,
    error       TEXT,
    CHECK ((new_items IS NULL) <> (error IS NULL))
);
CREATE INDEX source_check_by_source ON source_check (source, id);

CREATE TABLE sitemap_seen (
    site     TEXT NOT NULL,
    address  TEXT NOT NULL,
    lastmod  TEXT,
    seen_at  TEXT NOT NULL,
    PRIMARY KEY (site, address)
) WITHOUT ROWID;

CREATE TABLE run_log (
    id        INTEGER PRIMARY KEY,
    purpose   TEXT NOT NULL,
    from_day  TEXT,
    began     TEXT NOT NULL,
    ended     TEXT,
    report    TEXT
);
