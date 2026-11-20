# E2: local model against the API, same items, prompt and batches

Command: `company-news-radar e2-report --sample b25 --out results/e2_batch25_context.md --labelled-by 'a stronger model, Claude Opus 5.5 (Anthropic), blind'`

- Run: 2026-11-19 17:20 UTC
- Python 3.13.7 on Windows 11; httpx 0.28.1, lxml 6.1.3, truststore 0.10.5
- Sample: 150 stories the backfill sent to the LLM, none of them in the development subset the prompt was written from; seed 7, 6 batches of 25
- Prompts: v2

| Run | Failed batches | Items answered | Visible | Front page | Rule violations | Prompt tokens (median) | Output tokens (median) | Seconds per batch (median) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gemini-flash-lite-b25 | 0 | 150 of 150 | 106 | 10 | 4 | 4,460 | 2,274 | 6.94 |
| qwen3-8b-ctx4096-b25 | 0 | 90 of 150 | 90 | 0 | 129 | 2,050 | 1,814 | 37.98 |
| qwen3-8b-ctx8192-b25 | 0 | 149 of 150 | 129 | 16 | 5 | 4,716 | 1,830 | 88.45 |

Rule violations by check (items):

| Run | missing | summary_too_long | person_in_summary | bad_fact_key | company_out_of_range | market_noise_kept |
|---|---:|---:|---:|---:|---:|---:|
| gemini-flash-lite-b25 | 0 | 0 | 3 | 0 | 1 | 0 |
| qwen3-8b-ctx4096-b25 | 60 | 47 | 5 | 75 | 1 | 1 |
| qwen3-8b-ctx8192-b25 | 1 | 0 | 3 | 1 | 0 | 1 |

Agreement between runs (items both answered):

| A | B | n | Same type | Kappa (type) | Same visible | Same front page |
|---|---|---:|---:|---:|---:|---:|
| gemini-flash-lite-b25 | qwen3-8b-ctx4096-b25 | 90 | 8.9% | 0.02 | 72.2% | 93.3% |
| gemini-flash-lite-b25 | qwen3-8b-ctx8192-b25 | 149 | 63.1% | 0.58 | 82.6% | 87.9% |
| qwen3-8b-ctx4096-b25 | qwen3-8b-ctx8192-b25 | 90 | 14.4% | 0.04 | 93.3% | 85.6% |

Run notes (recorded by `e2-run` while the model was loaded):

- qwen3-8b-ctx4096-b25: gpu NVIDIA GeForce RTX 3070 Laptop GPU, 8192 MiB; ollama 0.40.16; model qwen3:8b; digest 500a1f067a9f; num_ctx 4096; think False; processor 100% GPU; loaded size (GB) 6.3
- qwen3-8b-ctx8192-b25: gpu NVIDIA GeForce RTX 3070 Laptop GPU, 8192 MiB; ollama 0.40.16; model qwen3:8b; digest 500a1f067a9f; num_ctx 8192; think False; processor 22%/78% CPU/GPU; loaded size (GB) 8.1

Against the blind reference labels (150 items, labelled by a stronger model, Claude Opus 5.5 (Anthropic), blind: agreement with that labeller, not accuracy):

| Run | Same type | Same visible | Same front page | Front page precision | recall |
|---|---:|---:|---:|---:|---:|
| gemini-flash-lite-b25 | 74.0% | 88.0% | 93.3% | 50.0% | 50.0% |
| qwen3-8b-ctx4096-b25 | 8.0% | 56.0% | 93.3% | n/a | 0.0% |
| qwen3-8b-ctx8192-b25 | 61.3% | 80.7% | 90.7% | 37.5% | 60.0% |

Reference front-page stories: 10.
