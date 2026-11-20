# Volume probe, before any LLM call

Command: `company-news-radar probe-report --out results/probe.md`

- Run: 2026-11-19 18:37 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5

## Items

| Source | Items | Pass the filters | Oldest | Newest |
|---|---:|---:|---|---|
| bing_news | 3263 | 2970 | 2025-11-19 | 2026-11-18 |
| feed | 1148 | 83 | 2025-06-26 | 2026-11-19 |
| ted | 133 | 133 | 2025-11-20 | 2026-11-19 |
| bdns | 50 | 50 | 2025-11-19 | 2026-11-06 |
| borme_c | 30 | 30 | 2025-12-01 | 2026-11-06 |
| newsroom | 20 | 20 | 2026-04-30 | 2026-11-04 |

Newsrooms: 19 sitemaps read (their first read is the baseline: 21744 addresses stored, none announced); newsroom items by source: newsroom:rovi:0 10, newsroom:solaria:0 10

Press-search items per month of publication (how far back the engine serves): 2025-11 27, 2025-12 64, 2026-01 50, 2026-02 149, 2026-03 70, 2026-04 120, 2026-05 82, 2026-06 77, 2026-07 132, 2026-08 70, 2026-09 184, 2026-10 465, 2026-11 1773

## Dropped before the LLM

| Reason | Items |
|---|---:|
| names no watched company | 1063 |
| share-price page | 140 |
| not named in headline or snippet | 97 |
| foreign outlet | 34 |
| homonym phrase | 21 |
| market session report | 3 |

Stories for the LLM: **2809**; official records (no LLM, one story each): 213; items folded into an existing story as exact repeats: 264.

| Batch size | Requests for one pass |
|---:|---:|
| 10 | 281 |
| 15 | 188 |
| 20 | 141 |
| 25 | 113 |

Stories per company: indra 151, redeia 150, unicaja 143, solaria 139, caixabank 135, bbva 130, mapfre 123, bankinter 119, repsol 118, acciona 116, enagas 109, aena 109, iberdrola 107, iag 106, telefonica 102, merlin 102, inditex 102, santander 96, rovi 95, colonial 94, naturgy 93, sabadell 90, cellnex 84, amadeus 81, grifols 80, endesa 80, sacyr 79, acs 74, acerinox 66, logista 60, puig 48, fluidra 31

## Requests made

| Run | Started (UTC) | Since | New items by source | Requests | Retries | Refused (robots.txt, never-ask, brake) | Redirects | Hosts: rules / no file / not a robots file / unreachable |
|---|---|---|---|---:|---:|---:|---:|---|
| fetch weekly | 2026-11-19T02:55 | 2025-11-19 | bdns 50, bing_news 1865, borme_c 30, feed 1129, newsroom 20, ted 133 | 911 | 0 | 1 | 3 | 43 / 2 / 0 / 0 |
| fetch | 2026-11-19T03:16 | 2025-11-19 | bing_news 1398 | 663 | 0 | 0 | 0 | 1 / 0 / 0 / 0 |
| fetch | 2026-11-19T03:38 | 2025-11-19 | feed 19 | 46 | 0 | 0 | 3 | 19 / 1 / 0 / 0 |
| process | 2026-11-19T03:39 | - | - | 0 | 0 | 0 | 0 | 0 / 0 / 0 / 0 |

- failed in the run of 2026-11-19T02:55: feed:finanzas/portada: Disallowed: robots.txt of www.finanzas.com disallows https://www.finanzas.com/feed/
- never asked, by design: news.google.com
