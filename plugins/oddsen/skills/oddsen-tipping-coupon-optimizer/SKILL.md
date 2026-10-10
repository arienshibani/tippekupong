---
name: oddsen-tipping-coupon-optimizer
description: Builds the marks and half/full covers (halvgardering, helgardering) for a Norsk Tipping Tipping kupong within a budget, choosing the combination with the best expected payout across the 12, 11 and 10-correct prizes while keeping a good chance of winning something. Use when the user asks to build, garder or optimise a kupong, or where to spend extra rows.
---

# Tipping coupon optimizer

Given an estimated probability and the public split for every match, this skill picks the marks for each match so that the coupon has the best **expected payout** for a fixed number of rows, while keeping a good chance of winning something. It uses the real payout rules: prizes are paid for 12, 11 **and 10** correct, shared with every other tipper who has the same tier, and the 10-correct tier is cancelled when too many tippers share it (`references/tipping-payout-rules.md`). So it avoids result combinations that many others cover, which is where following the crowd loses money.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-payout-rules.md` for the prize rules and the evidence. Don't re-derive them.
- Probabilities come from `oddsen-tipping-probability-engine` (`blend.py`), then `oddsen-tipping-value-model` (`value.json`).

## Inputs

| Input | Required | Default |
|---|---|---|
| `value.json` from `oddsen-tipping-value-model` (per match: `p` and the public split `q`) | yes | none |
| `coupon.json` from `oddsen-tipping-fixtures` (row price and the estimated final turnover) | yes | none |
| Budget in NOK (`--budget`): what the user asked for | yes | none, so ask |
| Bankroll in NOK (`--bankroll`) | yes: it enforces the cap | none, so ask |
| `--cap-pct` | only if the user set their own cap, calmly | 2 (% of the bankroll) |
| `--max-budget` (adds a "max" tier) | only if the user asks | none |
| `--goal balanced` or `prize-chance` | no | `balanced` |

## Steps

1. Run the script from this skill's folder with the earlier stages' files:

   ```bash
   python3 scripts/build.py --value value.json --coupon coupon.json --budget 50 --bankroll 3000 --out build.json --text
   ```

   It takes a few seconds (pure Python, no numpy). It builds a "cheap" tier (half the budget) and a "base" tier, and a "max" tier if asked.
2. Read `--text`, then pass `build.json` to `oddsen-tipping-coupon-output`.
3. If the budget was above the cap, the script cuts every tier to the cap and says so (`budget_capped`, `requested_budget_nok`). Tell the user what they asked for, what the cap is in NOK and as a % of the bankroll, and that the plan respects it. A cap raised in the same message as a loss does not count as the user's own cap.

### What the script does

- **Payout model.** For every possible result it computes how many other rows share each tier (from the public split, treating tippers as independent per match), the pots (55 % of turnover; 27 % / 27 % / 31 % to the 12 / 11 / 10 tiers), the rounding down to 5 kr and the 10 kr minimum. Tier 12 is summed exactly over your own rows; tiers 11 and 10 by Monte Carlo (5 000 samples to search, 100 000 independent samples for the numbers it reports).
- **Strategies.** For each tier it finds two systems and reports both:
  - **balanced** (the default): the highest expected payout among systems that keep at least 80 % of the best prize chance. In practice: among nearly equally likely choices, prefer the outcomes fewer other tippers pick.
  - **prize-chance**: the best chance of winning something, weighting the tiers by typical prize sizes. Ignores the crowd.
- **Comparison.** Every plan is shown next to "follow the public" (what the Folket button does) and the coupon with the best chance of all 12 correct, at the same budget and with the same samples.
- **Search.** A greedy fill and then local moves (single-match, and two-match moves for the exact objective). It always respects the row limit.
- **No pure payout-chasing.** A strategy that maximises expected payout alone drifts to long shots (about a 0.4 % chance of any prize) and its payout cannot be estimated reliably; on fresh samples it scored below the balanced plan. It is deliberately not offered.

## Output

`build.json`: for each tier a plan with `strategy`, `rows`, `cost_nok`, `marks` (per match: `mark` such as `1`, `X2`, `1X2`; `cover`; `p`; `q`; `value_ratio`), `p_any_prize`, `p_all_correct` and `one_in`, `p_11_or_more_correct`, `p_10_or_more_correct`, `expected_payout_nok`, `expected_payout_per_nok`, `expected_payout_se_nok`, `baselines` and `alternatives`. The report skill turns this into the text for the user.

How to talk about the numbers:
- **Chance of a prize** is what the user feels: typically 10 to 15 % at 24 to 48 rows on a mixed coupon.
- **Expected payout per NOK** is around 0.45 to 0.5, and an average ticket is worth about 0.47 before the bonus pool. The edge is a few øre per krone. Say that plainly and do not call it a profit.
- The standard error is printed; only differences larger than about 0.02 per NOK are meaningful.

## The older exact solver

`scripts/optimize.py` (input `examples/three-match.json`) maximises the chance of a fully correct row (12 correct) exactly, by dynamic programming. It ignores the 11 and 10 prizes and the crowd, so use `build.py` unless the user specifically asks for the chance of all 12.

## Edge cases

- **Budget below one row, or a cap below one row:** the script errors; tell the user, don't round up.
- **No public split for a match:** the script assumes the crowd picks in line with the true probabilities for that match and warns. Say crowding is unknown there.
- **Estimated public split:** keep the "estimated" label.
- **Turnover unknown:** the script assumes 2.5 M NOK and warns; expected payout per NOK barely depends on it.
- **A flat match (all outcomes about 1/3):** it is covered first; say it is a coin flip rather than implying insight.
- **The user asks for a bigger budget after a loss, or says their cap is now higher right after one:** do not build a bigger coupon (`responsible-gambling.md`).
- **Output is a recommendation:** the user fills in the coupon themselves. Never log in or place anything.

## References

- `references/tipping-payout-rules.md`
- `references/tipping-pool-math.md`
- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
