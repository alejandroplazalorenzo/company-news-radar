# Thresholds

Every tunable value lives in `src/company_news_radar/config.py`, marked `[re-derived]` (measured
on this repository's data), `[production]` (copied from the system this repository rebuilds,
not measured here) or `[here]` (chosen for this repository).

Source of the figures: `company-news-radar tuning-report --out results/tuning.md`, run on 19 Nov
2026 (Windows 11, Python 3.13.7) over the local store as it stood after the fetch, process,
classify and merge runs of that day (`fetch --since 2025-11-19 --until 2026-11-19 --weekly`).
The command reads the store only: no network, no LLM. n is given with each figure.

## Re-derived

| Value | Production | Here | n | Basis |
|---|---|---|---|---|
| Minimum grant | 100,000 EUR | 100,000 EUR | 50 BDNS grants | see below |
| Minimum public contract | 500,000 EUR | 1,000,000 EUR | 133 TED awards, 114 with an amount | see below |
| Outlets abroad | by country code | `ar bo cl co mx pa pe py uy` | 3,263 press-search items | see below |
| Calibration: largest share of texts a derived one-word key may match | 0.003 | 0.02 | 1,148 feed texts | see below |
| Headline similarity for exact repeats | 0.85 | 0.85 | 3,073 kept press captures | see below |

**Minimum grant.** 50 grants to 12 of the 31 tax ids queried: p10 6,000, p25 12,498, median
134,860, p75 1.27 M, p90 3.75 M EUR (`statistics.quantiles(..., n=100, method="inclusive")` and
`statistics.median`); 21 are below 100,000 EUR. On reading their titles (an AI coding
assistant), the small ones are hiring and training incentives, patent fees, small fleet or
self-consumption programmes and regional farm-support lines paid through the banks; the large
ones are research programmes, energy projects and more of the farm-support lines. The
production cut separates the two groups here too, so it is kept.

**Minimum public contract.** 133 awards to 9 tax ids, 114 with an amount (an award without
one is never discarded): p10 116,022, p25 357,229, median 1.15 M, p75 5.14 M, p90 11.8 M EUR;
55 are below 1 M EUR. On the same kind of reading, the awards between 300,000 EUR and 1 M EUR
are bank payment and treasury services, renting won through the banks' leasing arms, single
lots of software maintenance and single medicine lots: routine for groups with revenue in the
billions, so the cut is raised to 1 M EUR.

**Outlets abroad.** Top-level domains of the publishers of the 3,263 press-search items:
`.com` 2,388, `.es` 781, `.cat` 20, `.uy` 11, `.de` 8, `.mx` 7, `.org` 7, `.eus` 6, `.net` 6,
`.news` 5, `.cl` 5, `.it` 4, `.ar` 3, `.pe`, `.co` and `.bo` 2 each, `.pa`, `.tv`, `.py`,
`.jp`, `.io` and `.info` 1 each. The filter drops the Spanish-speaking American codes seen;
other countries are kept, and the classifier's `country` keeps their facts off the front page.

**Calibration share.** The 28 one-word company names of the watchlist (three letters or more,
not generic) appear in at most 0.87% of the feed texts (REPSOL, 10 texts). With production's
0.003 the limit here would be the floor of 5 texts, and six real company names match more
than that (REPSOL 10, ENAGAS 7, UNICAJA 7, BBVA, INDRA and MAPFRE 6): as derived keys, the
calibration would drop them. They are aliases here, so it does not. The new share is twice the largest observed one, rounded up: 0.02 (about 23 texts
at this corpus size). Nothing stored changes: the only derived one-word key of this watchlist,
COLONIAL, matches 2 texts and is kept under both values.

**Headline similarity.** Replaying the fold over the 3,073 kept press captures gives the
same 264 folds as the stored data. A fold is counted as wrong when the two captures name
disjoint sets of companies. At 0.85 (four days) 11 of the 264 folds are wrong; on reading
them (an AI coding assistant), all 11 are templated headlines where only the company name
changes (results announcements, profit headlines, dividend calendars, research pages,
stock-screen pieces) or a generic page title.
Lowering the cut to 0.80 adds 65 folds, 7 of them wrong (11%), and 40 of the 65 pairs ended
in one story anyway after the merge step. Raising it to 0.90 removes 50 folds, 7 wrong and 43
right. Neither direction is better on this data, so the cut stays at 0.85. A cut cannot tell
templated headlines apart; requiring a company in common would (a next step: it changes the
stored stories, so it needs a new classification run).

## Measured, not changed

**Day window for exact repeats: 4 days, production's.** A one-day window keeps 250 of the
264 current folds; 4 of the 14 it drops are wrong (29%), against 7 of the 250 it keeps (3%).
Among all pairs at 0.85 or more, those 2 to 4 days apart join different companies in 8 of 25
cases, and none of the 26 pairs 5 to 7 days apart ended in one story. A one-day window would
avoid those 4 wrong folds and lose 10 right ones; the data favours one or two days. It is not
applied, because every result in `results/` was produced with four days and a new fold means
classifying the stories again.

**Calibration lower-case count (2) and floor (5): production's.** None of the 28 names is
written in lower case in the corpus, short names included (ACS, AENA, BBVA, IAG, PUIG, ROVI),
so any lower-case count of 1 or more drops the same keys here (none): the data neither
supports nor contradicts the value. The floor only matters below 250 texts at the new share.

**Five letters for a one-word key: production's.** The length does change the keys. With five
letters (or six) the only derived one-word key is COLONIAL; a four-letter minimum adds PUIG,
and a three-letter one adds ACS as well. The corpus would not drop either (PUIG matches 1
text, ACS 2, neither in lower case), so both would reach the linker. Whether that links more
of the right stories or more of the wrong ones is not measured here (`results/tuning.md`,
table of minimum lengths).

## Kept from production, not measured here

| Value | Setting | Where it is measured, if anywhere |
|---|---|---|
| Signature merge | 2 shared names or figures, 3/4 of the smaller set, 3 days | E4 scores the merges against blind labels |
| Same fact key | 30 days | E4 |
| Long-lived keys | 365 days | E4 |
| Topic merge | 4 days | E4 |
| Doubtful pairs for the judge | same company within 1 day | E4 counts the pairs it would send |
| Judge batch | 20 pairs | |
| Newsroom redesign | more than 40 unseen addresses and more than a third of the known ones | |
| LLM | `gemini-flash-lite-latest`, batches of 15, 4.5 s apart, 4 attempts, waits of 15, 30 and 60 s, a 120 s request time-out | `results/quota.md`; E2 also runs batches of 25 |
| Per-minute 429 from Gemini | wait what it asks, at most 120 s, plus 1 s | |
| HTTP client | 1 s between requests to a host, 30 s time-out (8 s and 0.5 s pause for an article page), 3 attempts, 5 s times the attempt number when no Retry-After came | |
| Brake | a host is left alone after 3 answers in a row of 403, 429 or 503 | |
| Newsroom sitemap index | at most 30 child sitemaps | |
| Silent source | nothing new in its last 5 checks | |

The values marked `[here]` in `config.py` are this repository's own: the pauses for the press
search (2 s) and the BORME summary (0.5 s), the robots.txt time-out (15 s), the cap on a
Retry-After wait (120 s), the 2 s base of the wait after a network error, the 5 redirects, the
40 search pages, the 30 s wait after a per-minute 429 that gives no delay, the two failed
batches that stop a run and the default daily cap of 300.
