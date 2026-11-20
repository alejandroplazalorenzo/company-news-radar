# Guide for the blind reference labels (E2 and E4)

The labeller sees two queues built by `e2-sample` and `e4-report --queue`. Neither carries
anything the radar decided: no type, no level, no merge decision, no model output. The key
that links each line to a story is kept in another file the labeller does not open.

Work from the text in the queue only (headline, snippet, outlet, date, the watched companies
the radar found named in it). Do not search for the story elsewhere. Write one JSON object per
line, in any order, and leave out nothing.

## E2: `data/judge/queue.jsonl` -> `data/judge/labels.jsonl`

One label per `qid`:

```json
{"qid": "q001", "type": "deal", "relevance": "medium", "country": "Spain", "about_watched": true}
```

**`type`**: what the item reports, as one of the radar's types. Read the definitions as a
reader who follows these companies would: what changed for the company?

| Type | Use it when |
|---|---|
| `deal` | ownership or control changes hands: a purchase, a sale, a merger, a takeover bid, a joint venture, a holder crossing a significant stake |
| `results` | figures of a closed period, or a change in the targets the company gave the market |
| `capital` | money raised or returned: shares, buybacks, dividends declared, bonds, loans, a rating change |
| `leadership` | someone joins or leaves the board or the top executive team |
| `footprint` | a plant, office, store, branch network or data centre opens, closes or moves; a country or a business entered or left |
| `contract` | a significant order or contract won or lost, tenders included |
| `grant` | a public grant or subsidy awarded to the company |
| `risk` | something that can hurt operations or money: layoffs, strikes, fines, lawsuits, investigations, insolvency, a cyber-attack, an accident that halts activity |
| `regulation` | a dated rule (law, tax, tariff, licence, ruling) that changes the business of the company or its sector in Spain |
| `corporate` | the company's own governance and legal housekeeping: meetings, articles, registered office, name, a strategic plan |
| `image` | publicity: a product on sale, advertising, sponsorship, prizes and rankings, events, social programmes, interviews and profiles |
| `irrelevant` | nothing changes in the business: share-price moves, analysts' notes and targets, the company only in passing, someone else with the same name |

When an item tells several things, label the one its headline leads with. A report about
how the market or analysts reacted to an event is about the reaction (`irrelevant`), not the
event itself.

**`relevance`**, for someone who follows the company:

- `high`: the size, ownership, sites or finances of the company change in a way they must
  know about this week;
- `medium`: a real change of smaller size, or a large one at an early stage (talks, an offer
  not yet accepted, a project announced);
- `low`: real but routine for a group of this size, or anything labelled `irrelevant`.

**`country`**: the English name of the country where the event takes place (the plant, the
market, the buyer, the court). If the event belongs to the whole company and has no place
(its results, a bond, a board change), the country of its head office.

**`about_watched`**: `true` if at least one of the companies in `watched_companies_named` is
a party to the event (it acts, or the event happens to it). `false` if they are only lenders,
advisers, landlords, competitors or a passing mention, if the name belongs to someone else,
or if the list is empty.

## E4: `data/judge/merge_queue.jsonl` -> `data/judge/merge_labels.jsonl`

One label per `pid`, for the two items `a` and `b`:

```json
{"pid": "p001", "same": true}
```

`same` is `true` when a digest should show the two items as **one entry**, because they are
about one single event: the same parties doing the same thing to the same object. Different
headlines, more or less detail, the parent company named in one and a subsidiary or a brand
in the other, or a few days between them, do not make two events.

`same` is `false` when there are two events, even closely related ones: a bid and its later
acceptance, a plan and its approval, two contracts, two plants, two quarters, two bond
issues. Also `false` when the text does not let you tell.

## How the labels are scored

`e2-report --labelled-by "<who>"` turns each E2 label into the radar's levels with the
radar's own rules (`classify.decide`: abroad, homonym, front page, alert) and compares them
with each model's answers; `e4-report --labelled-by "<who>"` compares `same` with what the
merger did. Labels written by a model are reported as agreement with that model, not as
accuracy.
