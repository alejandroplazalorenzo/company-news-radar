# company-news-radar

Watches the press, the companies' own newsrooms and official registers for news about a list
of companies, throws away what costs nothing to throw away, has an LLM classify the rest
under a hard daily quota, merges the same event told several times, and keeps only what
changes a company's business: deals, results, capital, management, sites, contracts, risks
and regulation. The output is a markdown digest without personal names. Nothing is sent
anywhere and nothing is scheduled: the radar is run by hand.

## Why

A company register publishes what was inscribed; the press tells a deal, a plant or a fine
weeks earlier, but it tells it ten times, in ten outlets, mixed with share-price chatter and
product launches. A person following a list of companies needs the one story that matters,
once, with the rest gone. An LLM can sort that out, but on a free tier it has a daily quota,
so everything that can be decided without it is decided first.

## How it works

```
 sources (each one isolated: a failure is recorded and the others go on)
   press search, one query per alias (Bing News RSS) | 23 business-press feeds | 21 newsrooms
   BORME Section C by registered name | BDNS grants by tax id | TED awards by winner id
   every host: robots.txt first (RFC 9309, also for each redirect); Google News never asked
        v
 normalise: UTC dates, canonical URLs, tolerant XML; a stable key per item
        v
 link entities: whole phrases on normalised text, watchlist aliases, homonym phrases, tax ids
        v
 deterministic filters (no LLM): outlet abroad | homonym phrase | names nobody | not named in
   headline or snippet | share-price page | market session report
        v
 standfirst of the page, only for what passed and has no snippet
        v
 exact repeats: same URL, or headline >= 0.85 similar within 4 days -> one story
   (register records never: one record, one story)
        v
 LLM classification (Gemini flash-lite, JSON schema, temperature 0, batches of 15, >= 4.5 s
   apart, 429 per minute waits, 429 per day stops, persistent cap of 300 requests a day)
   -> type, relevance, summary, confirmed companies, country, fact key
   official records skip it: the register says what and whose; grants and contracts below
   the floor are discarded
        v
 post-rules: abroad, high -> medium; irrelevant, abroad without a company, homonym -> out
        v
 repeats: proper-name signature | same fact key | long-lived keys (yearly results, takeover
   bids) | topic | LLM judge for doubtful pairs | manual "no" verdicts win forever
        v
 levels: discarded / visible / front page (deals and sites, high or medium, in Spain) / alert
        v
 SQLite (data/radar.sqlite) -> digest (markdown, no names; --no-details: counts only)
```

Modules in `src/company_news_radar/`: `net` (polite client) and `robots` (RFC 9309),
`sources/` (`press`: feeds, press search and article pages; `newsrooms`; `official`;
`catalogue`), `textutil`, `watchlist`, `entities`, `filters`, `extract`, `process`, `store`
(+ `sql/`), `quota`, `gemini`, `prompts`, `classify`, `merge`, `privacy`, `digest`, `checks`,
`coverage`, `judge`, `ollama`, `tuning`, `experiments`, `cli`. Runtime dependencies: `httpx`, `lxml`,
`truststore` (and `tzdata` on Windows).

## Decisions from my production system (no internal figures)

This is a rebuild on public data of the news radar I built at work. These design decisions
come from that system, and every figure below was measured here. Five thresholds were
re-derived on this repository's data: the minimum grant (production's 100,000 EUR holds), the
minimum public contract (raised to 1 M EUR), the country codes of outlets abroad, the share of
texts at which calibration drops a derived key (0.003 to 0.02) and the headline similarity of
exact repeats (production's 0.85 holds). The four-day window of exact repeats was measured but
not changed (the data favours one or two days; changing it means classifying again). Every
other value is production's, unmeasured here (the calibration lower-case count, floor and
five-letter minimum, the merge windows and signature cut, the judge batch, the newsroom
redesign guard, the LLM batching and pacing, and the HTTP client's time-outs, retries and
brake), except a few client and quota settings chosen for this repository. The lists, with n
and commands, are in [docs/thresholds.md](docs/thresholds.md); `config.py` marks each value.

| Decision | Why |
|---|---|
| **Companies only: people are never searched by name.** | The press names people; the radar has no reason to follow them. |
| **A search query per watched company**, its aliases joined by OR and **homonym phrases as negative terms**; what the query brings counts for that company even if the name is only in the body, and the classifier confirms. (Both changed here, see the next table.) | One query per company is cheap; a homonym phrase removes a family of false hits at once. |
| **Newsrooms read through their sitemaps with a baseline**: the first read stores every address and announces nothing; `lastmod` never decides; section pages, galleries and translations of a known page are not news; many new addresses at once is a redesign; a filter that matches nothing is a failure. Feeds have no baseline. | What a company publishes itself may never reach the press; without a baseline the first run swallows the archive. |
| **Official records matched exactly**: BORME Section C by registered name (roles in brackets cut off), BDNS by tax id, TED by winner id with and without the country prefix. They **skip the LLM**. | The record says what and whose. Here, one-to-one, register stories came a median of 13.5 days before the Registro inscribed the act (E1). |
| **A daily pass and a weekly one**: BDNS and TED only in the weekly pass. | They change little and are slow. |
| **Each item has a stable key** (its canonical URL, or register and record id): running again duplicates nothing, and everything a source brought stays in the store, discarded included. | Reruns are safe; nothing is classified twice. |
| **Entity linking by whole phrases** on normalised text, never substrings; a key has to tell a company apart (not only generic words; one word needs five letters); aliases written explicitly in the watchlist, not derived from any data, bypass that; **calibration against the press** drops derived keys printed as ordinary lower-case words or matching too many texts. | Cheap and conservative: a homonym costs one classification, a missed story is lost. |
| **Deterministic filters before any LLM call**: outlets abroad by domain, floors for grants and contracts, and anything that names no watched company. | They cost nothing, and the LLM has a daily quota. |
| **The page's standfirst is fetched only for what passed the filters.** | Sitemaps give an address and nothing else; fetching every page would be slow and impolite. |
| **Exact repeats merged before the LLM**: same URL, or headlines at least 85% similar within four days. | The same agency piece runs in many outlets; it should cost one classification. |
| **One LLM (Gemini flash-lite), JSON schema, temperature 0, batches of 15, at least 4.5 s between calls**; a per-minute 429 waits what Gemini asks, a per-day 429 stops at once and says which quota; 500/503/timeouts wait 15, 30, 60 s; what is not classified stays pending. | The free tier has per-minute and per-day limits; a backfill is hundreds of calls. |
| The classifier returns **type, relevance, summary, confirmed companies, country and a fact key**, and sees only public text. | `country` keeps facts abroad off the front page; the fact key merges repeats told with other words. |
| **Prompt versions written from what the previous version got wrong**, run again on everything the LLM read by default; only on what the previous version left visible when the new one is only stricter. | Each version answers a measured failure; a stricter one cannot rescue what was discarded. |
| **Post-rules**: abroad, high becomes medium; irrelevant, abroad without a watched company, and named-but-not-confirmed (homonym) are discarded. | Seen, but never on the front page; homonyms out. |
| **Repeats after classification**: proper-name signature, same fact key (also across types), long-lived keys (a company's yearly results, for a year), topic for some types, never two different companies (also through chains), distances between story spans; the heaviest story stays and takes the others' items and companies. | The same event told by ten outlets over a week must appear once. |
| **An LLM judge for doubtful pairs** (two stories of one company within a day): its "yes" kept for good, its "no" asked again when the judge prompt changes, and **manual "no" verdicts win forever**, over the judge and the rules. | Rules miss paraphrases; a person's decision must not be undone by a later run. |
| **Visibility levels**: discarded / visible / front page / alert. The front page is only structural change (deals and sites), high or medium, in Spain. Alerts: deals, sites, results and risks of a watched company, and high-relevance regulation and risk, even with no watched company. | What is seen is not what interrupts. |
| **Source health**: a source that fails is not a source that is silent; each source runs isolated. | A failure needs fixing and an empty answer does not; `stats` lists the two apart. |
| **Coverage test against the Companies Register**: the company acts the Registro later published are the ground truth; the radar is scored on whether it saw them and how many days earlier. | A ground truth that is public, dated and not chosen by the radar. |
| The **local model was dropped** after measuring it; the measurement is repeated here (E2). | A rule-heavy prompt needs the rules to reach the model. |

Decisions of this rebuild, not of the production system:

| Decision | Why |
|---|---|
| **robots.txt for every host and every redirect hop**, read with this repository's own RFC 9309 parser (longest match, `*` and `$`, allow wins a tie; 4xx no rules, 5xx nothing asked). | A public tool has to respect it, and `urllib.robotparser` is not RFC 9309 (first match, no wildcards). |
| **Google News is never asked**: a hard rule in the HTTP client, whatever its robots.txt says (it disallows `/rss/`). There is no Google News extractor. **Bing News RSS** is the press search. | Its robots.txt disallows `/rss/` for generic agents, and the exclusion should not depend on that file staying as it is. |
| **One plain query per alias**: Bing's RSS answers nothing to `OR` and almost nothing to negative terms (measured, [docs/sources.md](docs/sources.md)), so the homonym phrases filter the results. | The same idea, applied after the engine instead of in it. |
| **No undocumented endpoints**: production turns Google links into publishers' URLs through an internal call; Bing's RSS carries the publisher URL as a plain parameter. | Only documented, public interfaces. |
| Two **filters for listed companies**: a search result that names no watched company in headline or snippet is dropped, and so are share-price pages and market-session reports. | Production keeps every Google result because Google gives no snippet. Bing gives one, and a result that names the company in neither headline nor snippet matched it only in the body: 97 results, 26 of them with a stock-market word in the headline (`results/tuning.md`). |
| **No sector-wide queries or trade-press feeds**: production also ran them; the 32 groups of the watchlist span banking, energy, construction, retail, pharma, telecoms, real estate and more. | Nothing to rebuild them on. |
| **Minimum contract raised to 1 M EUR** (grant minimum unchanged); **foreign outlets** by the country codes seen in the data. | Re-derived from the watchlist's records ([docs/thresholds.md](docs/thresholds.md)). |
| **One story per register record**: records are never folded, not even when they share an address. | Several grants of one call share the call's page; folding them hid small grants inside large ones and mixed companies. |
| **Doubtful pairs need a headline word in common** (other than the companies' names) even within a day. | A listed group has dozens of stories a day: "same company, same day" alone floods the judge. |
| **A takeover bid** (keyed by the companies in it) **replaces production's other long-lived key** (a brand entering a market); yearly results are kept from production. | What the press follows for months for these companies. |
| **`country` and the fact key in the schema from v1** (production added them in its fourth version). | The Spain rule and the merging need them; the versions differ in rules. |
| **A persistent daily cap of 300 requests**, counted on disk before each HTTP attempt (every retry counts) under a file lock; the quota day starts at 09:00 Europe/Madrid; the key travels in a header. **Two failed batches in a row stop a run.** | The free-tier key is shared with another system; every attempt spends quota. |
| **E2's sample is drawn from stories not used to write the prompt**: v2 was written from v1's answers on a random development subset, and E2 samples the rest. | Otherwise the agreement of the prompt's own model would be inflated. |
| **E1 adds strict variants**: the story has to be of a compatible type; one-to-one, each story counts for one act; and a row with only the acts whose whole window lies inside the period. | Listed groups are in the press every day: "any story within six months" is near 100% by construction. |
| **No messaging, no app**: a markdown digest; `--no-details` gives counts only. | A portfolio project publishes nothing. |

## Re-measured here on public data

All figures come from runs on 19 Nov 2026 (Windows 11, Python 3.13.7, httpx 0.28.1,
lxml 6.1.3; Gemini `gemini-flash-lite-latest`; Ollama 0.40.16 with `qwen3:8b`). The watchlist
is `examples/watchlist.csv`: the parent companies of 32 Spanish listed groups (the same list as
[borme-radar](https://github.com/alejandroplazalorenzo/borme-radar)), 31 of them with the tax
id checked on the CNMV (Puig's is not in that lookup and is left empty). Each figure has its
file in `results/` or `docs/` with the command, n, date and versions.

### Sources and the deterministic filters (`results/probe.md`)

Fetched on 19 Nov 2026 asking for one year (19 Nov 2025 to 19 Nov 2026) from every source.

| Source | Items | Pass the filters |
|---|---:|---:|
| Bing News search, one query per alias, paged back as far as it serves | 3,263 | 2,970 |
| 23 business-press feeds (what they still list, back to June 2025) | 1,148 | 83 |
| Newsrooms: 19 sitemaps (first read = baseline, 21,744 addresses, nothing announced) and 2 feeds | 20 | 20 |
| BORME Section C / BDNS / TED (12 months) | 30 / 50 / 133 | all |

The press search serves a year, but thinly: 1,773 of its items are from the first 18 days of
November 2026, 465 from October, and between 27 and 184 a month before that. Dropped before
any LLM call: 1,063 items that name no watched company, 140 share-price pages, 97 search
results that do not name the company in headline or snippet, 34 from outlets abroad, 21 with
a homonym phrase, 3 market-session reports; 264 more were exact repeats folded into a story.
**2,809 stories went to the LLM** (188 requests at 15 per request) and 213 register records
skipped it, one story each. The three fetches made 1,620 requests (911 + 663 + 46), with no
retry, one refusal (the `/feed/` path that finanzas.com's robots.txt disallows) and six
redirects, each checked against its target's robots.txt.

### Classification and quota (`results/quota.md`)

| Pass | Requests | OK | 503 (overloaded) | Items per OK request | Seconds per request (median) | Prompt / output tokens (mean) |
|---|---:|---:|---:|---:|---:|---:|
| v1, all 2,809 stories | 198 | 188 | 10 | 14.9 | 3.50 | 2,697 / 1,359 |
| v2, the 2,119 v1 left visible | 154 | 142 | 12 | 14.9 | 6.49 | 3,251 / 1,345 |
| E2, Gemini side, batches of 15 | 12 | 10 | 2 | 15.0 | 5.22 | 3,277 / 1,362 |
| E2, Gemini side, batches of 25 | 6 | 6 | 0 | 25.0 | 6.94 | 4,453 / 2,268 |
| repeats judge | 18 | 18 | 0 | 19.6 pairs | 4.34 | 5,487 / 632 |

388 requests in one quota day, 19 Nov 2026 (the call log and the persistent counter agree),
24 of them 503 answers that were retried, no 429. v1 ran under the default cap of 300; the
rest under `--daily-cap 480`, because the other system that shares the key was not running
that day, so everything fitted in one quota day. Every retry counts, and two failed batches in
a row would have stopped a run; none did.

### Prompt versions (E3, `results/e3_prompt_versions.md`)

| Version | Read | Visible | Front page (before merging) |
|---|---:|---:|---:|
| v1, minimal | 2,809 | 2,119 | 249 |
| v2, written from v1's mistakes on a development subset | 2,119 | 1,758 | 176 |

v2 ([docs/prompt_versions.md](docs/prompt_versions.md)) discarded 361 of the 2,119 stories v1
had left visible: it sent to irrelevant 88 image, 73 capital, 50 results, 36 risk, 32
footprint, 28 corporate and 17 deal stories of v1 (share-price pieces, dividend calendars,
opinions, consumer offers), and moved 35 footprint stories to corporate (investment plans and
progress of projects already announced). v2 was run only on the 2,119 stories v1 left
visible, as the rule above does for a version that is only stricter, so what it would do with
the 690 that v1 hid is not measured. It is not simply
stricter: its relevance levels move both ways, and 26 stories entered the front page, 31
gained an alert and 273 of those both versions kept visible rose in relevance (the counts,
both ways, are in `results/e3_prompt_versions.md`). Per month the front page follows the
depth of the press search,
not the news flow (v2: 52 in the first 18 days of November 2026, between 2 and 29 a month
before), so the monthly and weekly columns are not a trend.

### Repeats (E4, `results/e4_merges.md`)

698 stories were merged into others: 394 by headline signature, 164 by fact key, 8 by
long-lived keys, 40 by topic and 92 by the judge (352 doubtful pairs judged in 18 requests: 106
the same event, 246 not). After merging, **1,197 visible stories** (press search 1,037, feeds
17, newsrooms 6, BORME-C 30, BDNS 29, TED 78), **124 on the front page**, 423 alerts; the
digest of the year without details is
[examples/digest_2025-11-19_2026-11-19_no-details.md](examples/digest_2025-11-19_2026-11-19_no-details.md).
Among those stories, production's same-day rule (any two stories of one company within a
day) would still send **1,139 pairs** to the judge; the rule of this rebuild sends 201.

A blind sample of 80 pairs, 40 merged and 40 the judge said were not the same event (both
drawn at random with a seed), was shuffled and labelled without the decision by a stronger
model, Claude Opus 5.5 (Anthropic), from each item's headline, snippet, source and date and
the watched companies the linker named in it ([docs/label_guide.md](docs/label_guide.md)).
This is agreement with that labeller, not accuracy. It called **38 of the 40 merges** the
same event (signature 21 of 21, judge 8 of 8, fact key 8 of 9, topic 1 of 2) and **7 of the
40 pairs the judge kept apart** the same event too. In these samples, then, 7 of 40 "no"
pairs were one event and 2 of 40 merges were not.

### Local model against the API (E2, `results/e2_local_vs_api.md`, `results/e2_batch25_context.md`)

The same 150 stories (drawn outside the development subset v2 was written from), prompt v2,
10 batches of 15:

| Run | Visible | Front page | Rule violations | Prompt / output tokens (median) | Seconds per batch (median) | Where it ran |
|---|---:|---:|---:|---:|---:|---|
| Gemini flash-lite | 101 | 8 | 3 | 3,281 / 1,372 | 5.22 | API |
| qwen3:8b, num_ctx 4,096 | 126 | 15 | 5 | 3,438 / 1,140 | 22.05 | 100% GPU, 6.3 GB |
| qwen3:8b, num_ctx 8,192 | 128 | 16 | 5 | 3,438 / 1,137 | 50.91 | 22% CPU / 78% GPU, 8.1 GB |

(GPU: an 8 GB RTX 3070 Laptop. Rule violations: Gemini's 3 are all summaries the name
scrubber flags, which can be false alarms; qwen3:8b's 5 are 2 flagged summaries, 2 malformed
fact keys and 1 stock-market headline kept, in both contexts.) Gemini and qwen3:8b agree on the type of 57-58% of
the items (kappa 0.50-0.52) and on visibility for 78%; the local model lets about a quarter
more through and puts 15 or 16 stories on the front page against 8. With batches of 15 the
3,438-token prompt fits in 4,096, but prompt and answer together (a median of 1,140 more) do
not: Ollama shifts the context while it answers. Here that cost little: the two contexts give
almost the same answers (86.7% same type, 97.3% same visibility).

With **batches of 25** (`results/e2_batch25_context.md`) the prompt is about 4,700 tokens and
no longer fits: at 4,096 Ollama evaluated only **2,050** of them (median; 4,716 at 8,192),
that is, it cut the prompt. Only **90 of 150** items came back, none on the front page, with
129 rule violations, and their types agree with the 8,192 run on 14.4% (Gemini, which reads
the whole prompt, answered all 150). At 8,192 the model no longer fits on the GPU (22% CPU)
and a batch takes 88 s instead of 38 s. That is production's finding: on 8 GB only a 4,096
context stays on the GPU, and past it the model loses the instructions.

The same 150 stories were labelled blind by a stronger model, Claude Opus 5.5 (Anthropic),
from the headline, snippet, source and date and the watched companies the linker named
([docs/label_guide.md](docs/label_guide.md)).
Agreement with that labeller, not accuracy:

| Run (batches of 15) | Same type | Same visible | Same front page | Front page precision / recall |
|---|---:|---:|---:|---:|
| Gemini flash-lite | 73.3% | 83.3% | 94.7% | 62.5% / 50.0% |
| qwen3:8b, num_ctx 4,096 | 60.0% | 80.0% | 91.3% | 40.0% / 60.0% |
| qwen3:8b, num_ctx 8,192 | 60.0% | 81.3% | 90.7% | 37.5% / 60.0% |

The labeller put 10 stories on the front page. Gemini agrees with it on the type 13 points
more often than the local model. On the front page Gemini is the more precise (5 of its 8),
and the local model finds one more (6 of the 10) at the price of 15 or 16 picks. With batches
of 25 at 4,096, qwen3:8b agrees with the labeller on the type of 8% of the 150 items (the 60
it did not answer count as disagreements), against 74% for Gemini
(`results/e2_batch25_context.md`).

### Coverage against the Companies Register (E1, `results/e1_coverage.md`)

The ground truth is the company-level acts (capital, bonds, mergers, name, address, purpose,
dissolution) that the Registro published in BORME Section A for the 32 companies, read
read-only from the [borme-radar](https://github.com/alejandroplazalorenzo/borme-radar)
database. Officer acts are left out, because this radar never searches people, and so are
by-law amendments, errata, unexecuted capital increases, changes of powers or website and
"other" acts (counted in the results file). An act counts as seen if a story of the same
company appeared from 180 days before to 30 days after it (production's metric). Three
stricter readings were added here: the story has to be of a compatible type; one-to-one, each
story counts for one act only (greedy, the closest in date: a bound, not an optimal matching);
and rows with only the acts whose whole 210-day window lies inside the period.

| Stories from | Acts | Seen (any story) | Compatible type | One-to-one | Median days ahead (one-to-one) |
|---|---:|---:|---:|---:|---:|
| Press, 19 Nov 2025 to 18 Nov 2026, all acts | 67 | 61 | 20 | 17 | 3 |
| Press, acts with the whole window inside | 29 | 29 | 13 | 11 | -7 |
| Official records, 19 Nov 2025 to 19 Nov 2026, all acts | 67 | 59 | 48 | 22 | 13.5 |
| Official records, whole window inside | 29 | 27 | 21 | 15 | 17 |

The acts are mostly capital-market acts of large groups (30 bond issues, 23 capital
reductions, 9 capital increases). The loose metric is near 100% by construction for groups
that are in the press every week. A story of a compatible type covers 30% of the acts (45% of
the whole-window ones), and one-to-one 25% (38%), a few days before or after the act (median 3
days ahead, -7 for the whole-window ones): the press reports these acts around the time they
are inscribed; it does not anticipate them by months. The official records anticipate them by
construction: a Section C notice announces a capital reduction or a merger before it is
inscribed, so one-to-one they cover a third of the acts (half of the whole-window ones)
about two weeks earlier (median 13.5 days, 17 for the whole-window ones); 5 of the 59 acts "seen" under the loose metric had only
a grant or a contract in their window, which says nothing about the act.

## Limitations and next steps

- **Press depth**: the press search serves a year, but most of it is from the last weeks
  (`results/probe.md`); older months are thin by construction.
- **Two prompt versions** (production went to four): v3 would be written the same way, from
  what v2 still gets wrong on a new development subset ([docs/prompt_versions.md](docs/prompt_versions.md)).
- **v2 did not read the 690 stories v1 hid.** It was run only on what v1 left visible, and
  its relevance levels move both ways (it raised 273 stories), so some of those 690 might come
  back under v2. That is not measured.
- **Front page in Spain only** (production rule): for multinationals it leaves out deals and
  sites abroad, which stay visible with medium relevance.
- **Short names are not keys**: a search result that only says "Santander", "ACS" or "Merlin"
  is dropped when the aliases are longer ("Banco Santander", "Grupo ACS", "Merlin
  Properties"); a one-word key needs five letters and must not be a place.
- 11 of the 32 companies have no newsroom the radar can read, and BDNS and TED only see the
  parent companies' tax ids, not their subsidiaries'.
- E2 and E4 are scored against blind reference labels written by another model (Claude Opus
  5.5), not against the truth: a bias it shares with the models scored would not show.
- v2's rules, the label guide and the reference labels all come from the same model family
  (Claude, through the AI coding assistant used to build this repository), so Gemini v2's
  agreement with the labels may be higher than an independent annotator's would be.
- The name scrubber is a heuristic; that is why shared digests carry no free text.
- **Exact repeats can join templated headlines**: 11 of the 264 folds join two companies'
  results announcements, research pages or dividend calendars (`results/tuning.md`). Requiring
  a company in common, and a one- or two-day window, would avoid them; both change the stored
  stories, so they wait for a new classification run.

## How to run

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # Windows; .venv/bin/python elsewhere
cp .env.example .env                                 # then put your Gemini key in .env

company-news-radar sources                           # check feeds and robots.txt
company-news-radar fetch --since 2025-11-19 --until 2026-11-19 --weekly   # a year, BDNS and TED too
company-news-radar process                           # link, filter, complete, exact repeats
company-news-radar probe-report                      # what the LLM would cost (no call)
company-news-radar classify --prompt v1              # under the daily cap; resumable
company-news-radar dev-split --prompt v1 --share 0.3 --seed 7   # what a new prompt is written from
company-news-radar dev-report                        # counts of that subset (results/dev_subset.md)
company-news-radar e2-sample                         # E2: 150 stories outside that subset
company-news-radar reclassify --prompt v2 --only-visible       # v2 on what v1 left visible
company-news-radar merge --judge                     # repeats: rules, judge, manual verdicts
company-news-radar digest --since 2025-11-19 --until 2026-11-19 --out reports/digest.md
company-news-radar digest --since 2025-11-19 --until 2026-11-19 --no-details \
    --out examples/digest_2025-11-19_2026-11-19_no-details.md
company-news-radar stats                             # counts, failing and silent sources
company-news-radar quota                             # requests used and left today
```

The daily pass is `fetch` without `--weekly` (BDNS and TED only in the weekly one) and
`--since` defaults to the day before the last fetch. `--daily-cap N` (before the command)
raises the cap of 300 for a day, never above the free tier's 500; the runs above used 480
after v1. On 19 Nov 2026 the first fetch was followed by `fetch --only bing_news` and
`fetch --only feed` ([docs/sources.md](docs/sources.md) says why). Experiments: `e1-coverage --borme-db
<borme-radar sqlite>`, `e2-sample`, `e2-run --model gemini|qwen3:8b --num-ctx N --name X`,
`e2-report`, `e3-report`, `e4-report --queue`, `quota-report`, and `tuning-report` (thresholds
checked on the stored data, no network). The watchlist is
`examples/watchlist.csv` (`id`, `group`, `name`, `tax_id`, `tax_id_source`,
`registered_names`, `aliases`, `exclude`, `website`); newsroom entries are in
`examples/newsrooms.json`. Everything is written under `data/` (gitignored): the SQLite store,
the quota counter, the call log, the judge queues and the logs.

## Privacy

The radar searches companies, never people. Headlines and snippets can name people: they stay
in the local store (`data/`, gitignored). The digest prints no headline and no link (links
usually carry the headline), and the classifier's summary, which is told to name companies and
job titles and never people, passes through a name scrubber; `--no-details` prints counts
only. Results files contain counts, company ids and dates only. The test fixtures are
synthetic: the companies are real listed groups, every event, place and outlet in them is
invented, and their domains end in `.test`.

## Tests

```bash
pytest            # 64 passed on 19 Nov 2026 (Windows 11, Python 3.13.7 and 3.11.16)
ruff check . && ruff format --check .
```

The suite runs offline (`tests/conftest.py` makes any socket connection fail): robots.txt as
RFC 9309 reads it, the client (never-ask hosts, redirect hops, retries, the brake), source
parsers on synthetic fixtures, the fetch plan, the newsroom baseline and its guards, entity
linking and calibration, the deterministic filters, failing versus silent sources, exact repeats (never for register
records), the quota day and the cap shared across processes, the Gemini client (header key,
429 per minute and per day) on a mock transport, the post-rules, reclassification, merging
(fact keys, signatures, never two companies, manual verdicts, the judge), the digest without
names, E1 on a database with borme-radar's schema opened read-only, the rule checks, the
blind queues, the replay behind `tuning-report` and the CLI. GitHub Actions runs ruff and pytest on Python 3.11 and 3.12.

## Data sources and licences

- BORME: Agencia Estatal Boletín Oficial del Estado, open-data API
  (https://www.boe.es/datosabiertos/). **Basado en datos de la Agencia Estatal Boletín Oficial
  del Estado** (https://www.boe.es). Derived, unofficial output.
- BDNS (Sistema Nacional de Publicidad de Subvenciones y Ayudas Públicas): public API; reuse
  terms at https://www.infosubvenciones.es/bdnstrans/GE/es/avisolegal.
- TED (Tenders Electronic Daily, Publications Office of the EU): search API v3.
- Press: Bing News search RSS and the feeds listed in `src/company_news_radar/sources/catalogue.py`;
  only headlines, snippets and links are read, and nothing is redistributed.
- Tax ids: the CNMV entity page of each company, checked on 18 Nov 2026.
- Code: MIT licence, see [LICENSE](LICENSE).

## About

Rebuild on public data of the news radar I built at work and run on demand. No proprietary
code or data. Built with AI-assisted development; the design decisions come from my
production system and every figure here was re-measured on public data.

Alejandro Plaza Lorenzo - alejandroplaza.dev@gmail.com
