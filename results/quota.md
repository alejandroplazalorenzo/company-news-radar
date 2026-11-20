# LLM quota and cost

Command: `company-news-radar quota-report --out results/quota.md`

- Run: 2026-11-19 17:20 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Gemini free tier: 500 requests a day per project, shared with another system; this project's cap (counted on disk before each request): 300 a day by default, caps recorded in the call log: 480 (198 requests logged without one, before `--daily-cap` existed, ran under the default)
- Model requested: gemini-flash-lite-latest; versions that answered: gemini-3.5-flash-lite

| Quota day | Purpose | Requests | OK | 503 | Items | Items per OK request | Seconds per request (median) | Prompt tokens (mean) | Output tokens (mean) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-11-19 | classify-v1 | 198 | 188 | 10 | 2809 | 14.9 | 3.50 | 2697 | 1359 |
| 2026-11-19 | classify-v2 | 154 | 142 | 12 | 2119 | 14.9 | 6.49 | 3251 | 1345 |
| 2026-11-19 | e2-gemini-flash-lite | 12 | 10 | 2 | 150 | 15.0 | 5.22 | 3277 | 1362 |
| 2026-11-19 | e2-gemini-flash-lite-b25 | 6 | 6 | 0 | 150 | 25.0 | 6.94 | 4453 | 2268 |
| 2026-11-19 | judge-j1 | 18 | 18 | 0 | 352 | 19.6 | 4.34 | 5487 | 632 |

| Quota day | Requests in the call log | Persistent counter (`quota.json`) |
|---|---:|---:|
| 2026-11-19 | 388 | 388 |

The counter is written before each request is sent, so it can only be higher than the log (a run stopped between the two).
