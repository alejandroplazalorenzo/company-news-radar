# Sources

Checked on 19 Nov 2026 (Windows 11, Python 3.13.7, httpx 0.28.1, truststore 0.10.5) with
`company-news-radar sources` and during the backfill (`fetch --since 2025-11-19 --until
2026-11-19 --weekly`, then `fetch --only bing_news` and `fetch --only feed`). The client
reads the robots.txt of every host before asking it anything, and again for every host a
redirect leads to. The file is read as RFC 9309 says (`src/company_news_radar/robots.py`): the
group of this client's product token, else `*`; the longest matching rule decides, `*` and
`$` are understood, an allow wins a tie; a 4xx means no rules, a 429, a 5xx or a network
failure means nothing is asked. `results/probe.md` lists the requests of each run and the
verdict counts.

## Used

| Source | What it brings | Access | robots.txt |
|---|---|---|---|
| Bing News search RSS, one query per alias of each company | headline, snippet, outlet, publisher URL, date; about ten per page, paged back as far as the engine serves (a year, thinly: `results/probe.md`) | `bing.com/news/search?format=rss` | no rule for `/news/` (`/search` is disallowed and never asked) |
| 23 Spanish business-press feeds (`sources/catalogue.py`) | the latest entries of each section | RSS/Atom | allowed, or no file |
| Newsrooms of 21 of the 32 companies (`examples/newsrooms.json`) | new press-room pages after a baseline | sitemaps (19), feeds (2) | allowed |
| BORME Section C | legal notices (mergers, splits, capital, meetings) by registered name | BOE open-data API | allowed |
| BDNS | grants awarded, by tax id | public API | its robots.txt address answers an HTML page ("authorisation required") with no content type: no rule (the first fetch's summary still counts it among hosts with rules) |
| TED | contract awards above EU thresholds, by winner id | public API v3 | no file (404): no rule |

**The press search takes no operators.** On 19 Nov 2026, in four one-off requests that an AI
coding assistant sent while building the search (no repository command repeats them), Bing News RSS answered nothing to a query with `OR` (`"Banco Santander" OR "Grupo Santander"`: 0 items; `"Banco Santander"`: 10)
and almost nothing to a negative term (`Endesa -"Liga Endesa"`: 1; `Endesa`: 10). The first
fetch used production's query form and brought nothing for the 11 companies with more than
one alias; the search was run again with one plain query per alias
(`fetch --only bing_news`), and the homonym phrases of the watchlist are now applied to the
results (`process`, drop reason "homonym phrase").

## Left out, and why

| Source | Why |
|---|---|
| Google News search RSS (the production source) | `news.google.com/robots.txt` disallows `/rss/` for every generic user agent. The client never asks that host whatever its robots.txt says (`net.NEVER_ASK`), and the repository has no Google News extractor. Before its robots.txt was read, 15 exploratory queries were sent on 18 Nov 2026; none since (its robots.txt was read once more on 19 Nov to check the verdict with the new parser). |
| GDELT DOC API | tried on 18 Nov 2026 as a replacement: repeated HTTP 429 even at one request every 6 to 20 s, and almost no coverage of these companies in Spanish outlets. Not used. |
| Newsrooms of Iberdrola (sitemaps answer 403), Naturgy (404), Inditex and Amadeus (empty sitemaps), BBVA, ACS, Sabadell, Bankinter, Grifols and Sacyr (no newsroom section in the sitemap), Colonial (feed last updated in 2022) | nothing readable to follow |
| RTVE, Economía | robots.txt disallows the feed path |
| elEconomista | HTTP 403 to this client |
| Prensa Ibérica regional titles, El Periódico, Deia | HTTP 406 to this client |
| La Información, Vozpópuli, Público, Cinco Días · Mercados, La Razón, El Plural, Bolsamanía, The Objective, Energías Renovables | gone (410), not found (404), not a feed (370), 503, or no entries parsed |
| Certificate Transparency (crt.sh) | considered as an extra source; crt.sh answered 502 to its own robots.txt on 18 Nov 2026, which means no request. Not built. |

**Finanzas.com**: its robots.txt allows `/feed` and disallows `/feed/`. The first fetch of 19
Nov 2026 asked for the second address and the client refused it; the catalogue now has the
allowed one, read in the feeds-only fetch that followed.

Blocks are never worked around (no other user agent, no proxy).
