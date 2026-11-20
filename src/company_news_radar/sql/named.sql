-- Statements the store runs by name. Each block starts with "-- name: <name>"; the
-- parameters are named, and :now is filled in by the store.

-- name: capture.add
INSERT OR IGNORE INTO capture
    (ident, origin, channel, subject, headline, url, published, publisher, publisher_host,
     standfirst, record_type, record_level, amount_eur, tax_ids, captured_at)
VALUES
    (:ident, :origin, :channel, :subject, :headline, :url, :published, :publisher,
     :publisher_host, :standfirst, :record_type, :record_level, :amount_eur, :tax_ids, :now)

-- name: story.open
INSERT INTO story
    (origin, headline, url, published, publisher, standfirst, record_type, record_level,
     opened_at)
SELECT origin, headline, url, published, publisher, standfirst, record_type, record_level, :now
FROM capture WHERE id = :capture

-- name: party.add
INSERT OR IGNORE INTO party (story_id, company, how, evidence, tax_id)
VALUES (:story, :company, :how, :evidence, :tax_id)

-- name: party.confirm
UPDATE party
SET confirmed = id IN (SELECT value FROM json_each(:chosen))
WHERE story_id = :story

-- name: verdict.put
INSERT OR REPLACE INTO verdict
    (story_id, kind, level, shown, why_hidden, on_front, alerts, country, fact_key, gist,
     decided_by, decided_at)
VALUES
    (:story, :kind, :level, :shown, :why_hidden, :on_front, :alerts, :country, :fact_key,
     :gist, :decided_by, :now)

-- name: answer.add
INSERT INTO answer
    (version, model, story_id, kind, level, gist, country, fact_key, parties, shown,
     why_hidden, on_front, alerts, given_at)
VALUES
    (:version, :model, :story, :kind, :level, :gist, :country, :fact_key, :parties, :shown,
     :why_hidden, :on_front, :alerts, :now)

-- name: decision.verdict
INSERT INTO decision (act, first_id, second_id, same, author, made_at)
VALUES ('verdict', min(:a, :b), max(:a, :b), :same, :author, :now)
ON CONFLICT (first_id, second_id) WHERE act = 'verdict'
DO UPDATE SET same = :same, author = :author, made_at = :now
WHERE decision.author NOT LIKE 'manual%' OR :author LIKE 'manual%'

-- name: decision.merge
INSERT INTO decision (act, first_id, second_id, author, kept_id, made_at)
VALUES ('merge', :a, :b, :rule, :kept, :now)

-- name: source.checked
INSERT INTO source_check (checked_at, source, kind, new_items, error)
VALUES (:now, :source, :kind, :new_items, :error)

-- name: source.failing
SELECT c.source, c.kind, c.checked_at, c.error
FROM source_check c
WHERE c.error IS NOT NULL
  AND c.id = (SELECT max(id) FROM source_check WHERE source = c.source)
ORDER BY c.source

-- name: source.silent
SELECT source, kind
FROM (SELECT source, kind, new_items,
             row_number() OVER (PARTITION BY source ORDER BY id DESC) AS back
      FROM source_check)
WHERE back <= :runs
GROUP BY source
HAVING count(*) = :runs AND sum(new_items = 0) = :runs
ORDER BY source

-- name: sitemap.add
INSERT OR IGNORE INTO sitemap_seen (site, address, lastmod, seen_at)
VALUES (:site, :address, :lastmod, :now)

-- name: run.start
INSERT INTO run_log (purpose, from_day, began) VALUES (:purpose, :from_day, :now)

-- name: run.finish
UPDATE run_log SET ended = :now, report = :report WHERE id = :run

-- name: story.amount
SELECT amount_eur FROM capture
WHERE story_id = :story AND amount_eur IS NOT NULL
ORDER BY id LIMIT 1

-- name: run.last_fetch
SELECT max(began) FROM run_log WHERE purpose LIKE 'fetch%' AND ended IS NOT NULL
