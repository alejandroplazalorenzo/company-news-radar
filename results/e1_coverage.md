# E1: coverage against the Companies Register

Command: `company-news-radar e1-coverage --borme-db ../borme-radar/data/borme.sqlite --out results/e1_coverage.md`

- Run: 2026-11-19 17:20 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- borme-radar database (opened read-only): `borme.sqlite`
- A story counts if published 180 days before to 30 days after the act
- Rows 'all acts': every act of the source's period; rows 'whole window': only acts whose 180+30-day window lies inside the period
- One-to-one: acts in date order each take the unused compatible story closest in date (greedy, so a bound, not an optimal matching)
- Act types left out (not company facts this radar types): bylaws_amendment, erratum, ex_officio_cancellation, officer acts (appointments, removals, re-elections), other, powers_change, unexecuted_capital_increase, website

| Stories from | Acts | Seen (any story) | Median days ahead | Seen (compatible type) | Median days ahead | Seen (one-to-one) | Median days ahead |
|---|---:|---:|---:|---:|---:|---:|---:|
| press (2025-11-19 to 2026-11-18), all acts | 67 | 61 (91.0%) | 131.0 | 20 (29.9%) | 36.5 | 17 (25.4%) | 3.0 |
| press (2025-11-19 to 2026-11-18), whole window | 29 | 29 (100.0%) | 158.0 | 13 (44.8%) | 48.0 | 11 (37.9%) | -7.0 |
| official records (2025-11-19 to 2026-11-19), all acts | 67 | 59 (88.1%) | 75.0 | 48 (71.6%) | 42.0 | 22 (32.8%) | 13.5 |
| official records (2025-11-19 to 2026-11-19), whole window | 29 | 27 (93.1%) | 126.0 | 21 (72.4%) | 98.0 | 15 (51.7%) | 17.0 |

Positive days ahead: the radar had it before the Registro published it.

Acts of left-out types from 2025-11-19 to 2026-11-19: bylaws_amendment 14, erratum 8, ex_officio_cancellation 4, officer acts 1236, other 157, powers_change 1, unexecuted_capital_increase 2, website 1

### press

Acts seen under the loose metric, by the sources in their window: bing_news 56, bing_news+feed 4, bing_news+newsroom 1

| Company | Act | BORME date | Whole window | First compatible story | Days ahead | One-to-one story | Days ahead |
|---|---|---|---|---|---:|---|---:|
| santander | bond_issue | 2025-11-21 | no | - | - | - | - |
| caixabank | bond_issue | 2025-11-25 | no | - | - | - | - |
| cellnex | capital_reduction | 2025-11-27 | no | - | - | - | - |
| santander | bond_issue | 2025-12-05 | no | - | - | - | - |
| caixabank | capital_reduction | 2025-12-15 | no | - | - | - | - |
| merlin | bond_issue | 2025-12-17 | no | - | - | - | - |
| merlin | bond_issue | 2025-12-23 | no | - | - | - | - |
| santander | bond_issue | 2026-01-05 | no | - | - | - | - |
| bbva | capital_reduction | 2026-01-08 | no | - | - | - | - |
| santander | capital_reduction | 2026-01-12 | no | - | - | - | - |
| caixabank | bond_issue | 2026-01-13 | no | - | - | - | - |
| repsol | capital_reduction | 2026-01-19 | no | - | - | - | - |
| bbva | bond_issue | 2026-01-22 | no | - | - | - | - |
| santander | bond_issue | 2026-01-30 | no | - | - | - | - |
| santander | bond_issue | 2026-02-06 | no | - | - | - | - |
| sacyr | capital_increase | 2026-02-10 | no | - | - | - | - |
| caixabank | bond_issue | 2026-02-12 | no | - | - | - | - |
| iberdrola | capital_increase | 2026-02-12 | no | - | - | - | - |
| acs | capital_increase | 2026-02-16 | no | - | - | - | - |
| acs | capital_reduction | 2026-02-16 | no | - | - | - | - |
| santander | bond_issue | 2026-02-19 | no | - | - | - | - |
| santander | bond_issue | 2026-02-27 | no | - | - | - | - |
| santander | merger | 2026-02-27 | no | - | - | - | - |
| bankinter | merger_project | 2026-03-05 | no | - | - | - | - |
| bbva | bond_issue | 2026-03-10 | no | - | - | - | - |
| bbva | bond_issue | 2026-03-25 | no | - | - | - | - |
| merlin | capital_increase | 2026-04-06 | no | 2026-03-26 | 11 | 2026-03-26 | 11 |
| endesa | capital_reduction | 2026-04-07 | no | - | - | - | - |
| santander | bond_issue | 2026-04-10 | no | - | - | - | - |
| bbva | capital_reduction | 2026-04-16 | no | - | - | - | - |
| iag | capital_reduction | 2026-04-29 | no | 2026-02-26 | 62 | 2026-02-26 | 62 |
| solaria | capital_increase | 2026-05-08 | no | 2026-04-28 | 10 | 2026-05-06 | 2 |
| bbva | bond_issue | 2026-05-14 | no | - | - | - | - |
| caixabank | bond_issue | 2026-05-22 | yes | - | - | - | - |
| caixabank | capital_reduction | 2026-05-26 | yes | - | - | - | - |
| redeia | bond_issue | 2026-05-27 | yes | 2026-04-09 | 48 | 2026-04-09 | 48 |
| acs | capital_increase | 2026-05-28 | yes | - | - | - | - |
| amadeus | bond_issue | 2026-05-29 | yes | - | - | - | - |
| santander | bond_issue | 2026-06-05 | yes | 2026-05-27 | 9 | 2026-05-27 | 9 |
| sabadell | capital_reduction | 2026-06-19 | yes | - | - | - | - |
| santander | bond_issue | 2026-06-19 | yes | 2026-05-27 | 23 | - | - |
| caixabank | bond_issue | 2026-06-23 | yes | - | - | - | - |
| colonial | capital_reduction | 2026-06-30 | yes | 2026-03-26 | 96 | 2026-06-18 | 12 |
| amadeus | capital_reduction | 2026-07-07 | yes | - | - | - | - |
| bbva | bond_issue | 2026-07-07 | yes | - | - | - | - |
| bbva | capital_reduction | 2026-07-07 | yes | - | - | - | - |
| bankinter | merger | 2026-07-08 | yes | - | - | - | - |
| iberdrola | capital_reduction | 2026-07-14 | yes | - | - | - | - |
| acs | capital_increase | 2026-07-23 | yes | - | - | - | - |
| acs | capital_reduction | 2026-07-23 | yes | - | - | - | - |
| santander | bond_issue | 2026-07-30 | yes | 2026-05-27 | 64 | 2026-08-11 | -12 |
| indra | merger | 2026-08-03 | yes | 2026-02-05 | 179 | 2026-06-30 | 34 |
| iberdrola | capital_increase | 2026-08-06 | yes | - | - | - | - |
| sabadell | capital_reduction | 2026-08-07 | yes | 2026-09-01 | -25 | 2026-09-01 | -25 |
| repsol | capital_reduction | 2026-08-10 | yes | - | - | - | - |
| cellnex | capital_reduction | 2026-08-28 | yes | 2026-08-02 | 26 | 2026-08-25 | 3 |
| bbva | bond_issue | 2026-09-08 | yes | - | - | - | - |
| santander | capital_increase | 2026-09-10 | yes | 2026-05-27 | 106 | 2026-09-29 | -19 |
| santander | capital_reduction | 2026-09-18 | yes | 2026-05-27 | 114 | - | - |
| bbva | bond_issue | 2026-10-06 | yes | 2026-10-13 | -7 | 2026-10-13 | -7 |
| bbva | capital_reduction | 2026-10-06 | yes | 2026-10-13 | -7 | 2026-10-22 | -16 |
| santander | bond_issue | 2026-10-09 | yes | 2026-05-27 | 135 | 2026-10-28 | -19 |
| santander | bond_issue | 2026-10-23 | no | 2026-05-27 | 149 | - | - |
| telefonica | address_change | 2026-10-29 | no | 2026-09-21 | 38 | 2026-11-05 | -7 |
| endesa | capital_reduction | 2026-11-04 | no | - | - | - | - |
| fluidra | capital_reduction | 2026-11-12 | no | 2026-10-28 | 15 | 2026-10-28 | 15 |
| bbva | bond_issue | 2026-11-17 | no | 2026-10-13 | 35 | 2026-11-10 | 7 |

### official records

Acts seen under the loose metric, by the sources in their window: bdns 2, bdns+borme_c 3, bdns+borme_c+ted 23, bdns+ted 2, borme_c 17, borme_c+ted 11, ted 1

| Company | Act | BORME date | Whole window | First compatible story | Days ahead | One-to-one story | Days ahead |
|---|---|---|---|---|---:|---|---:|
| santander | bond_issue | 2025-11-21 | no | - | - | - | - |
| caixabank | bond_issue | 2025-11-25 | no | 2025-12-01 | -6 | 2025-12-01 | -6 |
| cellnex | capital_reduction | 2025-11-27 | no | - | - | - | - |
| santander | bond_issue | 2025-12-05 | no | 2025-12-24 | -19 | 2025-12-24 | -19 |
| caixabank | capital_reduction | 2025-12-15 | no | 2025-12-01 | 14 | - | - |
| merlin | bond_issue | 2025-12-17 | no | - | - | - | - |
| merlin | bond_issue | 2025-12-23 | no | - | - | - | - |
| santander | bond_issue | 2026-01-05 | no | 2025-12-24 | 12 | - | - |
| bbva | capital_reduction | 2026-01-08 | no | 2025-12-23 | 16 | 2025-12-23 | 16 |
| santander | capital_reduction | 2026-01-12 | no | 2025-12-24 | 19 | - | - |
| caixabank | bond_issue | 2026-01-13 | no | 2025-12-01 | 43 | - | - |
| repsol | capital_reduction | 2026-01-19 | no | - | - | - | - |
| bbva | bond_issue | 2026-01-22 | no | 2025-12-23 | 30 | - | - |
| santander | bond_issue | 2026-01-30 | no | 2025-12-24 | 37 | - | - |
| santander | bond_issue | 2026-02-06 | no | 2025-12-24 | 44 | - | - |
| sacyr | capital_increase | 2026-02-10 | no | 2026-01-12 | 29 | 2026-01-12 | 29 |
| caixabank | bond_issue | 2026-02-12 | no | 2025-12-01 | 73 | - | - |
| iberdrola | capital_increase | 2026-02-12 | no | 2026-01-09 | 34 | 2026-01-09 | 34 |
| acs | capital_increase | 2026-02-16 | no | - | - | - | - |
| acs | capital_reduction | 2026-02-16 | no | - | - | - | - |
| santander | bond_issue | 2026-02-19 | no | 2025-12-24 | 57 | - | - |
| santander | bond_issue | 2026-02-27 | no | 2025-12-24 | 65 | - | - |
| santander | merger | 2026-02-27 | no | - | - | - | - |
| bankinter | merger_project | 2026-03-05 | no | 2026-02-20 | 13 | 2026-02-20 | 13 |
| bbva | bond_issue | 2026-03-10 | no | 2025-12-23 | 77 | 2026-03-31 | -21 |
| bbva | bond_issue | 2026-03-25 | no | 2025-12-23 | 92 | - | - |
| merlin | capital_increase | 2026-04-06 | no | - | - | - | - |
| endesa | capital_reduction | 2026-04-07 | no | 2026-02-25 | 41 | 2026-02-25 | 41 |
| santander | bond_issue | 2026-04-10 | no | 2025-12-24 | 107 | - | - |
| bbva | capital_reduction | 2026-04-16 | no | 2025-12-23 | 114 | - | - |
| iag | capital_reduction | 2026-04-29 | no | 2026-03-24 | 36 | 2026-03-24 | 36 |
| solaria | capital_increase | 2026-05-08 | no | - | - | - | - |
| bbva | bond_issue | 2026-05-14 | no | 2025-12-23 | 142 | - | - |
| caixabank | bond_issue | 2026-05-22 | yes | 2025-12-01 | 172 | 2026-05-05 | 17 |
| caixabank | capital_reduction | 2026-05-26 | yes | 2025-12-01 | 176 | - | - |
| redeia | bond_issue | 2026-05-27 | yes | - | - | - | - |
| acs | capital_increase | 2026-05-28 | yes | - | - | - | - |
| amadeus | bond_issue | 2026-05-29 | yes | 2026-06-05 | -7 | 2026-06-05 | -7 |
| santander | bond_issue | 2026-06-05 | yes | 2025-12-24 | 163 | - | - |
| sabadell | capital_reduction | 2026-06-19 | yes | - | - | - | - |
| santander | bond_issue | 2026-06-19 | yes | 2025-12-24 | 177 | - | - |
| caixabank | bond_issue | 2026-06-23 | yes | 2026-05-05 | 49 | - | - |
| colonial | capital_reduction | 2026-06-30 | yes | 2026-06-19 | 11 | 2026-06-19 | 11 |
| amadeus | capital_reduction | 2026-07-07 | yes | 2026-06-05 | 32 | - | - |
| bbva | bond_issue | 2026-07-07 | yes | 2026-03-31 | 98 | 2026-06-24 | 13 |
| bbva | capital_reduction | 2026-07-07 | yes | 2026-03-31 | 98 | - | - |
| bankinter | merger | 2026-07-08 | yes | 2026-02-20 | 138 | - | - |
| iberdrola | capital_reduction | 2026-07-14 | yes | 2026-07-01 | 13 | 2026-07-03 | 11 |
| acs | capital_increase | 2026-07-23 | yes | - | - | - | - |
| acs | capital_reduction | 2026-07-23 | yes | - | - | - | - |
| santander | bond_issue | 2026-07-30 | yes | - | - | - | - |
| indra | merger | 2026-08-03 | yes | 2026-04-17 | 108 | 2026-04-17 | 108 |
| iberdrola | capital_increase | 2026-08-06 | yes | 2026-07-01 | 36 | 2026-07-01 | 36 |
| sabadell | capital_reduction | 2026-08-07 | yes | - | - | - | - |
| repsol | capital_reduction | 2026-08-10 | yes | - | - | - | - |
| cellnex | capital_reduction | 2026-08-28 | yes | 2026-08-05 | 23 | 2026-08-05 | 23 |
| bbva | bond_issue | 2026-09-08 | yes | 2026-03-31 | 161 | 2026-09-23 | -15 |
| santander | capital_increase | 2026-09-10 | yes | 2026-09-03 | 7 | 2026-09-03 | 7 |
| santander | capital_reduction | 2026-09-18 | yes | 2026-09-03 | 15 | - | - |
| bbva | bond_issue | 2026-10-06 | yes | 2026-06-24 | 104 | - | - |
| bbva | capital_reduction | 2026-10-06 | yes | 2026-06-24 | 104 | - | - |
| santander | bond_issue | 2026-10-09 | yes | 2026-09-03 | 36 | 2026-11-06 | -28 |
| santander | bond_issue | 2026-10-23 | no | 2026-09-03 | 50 | - | - |
| telefonica | address_change | 2026-10-29 | no | - | - | - | - |
| endesa | capital_reduction | 2026-11-04 | no | 2026-10-01 | 34 | 2026-10-01 | 34 |
| fluidra | capital_reduction | 2026-11-12 | no | 2026-10-29 | 14 | 2026-10-29 | 14 |
| bbva | bond_issue | 2026-11-17 | no | 2026-06-24 | 146 | - | - |
