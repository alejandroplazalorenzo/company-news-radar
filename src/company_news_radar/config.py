"""Every tunable value in one place.

Each value carries one of three labels: [production] is copied from the system this
repository rebuilds and was not measured here; [re-derived] was measured on this
repository's data (docs/thresholds.md, results/tuning.md); [here] was chosen for this
repository.
"""

from __future__ import annotations

# HTTP client
PAUSE_S = 1.0  # [production] gap between requests to one host
PAUSE_SEARCH_S = 2.0  # [here]
PAUSE_PAGE_S = 0.5  # [production]
PAUSE_SUMMARY_S = 0.5  # [here]
TIMEOUT_S = 30.0  # [production]
TIMEOUT_PAGE_S = 8.0  # [production]
TIMEOUT_ROBOTS_S = 15.0  # [here]
ATTEMPTS = 3  # [production]
RETRY_WAIT_S = 5.0  # [production] times the attempt number, when no Retry-After came
RETRY_AFTER_CAP_S = 120.0  # [here]
NETWORK_WAIT_BASE_S = 2.0  # [here] raised to the attempt number after a network error
MAX_REDIRECTS = 5  # [here]
BRAKE_AFTER = 3  # [production] blocking answers in a row before a host is skipped
BRAKE_STATUSES = frozenset({403, 429, 503})  # [production] answers that count as blocking

# press search
SEARCH_MAX_PAGES = 40  # [here]

# entity keys
MIN_ONE_WORD_LETTERS = 5  # [production]
CALIBRATION_MIN_LOWERCASE = 2  # [production]
CALIBRATION_MAX_SHARE = 0.02  # [re-derived] production had 0.003
CALIBRATION_FLOOR = 5  # [production]

# newsrooms
REDESIGN_NEW_URLS = 40  # [production]
REDESIGN_SHARE = 1 / 3  # [production]
CHILD_SITEMAPS_MAX = 30  # [production]

# exact repeats in process.py
HEADLINE_SIMILARITY = 0.85  # [re-derived] same as production
REPEAT_DAYS = 4  # [production] measured, see docs/thresholds.md

# rule-based filters
GRANT_FLOOR_EUR = 100_000  # [re-derived] same as production
CONTRACT_FLOOR_EUR = 1_000_000  # [re-derived] production had 500,000
FOREIGN_CCTLDS = frozenset("ar bo cl co mx pa pe py uy".split())  # [re-derived]

# LLM
GEMINI_MODEL = "gemini-flash-lite-latest"  # [production]
BATCH_SIZE = 15  # [production]
GEMINI_GAP_S = 4.5  # [production]
GEMINI_ATTEMPTS = 4  # [production]
GEMINI_TIMEOUT_S = 120.0  # [production]
RATE_WAIT_CAP_S = 120.0  # [production] longest wait after a per-minute 429
RATE_WAIT_EXTRA_S = 1.0  # [production] added to that wait
RATE_WAIT_DEFAULT_S = 30.0  # [here] when the 429 gives no delay
OVERLOAD_WAITS_S = (15.0, 30.0, 60.0)  # [production]
FAILED_BATCHES_STOP = 2  # [here]
DAILY_CAP = 300  # [here] default; --daily-cap overrides it
FREE_TIER_PER_DAY = 500  # Gemini free tier, per project and day
QUOTA_ZONE = "Europe/Madrid"  # with QUOTA_DAY_STARTS_AT, when the free tier resets
QUOTA_DAY_STARTS_AT = 9

# source health
IDLE_RUNS = 5  # [production] runs with nothing new before a source counts as silent

# merge step
SIGNATURE_MIN_SHARED = 2  # [production]
SIGNATURE_MIN_SHARE = 0.75  # [production] of the smaller signature
SIGNATURE_WINDOW_DAYS = 3  # [production]
FACT_WINDOW_DAYS = 30  # [production]
LONG_KEY_WINDOW_DAYS = 365  # [production]
TOPIC_WINDOW_DAYS = 4  # [production]
DOUBTFUL_WINDOW_DAYS = 1  # [production]
JUDGE_BATCH = 20  # [production]
