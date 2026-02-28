# MyStrategyStrategy - Agent Guide

> AI coding agent context for the `my_strategy` strategy.

## Overview

- **Template:** blank
- **Chain:** base
- **Class:** `MyStrategyStrategy` in `strategy.py`
- **Config:** `config.json`
- **Default Pair:** DEGEN/USDC on Base
- **Default Protocol:** `uniswap_v3`

## Files

| File | Purpose |
|------|---------|
| `strategy.py` | Main strategy - edit `decide()` to change entry/exit logic |
| `config.json` | Runtime parameters (tokens, thresholds, protocol, risk) |
| `.env` | Secrets (private key, API keys) - never commit this |
| `tests/test_strategy.py` | Unit tests for the strategy |
| `README.md` | Project setup and runbook |

## How to Run

```bash
# Single iteration on Anvil fork (safe, no real funds)
almanak strat run --network anvil --once

# Single iteration on mainnet (managed gateway)
almanak strat run --once --gateway-port 50110

# Standalone gateway (Base only)
almanak gateway --port 50130 --chains base

# Dry run against existing gateway
almanak strat run --once --dry-run --no-gateway --gateway-port 50130

# Live run against existing gateway
almanak strat run --once --no-gateway --gateway-port 50130
```

## Intent Types Used

This strategy uses these intent types:

- `Intent.swap(from_token, to_token, amount_usd=, max_slippage=..., protocol=..., chain=...)`
- `Intent.swap(from_token, to_token, amount=, max_slippage=..., protocol=..., chain=...)`
- `Intent.hold(reason="...")`

All intents are created via `from almanak.framework.intents import Intent`.

## Key Patterns

- `decide(market)` receives a `MarketSnapshot` with `market.price()`, `market.balance()`, `market.rsi()`, etc.
- Return an `Intent` object or `Intent.hold(reason=...)` from `decide()`
- Always wrap `decide()` logic in try/except, returning `Intent.hold()` on error
- Config values are read via `self.config.get("key", default)` in `__init__`
- State persists between iterations via `self.state` dict
- Strategy prints `[STATUS]` for price/balance/portfolio/profit and `[ACTION]` for BUY/SELL/HOLD/ERROR decisions
- Token handling supports symbol and address fallback for price, balance, and RSI queries.
- Persistent keys include `entry_price`, `entry_ts`, and `last_buy_ts`.

## Testing

```bash
# Run unit tests
uv run pytest tests/ -v

# Paper trade (Anvil fork with PnL tracking)
almanak strat backtest paper --duration 3600 --interval 60

# PnL backtest (historical prices)
almanak strat backtest pnl --start 2024-01-01 --end 2024-06-01
```

## Environment Notes

- For live execution, both strategy and gateway need a private key: `ALMANAK_PRIVATE_KEY` and `ALMANAK_GATEWAY_PRIVATE_KEY`.
- If gateway auth is enabled, set both `ALMANAK_GATEWAY_AUTH_TOKEN` and `GATEWAY_AUTH_TOKEN`.
- `ALMANAK_GATEWAY_ALLOW_INSECURE=true` is for local testing only.

## Full SDK Reference

For the complete intent vocabulary, market data API, and advanced patterns,
install the full agent skill:

```bash
almanak agent install
```

Or read the bundled skill directly:

```bash
almanak docs agent-skill --dump
```
