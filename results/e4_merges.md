# E4: merging repeats

Command: `company-news-radar e4-report --out results/e4_merges.md --labelled-by 'a stronger model, Claude Opus 5.5 (Anthropic), blind'`

- Run: 2026-11-19 17:20 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Visible stories after merging: 1197
- Judge verdicts stored: same 106, not the same 246

| Rule | Merges |
|---|---:|
| fact | 164 |
| judge | 92 |
| long_key | 8 |
| signature | 394 |
| topic | 40 |
| total | 698 |

Visible stories after merging, by source:

| Source | Visible | Front page | Alerts |
|---|---:|---:|---:|
| bdns | 29 | 0 | 0 |
| bing_news | 1037 | 120 | 414 |
| borme_c | 30 | 2 | 2 |
| feed | 17 | 2 | 4 |
| newsroom | 6 | 0 | 3 |
| ted | 78 | 0 | 0 |
| total | 1197 | 124 | 423 |

Doubtful pairs among the visible stories now (what the judge would be asked):

- production's same-day rule applied to these stories (two stories of one company within a day): 1139
- this rebuild (within a day, also a headline word in common other than the companies' names): 201

Against the blind labels (labelled by a stronger model, Claude Opus 5.5 (Anthropic), blind: agreement, not accuracy):

- merged pairs labelled the same event: 38 of 40
  - rule fact: 8 of 9
  - rule judge: 8 of 8
  - rule signature: 21 of 21
  - rule topic: 1 of 2
- not-merged pairs labelled the same event: 7 of 40
  - judge said no: 7 of 40
