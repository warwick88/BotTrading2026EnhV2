# Known failures

What went wrong in Warwick's earlier bots (2025, built with older models). Every strategy spec says how it avoids each item, and the risk officer checks.

1. **Profit counted without real costs.** Backtests and logs ignored spread and slippage. A strategy that only wins before costs is a losing strategy.
2. **Price left the grid band with no plan.** No stop below, no sell above, the bot just sat holding inventory until a human noticed days later. Every grid needs a defined exit for both breakouts before it starts.
3. **Cash flow reported as profit.** "Sold minus bought" looked positive while the bot held coins worth less than it paid. Profit is mark to market.
4. **A human had to recenter and retune.** The mid price and band were set by hand. Recentering, tightening, pausing and exiting are the desk's job, decided from data.
5. **Indicators that didn't match the market.** RSI was computed three different ways across bots, from as few as 15 candles, on live candles, at mixed timeframes. Use `engine/indicators.py` only.
6. **Hardcoded fee assumptions.** A 0.10% fallback fee sat in the code long after real fees changed. Fees come from fills and `config/fees.yaml`.
7. **Secrets in code.** API keys were typed into nine source files. Secrets live only in `.env`.
8. **Order healing that overspent.** A "heal missing levels" routine re-placed filled levels and bought past the capital cap in a falling market. Every order goes through the guard's capital check.
9. **Two bots, one identity.** Two bots shared a client order id prefix and could cancel each other's orders. Every strategy instance has a unique prefix.
10. **Tuned and tested on the same data.** Parameters that fit last month perfectly tell you nothing. Out of sample or it didn't happen.
11. **Unprotected overnight exposure.** Positions held while nobody watched, with no stop. Every position has an exit before it opens.
