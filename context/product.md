# Product

## The one-liner

Strava Premium, individualised to one person, for free — built on Garmin watch
data I already generate.

## Who it is for

**Now: me.** One person, one Garmin watch, several years of history. Every
decision optimises for that one reader. n=1 is a feature at this stage: it means
the analytics can assume my baselines rather than a population's.

**Later, maybe: a few friends.** Only if it works well enough that I would send
them a link without apologising for it first. Not a business, not a product
launch — a thing I share.

## The pain

Strava charges a subscription for the analysis layer. I did not want to spend
the money, and the data underneath it is mine already: my watch records it, my
Garmin account holds it, and Garmin's own API will hand it back.

## The promise

1. **Everything I actually used** from the paid tier.
2. **Individualised** — thresholds derived from my own history, not from
   population averages. "Low HRV" should mean low *for me*.
3. **Free of charge** — no subscription, no hosted service, no third party
   holding the data.
4. **Transparent** — every number traces to a formula I can read. Where a
   subscription gives you a score, this gives you the score and its inputs.

## Scope for v1

**In:** the derived analytics layer. Fitness/fatigue/form, workload ratios,
recovery, sleep debt, correlations, and — next — a written weekly review that
interprets them.

**Out for now:** segments, routes, maps, social features, coaching plans,
multi-user accounts. See ROADMAP.md for why each is deferred.

## What "better than the paid thing" means here

Not more features. Two specific advantages a subscription cannot match:

- **It knows only me.** No cohort, no averages, no defaults.
- **It shows its work.** Every score arrives with its components visible.

## Open questions

- **Is this repo public?** Unresolved as of 2026-08-18. It contains resting heart
  rate, sleep, and weight. GitHub Pages on a private repo needs a paid plan,
  which pushes toward opening it — but that is a decision to make deliberately,
  not to discover. Tracked as item 2 in ROADMAP.md.
- **Which Strava paid features did I actually use?** The v1 scope is a bet that
  it was mostly the analysis. Worth checking against memory before building
  anything in the Later column.
