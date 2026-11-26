---
title: "How betting odds work, and how to read the chance hidden in them"
description: "Decimal, fractional and American odds are three ways of writing one number. How to convert between them, and how to turn any price into the probability it implies."
topic: odds
published: 2026-11-26
updated: 2026-11-26
sources:
  - label: "Štrumbelj, E. (2014). On determining probability forecasts from betting odds. International Journal of Forecasting, 30(4), 934–943."
    href: "https://doi.org/10.1016/j.ijforecast.2014.02.008"
  - label: "Snowberg, E. & Wolfers, J. (2010). Explaining the favorite–long shot bias: is it risk-love or misperceptions? Journal of Political Economy, 118(4), 723–746."
    href: "https://doi.org/10.1086/655844"
---

Odds look like a prediction. They are really a price: what a bookmaker will pay you, per unit staked, if you turn out to be right. Hidden inside every price is a probability, and learning to pull it out is the single most useful thing you can know about betting — mostly because of what it shows you.

This guide covers the three ways odds are written, how to convert each into a percentage, and why the percentages never quite add up.

## Three ways of writing the same thing

Take a bet that returns £2.50 in total for every £1 staked — your £1 back, plus £1.50 profit. That one price can be written three ways.

| Format | Written as | What the number means |
| --- | --- | --- |
| Decimal | 2.50 | Total returned per 1 staked, stake included |
| Fractional | 6/4 | Profit per stake: win 6 for every 4 staked |
| American | +150 | Profit on a stake of 100 |

**Decimal odds** are the simplest and the most common outside the UK and the US. Multiply your stake by the number and that is what comes back. Anything below 2.00 is a favourite; anything above is an outsider.

**Fractional odds** are traditional in Britain and Ireland, especially in racing. The fraction is profit over stake. “5/1” pays five for every one staked. “1/2” — said “two to one on” — pays one for every two staked, so it is a strong favourite.

**American odds** come in two flavours. A plus number is the profit on a stake of 100: +150 wins 150 from 100. A minus number is the stake needed to win 100: −200 means you must put up 200 to win 100.

### Converting between them

Everything is easiest if you go through decimal.

- **Fractional to decimal:** divide the fraction and add one. 6/4 is 1.5, plus 1, is 2.50.
- **American plus to decimal:** divide by 100 and add one. +150 becomes 2.50.
- **American minus to decimal:** divide 100 by the number (ignoring the sign) and add one. −200 becomes 1.50.

## From a price to a probability

Here is the part worth remembering. For decimal odds:

> **implied probability = 1 ÷ decimal odds**

Odds of 2.00 imply 50%. Odds of 4.00 imply 25%. Odds of 1.25 imply 80%.

| Decimal | Fractional | American | Implied chance |
| --- | --- | --- | --- |
| 1.20 | 1/5 | −500 | 83.3% |
| 1.50 | 1/2 | −200 | 66.7% |
| 1.91 | 10/11 | −110 | 52.4% |
| 2.00 | Evens | +100 | 50.0% |
| 3.00 | 2/1 | +200 | 33.3% |
| 5.00 | 4/1 | +400 | 20.0% |
| 11.00 | 10/1 | +1000 | 9.1% |
| 101.00 | 100/1 | +10000 | 1.0% |

The implied probability is the break-even point. If you back something at 4.00 and it wins more than one time in four, you come out ahead over the long run. If it wins less often than that, you lose. Nothing else about the bet matters as much as that comparison: *is this more likely than the price says?*

## Why the percentages do not add up to 100

Now try it on both sides of a simple bet. A tennis match has two possible winners, so the two chances must add up to 100%. A typical pair of prices:

| Player | Decimal odds | Implied chance |
| --- | --- | --- |
| Player A | 1.57 | 63.7% |
| Player B | 2.40 | 41.7% |
| **Total** | | **105.4%** |

One hundred and five percent. That extra 5.4% is not a rounding error. It is the bookmaker's margin, sometimes called the overround or the vig, and it is how they are paid: every price on the board is a little shorter than the true chance would justify, so that the book as a whole pays out less than it takes in.

The standard American point-spread price shows it most plainly. Both sides of a bet designed to be a coin toss are offered at −110, which is 1.91 in decimal and 52.4% in implied chance. Two coin-toss outcomes at 52.4% each make 104.8%. To break even at those prices you need to be right 52.4% of the time, on something that is, by construction, close to fifty-fifty.

We take the margin apart properly in [the bookmaker's margin, explained](/articles/bookmaker-margin-explained), including the awkward thing that happens to it when you combine bets — which is the subject of [why parlays are the worst bet on the menu](/articles/why-parlays-are-a-bad-bet).

## Getting back to the real chance

If you want the bookmaker's actual opinion rather than their price, divide each implied probability by the total. For the tennis match:

- Player A: 63.7 ÷ 105.4 = **60.4%**
- Player B: 41.7 ÷ 105.4 = **39.6%**

That simple method spreads the margin evenly across the outcomes. It is a reasonable first approximation and it is what most people use. Researchers who have tested it against real results find it is slightly off in one consistent direction: bookmakers tend to load more of their margin onto outsiders than onto favourites, so long shots are a worse deal than the even-handed arithmetic suggests. The rule of thumb that follows is an old one — the longer the odds, the more you are paying for the ticket.

## What fair odds would look like

Strip the margin out and you have fair odds: one divided by the true probability, nothing more. A genuine 50% chance pays 2.00. A 25% chance pays 4.00. Back a hundred such bets and, on average, you finish where you started — which is exactly what “fair” means.

No bookmaker can offer that and stay in business, which is not a criticism. It is simply what the product is. A betting price is a fair price with a fee folded into it, and the fee is invisible unless you do the sum above.

It is also why this site can do something a bookmaker cannot. Forecasts here are made with points that have no cash value, so there is no business to fund and no reason for a margin. Every price is exactly one divided by the market's probability, and the two sides of every question add up to 100%.

## The short version

- Decimal, fractional and American odds are the same price written three ways.
- One divided by the decimal odds is the chance you need to beat to break even.
- Add up the implied chances of every outcome and you get more than 100%. The excess is the bookmaker's margin.
- Long shots usually carry more of that margin than favourites.
- Fair odds add up to exactly 100% — and are not something a business that takes bets can sell.
