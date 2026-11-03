# Research queue

One item per RESEARCH wake. Strike items through when done and link the report.

1. Indicator audit: `engine/indicators.py` RSI(14), MACD(12,26,9), ATR(14) and Bollinger(20,2) against Binance.US chart values on ADA/USD and BNB/USD, closed 15 minute and 1 hour candles.
2. Fill model calibration: once the collector has two weeks of order book and trade data, measure how often a resting maker order at N ticks from the touch actually fills, per pair. The backtester's fill model comes from this.
3. Range grid on ADA/USD and BNB/USD: calm periods only, with stops and band exits, mark to market, against holding.
4. Swing entries on pullbacks in trending periods, ADA/USD and BNB/USD, taker exits at today's fees.
5. Regime classifier: can the watcher's snapshot features predict the next 24 hours' volatility better than "same as today"? If not, say so and stop.
6. Watchlist review: the most liquid USD pairs on Binance.US by spread and depth. Recommend at most four.
