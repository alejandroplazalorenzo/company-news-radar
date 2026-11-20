# E3: prompt versions, front page per period

Command: `company-news-radar e3-report --out results/e3_prompt_versions.md`

- Run: 2026-11-19 18:33 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Stories classified by v1: 2809; read again by each version: v1 2809, v2 2119
- Front page = deal or footprint, high or medium relevance, in Spain; counted before merging repeats, so only the prompt changes between rows

| Version | Read | Visible | Front page | 2025-11 | 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 | 2026-10 | 2026-11 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 2809 | 2119 | 249 | 2 | 22 | 6 | 14 | 6 | 15 | 12 | 8 | 11 | 7 | 26 | 33 | 87 |
| v2 | 2119 | 1758 | 176 | 2 | 18 | 4 | 11 | 4 | 10 | 10 | 6 | 7 | 7 | 16 | 29 | 52 |

Front page per ISO week:

| Version | 2025-W47 | 2025-W48 | 2025-W49 | 2025-W50 | 2025-W51 | 2025-W52 | 2026-W01 | 2026-W02 | 2026-W03 | 2026-W04 | 2026-W05 | 2026-W06 | 2026-W07 | 2026-W08 | 2026-W09 | 2026-W10 | 2026-W11 | 2026-W12 | 2026-W13 | 2026-W14 | 2026-W15 | 2026-W16 | 2026-W17 | 2026-W18 | 2026-W19 | 2026-W20 | 2026-W21 | 2026-W22 | 2026-W23 | 2026-W24 | 2026-W25 | 2026-W26 | 2026-W27 | 2026-W28 | 2026-W29 | 2026-W30 | 2026-W31 | 2026-W32 | 2026-W33 | 2026-W34 | 2026-W35 | 2026-W36 | 2026-W37 | 2026-W38 | 2026-W39 | 2026-W40 | 2026-W41 | 2026-W42 | 2026-W43 | 2026-W44 | 2026-W45 | 2026-W46 | 2026-W47 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v1 | 2 | 0 | 6 | 10 | 2 | 3 | 1 | 0 | 5 | 0 | 1 | 3 | 4 | 2 | 5 | 0 | 2 | 1 | 3 | 0 | 6 | 2 | 6 | 1 | 3 | 1 | 3 | 5 | 3 | 1 | 3 | 0 | 3 | 2 | 1 | 1 | 6 | 3 | 3 | 0 | 0 | 2 | 2 | 6 | 12 | 6 | 6 | 8 | 5 | 12 | 20 | 44 | 23 |
| v2 | 2 | 0 | 5 | 9 | 1 | 2 | 1 | 0 | 4 | 0 | 0 | 2 | 5 | 1 | 3 | 0 | 2 | 0 | 2 | 1 | 6 | 2 | 0 | 1 | 3 | 1 | 3 | 3 | 2 | 1 | 2 | 0 | 2 | 0 | 1 | 1 | 5 | 3 | 3 | 0 | 0 | 0 | 1 | 5 | 7 | 7 | 5 | 9 | 1 | 10 | 10 | 34 | 8 |

Visibility v1 -> v2: classified -> classified: 1758, classified -> discarded: 361, discarded -> discarded: 690

Type changes v1 -> v2 (top 12):

| From | To | Stories |
|---|---|---:|
| image | irrelevant | 88 |
| capital | irrelevant | 73 |
| results | irrelevant | 50 |
| risk | irrelevant | 36 |
| footprint | corporate | 35 |
| footprint | irrelevant | 32 |
| corporate | irrelevant | 28 |
| corporate | image | 24 |
| footprint | image | 21 |
| deal | irrelevant | 17 |
| contract | image | 16 |
| capital | corporate | 15 |

Stories read by both v1 and v2: 2119. Changes from v1 to v2, both ways (kind weight: deal and footprint 4; regulation, results and risk 3; other business kinds 2; image 1; irrelevant 0):

| Change | Up | Down |
|---|---:|---:|
| front page (entered / left) | 26 | 99 |
| alert (gained / lost) | 31 | 243 |
| relevance level, stories shown by both (higher / lower) | 273 | 175 |
| kind, by weight in the visibility rules (heavier / lighter) | 45 | 508 |

Weeks with more front-page stories under v2 than under v1: 2026-W07, 2026-W14, 2026-W40, 2026-W42.
Stories v1 read and v2 did not: 690 (what v2 would do with them is not measured).
