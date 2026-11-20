# Prompt versions

Counts below: `company-news-radar dev-report --out results/dev_subset.md`, run on 19 Nov 2026
(Windows 11, Python 3.13.7), over the answers stored by `classify --prompt v1` and
`reclassify --prompt v2 --only-visible` on the same day (`gemini-flash-lite-latest`).

The prompts are this rebuild's own (`src/company_news_radar/prompts.py`). What each answer
field means is written once, in the `description` of the field in the JSON schema, and the
prompt prints that schema: Gemini also gets it as its enforced response format, and the local
model of E2 reads the same text. Items go in as one compact JSON object per line (headline,
outlet, date, the first 300 characters of the snippet, and the candidate companies numbered).

The process is the production one: start minimal, look at what the version gets wrong on
real data, write a rule for each failure, run the new version. `results/e3_prompt_versions.md`
measures the effect.

## v1: the minimal instruction

The task (sort items about large Spanish listed groups for an analyst who follows them, from
the given text only), the twelve types with their definitions (`models.TAXONOMY`), the three
relevance levels with no criteria, and a note that candidates can be homonyms or passing
mentions. The schema asks for the type of the fact in the headline, a 25-word English summary
with companies and job titles but no personal names, the candidates that are a party to the
fact, the country where it happens, and a fact key with fixed forms for yearly results,
quarterly results and takeover bids (the long-lived keys of the merger). `country` and the
fact key are in the schema from the start: the Spain rule and the merging need them; what
changes between versions is the rules.

## How v2 was written

After v1 had read the 2,809 stories, `dev-split --prompt v1 --share 0.3 --seed 7` set apart a
random **development subset of 843 stories** (`data/dev/ids.json`, gitignored). The subset
was read with an AI coding assistant (Claude, Anthropic), which also drafted v2's rules from
v1's answers on that subset only. E2 draws its sample from the other 1,966 stories, so the
prompt is not scored on the stories it was written from.

On the subset v1 left 639 stories visible and 72 on the front page (45 deals, 27 footprint
changes). The verdicts of that first reading were not saved one by one, so the 72 were read
again on 19 Nov 2026 by the same assistant and its verdicts are now stored
(`data/dev/v1_front_reading.jsonl`, counted by `dev-report`). That reading is not blind (it
saw v1's answers and knew v2's rules): 43 of the 72 should not be on the front page (28 of 45
deals, 15 of 27 footprint changes). v2 took 26 of the 72 off the front page; v2 and the
reading agree on 45 of the 72 (`results/dev_subset.md`). What v1 got wrong, and the rule v2
adds for it:

| v1 got wrong | v2 rule |
|---|---|
| Share-price stories, "why is it falling" pieces and rumours typed as deals or results, some with high relevance | 1: stock-market items are irrelevant, even when the move is explained by a deal or results |
| Commercial alliances, joint offers to customers, technology partnerships, consortia and talks about collaborating typed as deals | 2: a deal needs a business, or a stake of 3% or more, to change owner (agreed, closed or formally offered) |
| Funds moving a stake of about 1% taken for a significant holding | 2 (the 3% threshold) |
| The watched company confirmed when it was a competitor, a partner in passing, the former owner, or when its founding family acted on its own account | 3: a candidate counts only if it acts or the event happens to it |
| Works, upgrades and investment in existing networks and plants, grid connections, progress of announced projects, new routes from existing hubs, a regional reorganisation, an investment budget, even a carbon-footprint report, typed as footprint | 4: what footprint is and is not |
| Investment plans typed as capital; dividend calendars, payment dates of dividends already declared and savings-account rates kept visible | 5 |
| Agreements where the watched company is the client of a technology provider, and bids not yet won, typed as contracts | 6 |
| Opinions and statements (an executive or a mayor defending a project, a company that sees a business opportunity in a new rule), political proposals, executives' pay | 7 |
| No criteria for relevance: a share-price piece marked high | the three levels defined |

v2 was run only on the 2,119 stories v1 left visible
(`reclassify --prompt v2 --only-visible`). What v2 would do with the 690 stories v1 hid is not
measured.

On the kinds, v2 is the stricter of the two: 361 of the 2,119 went to irrelevant. On
relevance it is not, because v2 defines the levels that v1 left open, and the stored answers
move both ways. Of the 2,119 stories both versions read, 26 entered the front page under v2
and 99 left it; 31 gained an alert and 243 lost one; among the stories both kept visible, 273
got a higher level and 175 a lower one; 45 moved to a kind that weighs more in the visibility
rules and 508 to one that weighs less. In four weeks (2026-W07, W14, W40 and W42) v2 has more
front-page stories than v1. All of it is in `results/e3_prompt_versions.md`.
