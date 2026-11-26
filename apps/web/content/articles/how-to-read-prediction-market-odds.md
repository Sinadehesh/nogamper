---
title: "What a 70% chance really means: how to read prediction market odds"
description: "A 70% forecast that fails was not necessarily wrong. How to read a prediction market price, what calibration is, and how to tell skill from luck in your own record."
topic: prediction-markets
published: 2026-11-26
updated: 2026-11-26
sources:
  - label: "Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. Monthly Weather Review, 78(1), 1–3."
    href: "https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2"
  - label: "Page, L. & Clemen, R. T. (2013). Do prediction markets produce well-calibrated probability forecasts? The Economic Journal, 123(568), 491–513."
    href: "https://doi.org/10.1111/j.1468-0297.2012.02561.x"
  - label: "Wolfers, J. & Zitzewitz, E. (2006). Interpreting prediction market prices as probabilities. NBER Working Paper 12200."
    href: "https://doi.org/10.3386/w12200"
  - label: "Manski, C. F. (2006). Interpreting the predictions of prediction markets. Economics Letters, 91(3), 425–429."
    href: "https://doi.org/10.1016/j.econlet.2006.01.004"
  - label: "Snowberg, E. & Wolfers, J. (2010). Explaining the favorite–long shot bias: is it risk-love or misperceptions? Journal of Political Economy, 118(4), 723–746."
    href: "https://doi.org/10.1086/655844"
  - label: "Mellers, B. et al. (2014). Psychological strategies for winning a geopolitical forecasting tournament. Psychological Science, 25(5), 1106–1115."
    href: "https://doi.org/10.1177/0956797614524255"
---

A market says something has a 70% chance of happening. It does not happen. Was the market wrong?

Probably not — and seeing why is the difference between reading a forecast and misreading one. (If the idea of a price as a probability is new, start with [what a prediction market is](/articles/what-is-a-prediction-market).)

## A price is a probability, not a verdict

In a prediction market, a share that pays 1 if something happens trades somewhere between 0 and 1. A price of 0.70 means the people trading it, taken together, think the thing is about 70% likely. That is all it means.

It is tempting to round that to “yes”. Resist it. Put ten balls in a bag, three of them red, and draw one. Seventy percent is the chance it is not red — likely, and you would not be astonished to see red. If you treat every 70% as a certainty you will be wrong about three times in ten, and it will feel as though the forecasts are broken when they are behaving exactly as advertised.

A useful habit is to say the other half out loud. Not “70% it happens” but “**30% it doesn't**”. Three in ten is not a long shot. It is roughly the chance of rain on a day you would still think about a coat.

| The price says | Out of 100 such forecasts, expect about |
| --- | --- |
| 95% | 5 to fail |
| 80% | 20 to fail |
| 70% | 30 to fail |
| 55% | 45 to fail — barely better than a coin |
| 10% | 10 to *come in* |

That last row matters as much as the first. A 10% outcome arriving is not a miracle. It is the thing that happens one time in ten.

## You cannot judge one forecast

Here is the uncomfortable part: a single forecast cannot be marked right or wrong, unless it was 0% or 100%.

If a market said 70% and the thing happened, that is consistent with 70% being correct. It is also consistent with the true chance having been 40% and the market getting lucky. One result does not tell you which.

What you *can* judge is a pile of forecasts. Gather every question that was priced near 70% and count how many happened. If the answer is close to seventy in a hundred, the forecaster is **calibrated**: their 70% means 70%. If only fifty in a hundred happened, their “70%” is overconfident, and should be read as something closer to a coin toss.

This is how weather forecasters are assessed, and it is the fairest test there is. It does not ask whether you were right. It asks whether your confidence was *earned*.

## Calibration is not the whole of skill

A forecaster who says “50%” to every yes-or-no question about coin tosses is perfectly calibrated and has told you nothing. Calibration is necessary and it is not enough.

The other half is sometimes called **resolution**: the willingness to move away from the middle when there is reason to, and be right about it. A good forecaster says 90% about things that mostly happen and 10% about things that mostly do not, and both numbers hold up.

The standard way of scoring both at once was worked out for weather forecasts in 1950 by a meteorologist called Glenn Brier. A Brier score is simply the average squared distance between what you said and what happened: say 70% for something that happens and you score (1 − 0.7)² = 0.09; say 70% for something that does not and you score (0 − 0.7)² = 0.49. Lower is better. Guessing 50% for everything earns 0.25 every time, so anything consistently below that is real information.

The beauty of the squared distance is that it punishes confident mistakes much harder than timid ones — which is exactly the right thing to punish.

## Where market prices lean

Prices from a busy market are, on the whole, well calibrated. Things priced at 70% happen about 70% of the time. But a few lean in predictable directions, and knowing them helps you read a price properly.

**Cheap long shots are a bit too dear.** A share at 2% often belongs nearer 1%. People enjoy a small stake with a large payout, and there is little money to be made correcting a price that low, so it drifts up. The same pattern has been found at racecourses for decades.

**Near-certainties are a bit too cheap.** The mirror image: something at 97% is often really 98% or 99%. Tying up money for months to earn two percent is unattractive, so the price sits slightly low.

**Thin markets wobble.** A price set by a dozen traders can be moved by one of them. Look at how much has been traded before trusting the decimal places.

**Far-off questions are vaguer than they look.** A price on something a year away carries a great deal of uncertainty that a single number hides. It will move, possibly a long way, and that movement is the market learning, not the market being wrong before.

**Prices are not quite probabilities.** Strictly, a price reflects both what traders believe and how much they are prepared to risk. Economists have argued about how far apart those can drift; the practical conclusion is that for most markets they sit close together. Read 63% as “about three in five” rather than as a reading off an instrument.

## Reading your own record

Everything above applies to you as much as to a market, and this is where it gets useful.

After twenty or thirty forecasts, look at them in bands. Of the things you backed at around 80%, did about four in five come in? If fewer did, you are overconfident there — the commonest finding, by a distance. Of the long shots you fancied at 15%, did roughly one in seven land, or almost none?

Two patterns show up in nearly everyone:

- **Overconfidence at the top.** Things we are “sure” about happen less often than we think.
- **Wishful thinking.** Forecasts about our own team, our own side of an argument or our own investments are worse than our forecasts about things we do not care about.

Neither is a flaw of character. They are the default settings, and the only known cure is feedback: making a specific forecast, writing it down, and finding out. Researchers who ran large forecasting tournaments found that the people who did best were not those with special knowledge. They were the ones who kept score, thought in specific numbers, and changed their minds in small steps when the evidence moved.

On this site, the reality check on the safer-play page does this sum for you: it groups your settled forecasts by the chance you took them at, and shows how often each group came in beside how often it should have.

## A short checklist

When you look at a price, ask:

1. **What is the other half?** 70% for means 30% against. Is that a surprise you could live with?
2. **How busy is this market?** Much traded, or barely?
3. **How far away is the answer?** The further, the looser the number.
4. **Is it at an extreme?** Shade long shots down and near-certainties up, a little.
5. **Do I know something the price does not?** If the honest answer is no, the price is probably a better estimate than your hunch.

That last question is the humbling one, and the most valuable.

You do not need to trade anything to use any of this: the prices on the big markets are public. Our [guide to the main sites](/articles/best-prediction-markets) says where to find them, and which are played with money and which are not.

## The short version

- A price is the crowd's estimate of a chance, not a prediction of what will happen.
- 70% fails three times in ten. That is the forecast working, not failing.
- Forecasts can only be judged in bulk: of everything said at 70%, did about 70% happen?
- Markets lean slightly: long shots overpriced, near-certainties underpriced, thin markets noisy.
- The way to get better is to write the number down and check it later.
