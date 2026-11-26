---
title: "The bookmaker's margin, explained: how the house is paid"
description: "Every betting price has a fee folded into it: the margin, overround or vig. How to find it in any market, what it costs over time, and why it is easy to miss."
topic: odds
published: 2026-11-26
updated: 2026-11-26
sources:
  - label: "Snowberg, E. & Wolfers, J. (2010). Explaining the favorite–long shot bias: is it risk-love or misperceptions? Journal of Political Economy, 118(4), 723–746."
    href: "https://doi.org/10.1086/655844"
  - label: "Štrumbelj, E. (2014). On determining probability forecasts from betting odds. International Journal of Forecasting, 30(4), 934–943."
    href: "https://doi.org/10.1016/j.ijforecast.2014.02.008"
  - label: "Gambling Commission (Great Britain), July 2025. Commercial restrictions by betting operators: what operators' own data shows."
    href: "https://www.gamblingcommission.gov.uk/blog/post/commercial-restrictions-by-betting-operators"
  - label: "UNLV Center for Gaming Research (February 2026). Nevada sports betting totals, 1984–2025: win, drop and win percentages by sport."
    href: "https://www.library.unlv.edu/gaming/reports/NV_sportsbetting.pdf"
---

A bookmaker does not charge a fee. There is no line on a betting slip that says “commission”, and nothing is deducted from a winning bet. So where does the money come from?

It comes out of the price. Every set of odds on offer is a little worse than the true chances would justify, and the difference — a few percent of everything staked — is the bookmaker's income. It has several names: the **margin**, the **overround**, the **vig** or **vigorish**, the **juice**. They all mean the same thing, and it is the most important number in betting that nobody is shown.

## Finding the margin in any market

You can work it out yourself in a minute.

1. Turn each price into an implied probability: one divided by the decimal odds. (If odds are new to you, start with [how betting odds work](/articles/how-betting-odds-work).)
2. Add the probabilities for every possible outcome.
3. Whatever the total is above 100% is the overround.

A fair book adds up to exactly 100%, because exactly one thing will happen. A bookmaker's book always adds up to more.

### A two-way market

The standard price on an American point-spread bet is −110 on both sides, which is 1.91 in decimal.

| Outcome | Odds | Implied chance |
| --- | --- | --- |
| Team A covers | 1.91 | 52.4% |
| Team B covers | 1.91 | 52.4% |
| **Total** | | **104.8%** |

The overround is 4.8%. Put another way: stake 110 on each side, 220 in all, and whichever wins returns 210. The bookmaker keeps 10 of every 220, about 4.5% of the money staked, whatever happens.

### A three-way market

A football match can be a home win, a draw or an away win.

| Outcome | Odds | Implied chance |
| --- | --- | --- |
| Home | 2.10 | 47.6% |
| Draw | 3.40 | 29.4% |
| Away | 3.60 | 27.8% |
| **Total** | | **104.8%** |

Same idea, same answer: about 4.8% over, so about 4.6% of all stakes kept.

### Overround and margin are not quite the same number

The overround is how far the book is above 100%. The margin — the share of stakes the bookmaker expects to keep — is slightly smaller:

> **margin = 1 − (1 ÷ total implied probability)**

A book of 104.8% keeps 1 − 1/1.048 = 4.6%. A book of 110% keeps 9.1%. A book of 125%, which is not unusual in a market with many runners, keeps a fifth of everything staked. The two figures sit close together when the margin is small and drift apart as it grows, which is worth knowing when somebody quotes you one of them.

## The margin is not the same everywhere

Three patterns hold in almost every betting market.

**The more outcomes, the bigger the margin.** A two-way bet on a major match is the keenest price a bookmaker offers. A market with twenty possible winners — a tournament outright, a race with a big field — usually carries several times the margin, because a few percent shaved off each of twenty prices adds up, and because it is much harder for a customer to notice.

**The more obscure the event, the bigger the margin.** Big matches attract a lot of money and a lot of competition between bookmakers. A lower-league fixture or a novelty market attracts neither, and is priced accordingly.

**Long shots carry more than favourites.** The margin is not spread evenly. Prices on outsiders are shortened more than prices on favourites — partly because people like long shots and will take them anyway. This is one of the oldest findings in the study of betting markets, and it has a name: the favourite–longshot bias.

## What it costs, in money

A margin of 4.5% sounds small, and on one bet it is invisible. Luck swamps it: you win or you lose, and either way the 4.5% is not what you notice.

It shows up over time, because luck averages out and the margin does not. It is charged on every bet, win or lose, and it is charged on *turnover* — on the total amount staked, not on the money you started with.

That last point is the one people miss. Suppose you start a month with 100 and bet it, win some, bet the winnings, lose some, and keep going. By the end of the month you might have staked 1,000 in total without ever having more than 150 in the account. The margin is 4.5% of the 1,000, not of the 100: an expected cost of 45, from a float of 100.

| Total staked over a year | Expected cost at 4.5% | At 10% |
| --- | --- | --- |
| 500 | 23 | 50 |
| 2,000 | 90 | 200 |
| 10,000 | 450 | 1,000 |
| 50,000 | 2,250 | 5,000 |

These are averages. Any one person's year will be better or worse, sometimes much better. But nobody's *long run* escapes them unless their judgement is better than the bookmaker's by more than the margin — consistently, across hundreds of bets.

## Why it compounds

There is one more property of the margin worth understanding, because it is the basis of the most heavily promoted product in modern betting.

When several bets are combined on one slip — a parlay, an accumulator, a same-game multi — the odds are multiplied together. So are the margins. If each pick returns, on average, 95.5% of what a fair price would, then two picks return 95.5% of 95.5%, and so on:

| Picks on the slip | Average share of stakes kept |
| --- | --- |
| 1 | 4.5% |
| 2 | 8.8% |
| 3 | 12.9% |
| 5 | 20.6% |
| 8 | 30.8% |
| 10 | 36.9% |

Nothing on the slip tells you this. The potential payout gets bigger and more exciting with every pick added, and the price gets worse at exactly the same rate. The published figures agree with the arithmetic: in Nevada, the sportsbooks' share of money staked on parlay cards has been higher than their share of sports betting as a whole in every year since records by sport began in 1992. We look at the evidence in [why parlays are the worst bet on the menu](/articles/why-parlays-are-a-bad-bet).

## Can the margin be beaten?

In principle, yes: if you can judge probabilities better than the bookmaker by more than their margin, you have an edge. A small number of people do, and it is close to a full-time job involving models, data and many accounts.

Two things are worth knowing before taking that as encouragement.

First, the bookmaker is not guessing. The prices on a major market are set by specialists and then corrected by the weight of money from everyone else. To beat them you are not competing with the person behind the counter. You are competing with the market.

Second, bookmakers restrict or close the accounts of customers who cost them money, and winning is the usual way to do that. When Britain's gambling regulator asked operators for their own figures in 2025, it found that 47% of the accounts they had restricted were in profit, against 25% of accounts in general. The commonest restriction was a cap on how much the customer could stake, sometimes of zero. The business is designed around customers who lose at roughly the rate of the margin, and it is entitled to turn away the ones who do not.

For nearly everyone, then, the honest way to think about a bet is as a purchase. You are paying about 5% of your stake, on average, for some entertainment — more for long shots, much more for multiples. Whether that is a fair price for the fun is a personal matter. It is only a problem when the cost is hidden, or when it stops being fun.

## What fair odds look like

A fair price is one divided by the true probability, with nothing folded in. Every outcome in the market adds up to exactly 100%, and a customer backing things at random would, on average, finish where they started.

That is what prediction markets aim at, and it is what this site uses. Forecasts here are made in points that have no cash value, so there is no business to fund: every price is exactly one divided by the market's probability, at any number of picks. The reality check on your account shows your own record next to what the same record would have cost at a bookmaker's margin — the one number a betting site has no reason to show you.

## The short version

- The bookmaker's income is built into the odds. It is called the margin, overround or vig.
- To find it, add up the implied chance of every outcome. Anything over 100% is the bookmaker's.
- It is larger in markets with many outcomes, in obscure events, and on long shots.
- It is charged on everything you stake, not on what you deposit, so it adds up quickly.
- Combine bets on one slip and the margins multiply.
