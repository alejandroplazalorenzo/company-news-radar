# Thresholds checked on the stored data

Command: `company-news-radar tuning-report --out results/tuning.md`

- Run: 2026-11-19 18:40 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5

## Exact repeats: headline similarity and day window

Kept press captures: 3073 in 2809 press stories, so 264 were folded. Replaying the current setting (0.85 within 4 days) folds 264 (through process.RepeatIndex: the same).

Folds per setting. The outcome columns describe the folds that setting makes and the current one does not (Extra); Lost counts the current folds it does not make, and how many of those joined disjoint companies. Companies are those the linker finds in each capture.

| Cut | Days | Folds | Extra | disjoint companies | same story in the end | kept apart by the merge step | one of them hidden | Lost | Lost, disjoint companies |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.70 | 1 | 458 | 213 | 25 | 144 | 7 | 37 | 19 | 5 |
| 0.70 | 2 | 466 | 215 | 26 | 142 | 6 | 41 | 13 | 3 |
| 0.70 | 4 | 483 | 225 | 27 | 143 | 7 | 48 | 6 | 1 |
| 0.70 | 7 | 508 | 249 | 39 | 142 | 11 | 57 | 5 | 1 |
| 0.75 | 1 | 378 | 130 | 14 | 93 | 4 | 19 | 16 | 5 |
| 0.75 | 2 | 387 | 134 | 14 | 93 | 4 | 23 | 11 | 4 |
| 0.75 | 4 | 401 | 141 | 15 | 94 | 5 | 27 | 4 | 2 |
| 0.75 | 7 | 424 | 164 | 25 | 95 | 8 | 36 | 4 | 2 |
| 0.80 | 1 | 308 | 59 | 7 | 39 | 2 | 11 | 15 | 4 |
| 0.80 | 2 | 314 | 60 | 7 | 39 | 2 | 12 | 10 | 3 |
| 0.80 | 4 | 328 | 65 | 7 | 40 | 3 | 15 | 1 | 0 |
| 0.80 | 7 | 345 | 83 | 14 | 41 | 5 | 23 | 2 | 0 |
| 0.85 | 1 | 250 | 0 | 0 | 0 | 0 | 0 | 14 | 4 |
| 0.85 | 2 | 256 | 0 | 0 | 0 | 0 | 0 | 8 | 2 |
| 0.85 | 4 | 264 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.85 | 7 | 278 | 15 | 5 | 0 | 2 | 8 | 1 | 0 |
| 0.90 | 1 | 207 | 2 | 0 | 1 | 0 | 1 | 59 | 8 |
| 0.90 | 2 | 211 | 2 | 0 | 1 | 0 | 1 | 55 | 7 |
| 0.90 | 4 | 216 | 2 | 0 | 1 | 0 | 1 | 50 | 7 |
| 0.90 | 7 | 228 | 14 | 3 | 1 | 3 | 7 | 50 | 7 |
| 0.95 | 1 | 172 | 2 | 0 | 1 | 0 | 1 | 94 | 9 |
| 0.95 | 2 | 176 | 2 | 0 | 1 | 0 | 1 | 90 | 8 |
| 0.95 | 4 | 181 | 2 | 0 | 1 | 0 | 1 | 85 | 8 |
| 0.95 | 7 | 189 | 10 | 1 | 1 | 2 | 6 | 85 | 8 |

The 264 folds of the current setting: disjoint companies 11, same story in the end 253, kept apart by the merge step 0, one of them hidden 0.

Every pair of kept press captures up to 7 days apart, by headline similarity, whatever the fold did:

| Similarity | Pairs | disjoint companies | same story in the end | kept apart by the merge step | one of them hidden |
|---|---:|---:|---:|---:|---:|
| 0.60-0.65 | 781 | 346 | 292 | 34 | 109 |
| 0.65-0.70 | 451 | 124 | 238 | 17 | 72 |
| 0.70-0.75 | 327 | 63 | 197 | 9 | 58 |
| 0.75-0.80 | 236 | 31 | 159 | 4 | 42 |
| 0.80-0.85 | 157 | 21 | 102 | 4 | 30 |
| 0.85-0.90 | 112 | 17 | 90 | 0 | 5 |
| 0.90-0.95 | 62 | 4 | 55 | 1 | 2 |
| 0.95-1.00 | 221 | 2 | 204 | 2 | 13 |

Pairs at 0.85 or more, by days apart:

| Days apart | Pairs | disjoint companies | same story in the end | kept apart by the merge step | one of them hidden |
|---:|---:|---:|---:|---:|---:|
| 0 | 291 | 5 | 284 | 0 | 2 |
| 1 | 53 | 2 | 51 | 0 | 0 |
| 2 | 12 | 5 | 7 | 0 | 0 |
| 3 | 6 | 2 | 3 | 0 | 1 |
| 4 | 7 | 1 | 4 | 0 | 2 |
| 5 | 9 | 3 | 0 | 1 | 5 |
| 6 | 6 | 1 | 0 | 1 | 4 |
| 7 | 11 | 4 | 0 | 1 | 6 |

## Calibration of derived one-word keys

Corpus: 1148 feed captures. One-word company names in the watchlist (three letters or more, not generic): 28. Derived one-word keys in use: COLONIAL; the other names are aliases, or shorter than 5 letters, and the calibration never touches them.
Current setting: a derived key goes when 2 or more texts write it in lower case, or when it matches more than 22.96 texts (the larger of 5 and 0.02 x 1148). The last column applies that test to every name, as if all were derived.

| Name | Letters | Texts in lower case | Texts matched | Share | Would go |
|---|---:|---:|---:|---:|---|
| REPSOL | 6 | 0 | 10 | 0.87% | no |
| ENAGAS | 6 | 0 | 7 | 0.61% | no |
| UNICAJA | 7 | 0 | 7 | 0.61% | no |
| BBVA | 4 | 0 | 6 | 0.52% | no |
| INDRA | 5 | 0 | 6 | 0.52% | no |
| MAPFRE | 6 | 0 | 6 | 0.52% | no |
| BANKINTER | 9 | 0 | 5 | 0.44% | no |
| CAIXABANK | 9 | 0 | 5 | 0.44% | no |
| INDITEX | 7 | 0 | 4 | 0.35% | no |
| ACCIONA | 7 | 0 | 3 | 0.26% | no |
| SOLARIA | 7 | 0 | 3 | 0.26% | no |
| ACERINOX | 8 | 0 | 2 | 0.17% | no |
| ACS | 3 | 0 | 2 | 0.17% | no |
| AENA | 4 | 0 | 2 | 0.17% | no |
| COLONIAL | 8 | 0 | 2 | 0.17% | no |
| ENDESA | 6 | 0 | 2 | 0.17% | no |
| IAG | 3 | 0 | 2 | 0.17% | no |
| IBERDROLA | 9 | 0 | 2 | 0.17% | no |
| GRIFOLS | 7 | 0 | 1 | 0.09% | no |
| NATURGY | 7 | 0 | 1 | 0.09% | no |
| PUIG | 4 | 0 | 1 | 0.09% | no |
| REDEIA | 6 | 0 | 1 | 0.09% | no |
| ROVI | 4 | 0 | 1 | 0.09% | no |
| AMADEUS | 7 | 0 | 0 | 0.00% | no |
| CELLNEX | 7 | 0 | 0 | 0.00% | no |
| FLUIDRA | 7 | 0 | 0 | 0.00% | no |
| LOGISTA | 7 | 0 | 0 | 0.00% | no |
| SACYR | 5 | 0 | 0 | 0.00% | no |

Derived one-word keys for each minimum length of a one-word key (the current one is 5); a key the calibration keeps stays in the linker:

| Minimum letters | Derived one-word keys | Kept by the calibration |
|---:|---|---|
| 3 | ACS, COLONIAL, PUIG | ACS, COLONIAL, PUIG |
| 4 | COLONIAL, PUIG | COLONIAL, PUIG |
| 5 | COLONIAL | COLONIAL |
| 6 | COLONIAL | COLONIAL |

## Figures behind the other re-derived values

- grant records: 50 for 12 companies, 50 with an amount; p10 6,000, p25 12,498, median 134,860, p75 1,269,735, p90 3,752,963 EUR (statistics.quantiles, inclusive; statistics.median); below the floor of 100,000 EUR: 21.
- contract records: 133 for 9 companies, 114 with an amount; p10 116,022, p25 357,229, median 1,146,811, p75 5,144,882, p90 11,766,862 EUR (statistics.quantiles, inclusive; statistics.median); below the floor of 1,000,000 EUR: 55.
- press-search captures by publisher top-level domain: .com 2388, .es 781, .cat 20, .uy 11, .de 8, .mx 7, .org 7, .eus 6, .net 6, .news 5, .cl 5, .it 4, .ar 3, .pe 2, .co 2, .bo 2, .pa 1, .tv 1, .py 1, .jp 1, .io 1, .info 1; dropped as foreign: ar, bo, cl, co, mx, pa, pe, py, uy.
- search results dropped because headline and snippet name no watched company: 97; with a stock-market word in the headline: 26 (words: `\b(?:ibex|bolsas?|selectivo|mercados?|cotiza\w*|acciones|valores|wall street|dividendo\w*|analistas?|precio objetivo)\b`).
- of those, also matched by the share-price or session patterns: 0 (the triage checks names first, so none of them reached those patterns).
