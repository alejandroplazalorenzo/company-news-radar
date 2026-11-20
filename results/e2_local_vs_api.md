# E2: local model against the API, same items, prompt and batches

Command: `company-news-radar e2-report --out results/e2_local_vs_api.md --labelled-by 'a stronger model, Claude Opus 5.5 (Anthropic), blind'`

- Run: 2026-11-19 17:20 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Sample: 150 stories the backfill sent to the LLM, none of them in the development subset the prompt was written from; seed 7, 10 batches of 15
- Prompts: v2

| Run | Failed batches | Items answered | Visible | Front page | Rule violations | Prompt tokens (median) | Output tokens (median) | Seconds per batch (median) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gemini-flash-lite | 0 | 150 of 150 | 101 | 8 | 3 | 3,281 | 1,372 | 5.22 |
| qwen3-8b-ctx4096 | 0 | 150 of 150 | 126 | 15 | 5 | 3,438 | 1,140 | 22.05 |
| qwen3-8b-ctx8192 | 0 | 150 of 150 | 128 | 16 | 5 | 3,438 | 1,137 | 50.91 |

Rule violations by check (items):

| Run | missing | summary_too_long | person_in_summary | bad_fact_key | company_out_of_range | market_noise_kept |
|---|---:|---:|---:|---:|---:|---:|
| gemini-flash-lite | 0 | 0 | 3 | 0 | 0 | 0 |
| qwen3-8b-ctx4096 | 0 | 0 | 2 | 2 | 0 | 1 |
| qwen3-8b-ctx8192 | 0 | 0 | 2 | 2 | 0 | 1 |

Agreement between runs (items both answered):

| A | B | n | Same type | Kappa (type) | Same visible | Same front page |
|---|---|---:|---:|---:|---:|---:|
| gemini-flash-lite | qwen3-8b-ctx4096 | 150 | 56.7% | 0.50 | 78.0% | 90.0% |
| gemini-flash-lite | qwen3-8b-ctx8192 | 150 | 58.0% | 0.52 | 78.0% | 90.7% |
| qwen3-8b-ctx4096 | qwen3-8b-ctx8192 | 150 | 86.7% | 0.85 | 97.3% | 98.0% |

Run notes (recorded by `e2-run` while the model was loaded):

- qwen3-8b-ctx4096: gpu NVIDIA GeForce RTX 3070 Laptop GPU, 8192 MiB; ollama 0.40.16; model qwen3:8b; digest 500a1f067a9f; num_ctx 4096; think False; processor 100% GPU; loaded size (GB) 6.3
- qwen3-8b-ctx8192: gpu NVIDIA GeForce RTX 3070 Laptop GPU, 8192 MiB; ollama 0.40.16; model qwen3:8b; digest 500a1f067a9f; num_ctx 8192; think False; processor 22%/78% CPU/GPU; loaded size (GB) 8.1

Against the blind reference labels (150 items, labelled by a stronger model, Claude Opus 5.5 (Anthropic), blind: agreement with that labeller, not accuracy):

| Run | Same type | Same visible | Same front page | Front page precision | recall |
|---|---:|---:|---:|---:|---:|
| gemini-flash-lite | 73.3% | 83.3% | 94.7% | 62.5% | 50.0% |
| qwen3-8b-ctx4096 | 60.0% | 80.0% | 91.3% | 40.0% | 60.0% |
| qwen3-8b-ctx8192 | 60.0% | 81.3% | 90.7% | 37.5% | 60.0% |

Reference front-page stories: 10.
