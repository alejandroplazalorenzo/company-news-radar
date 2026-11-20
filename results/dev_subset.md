# Development subset

Command: `company-news-radar dev-report --out results/dev_subset.md`

- Run: 2026-11-19 17:31 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Drawn by `dev-split --prompt v1 --seed 7` from the 2809 stories v1 read; the rest (1966) is where E2 draws its sample

| v1 on the subset | Stories |
|---|---:|
| read | 843 |
| shown | 639 |
| on the front page | 72 |
| front page, deal | 45 |
| front page, footprint | 27 |

Reading of the 72 front-page stories (`v1_front_reading.jsonl`, written by an AI coding assistant; not blind: the reader saw v1's answers): 43 should not be on the front page (28 of 45 deal, 15 of 27 footprint); not read: 0.

v2 on the same 72 stories: 46 kept on the front page, 26 taken off; it agrees with the reading on 45 of them.
