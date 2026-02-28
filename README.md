# Almanak Strategy

Automated DEGEN/USDC strategy on Base using the Almanak SDK.

## What This Strategy Does

- Chain: Base
- Pair: DEGEN / USDC
- Entry: Buys when RSI is below `buy_rsi`
- Exit rules: take profit at `take_profit_pct`, stop loss at `stop_loss_pct`, and time-based profit exit at `max_hold_minutes`
- Position sizing and risk use `trade_amount_usd` (with optional compounding), enforce `min_trade_amount_usd`, use separate buy/sell slippage, include exit retry cooldown/escalation, and apply a gas guard for low-edge trades.

Current defaults in [config.json](/Users/0xgets/my_strategy/config.json) are tuned for small-size testing (`$1`).

## Compounding Behavior

When `compound_profits` is enabled, buy size can increase from realized portfolio profit:

- Base buy size starts from `trade_amount_usd`
- Extra size is `max(0, total_profit_usd) * compound_factor`
- Example: if base is `$1.00` and profit is `$0.10`, next target buy is about `$1.10`

Use `max_trade_amount_usd` to cap compounding size.

## Gas Guard

Gas guard helps avoid trades where expected edge is too small for gas cost.

Key config fields:

- `enable_gas_guard`
- `estimated_buy_gas_usd`
- `estimated_sell_gas_usd`
- `gas_safety_multiplier`
- `min_net_profit_usd`

If the guard blocks a trade, logs show an `[ACTION] HOLD` reason.

## Project Files

- [strategy.py](/Users/0xgets/my_strategy/strategy.py): main strategy logic
- [config.json](/Users/0xgets/my_strategy/config.json): runtime parameters
- [.env](/Users/0xgets/my_strategy/.env): secrets and gateway/rpc settings (do not commit)
- [tests/test_strategy.py](/Users/0xgets/my_strategy/tests/test_strategy.py): unit tests
- [AGENTS.md](/Users/0xgets/my_strategy/AGENTS.md): coding agent guidance

## Setup

1. Install dependencies in your virtualenv.
2. Configure `.env` with at least:

```bash
ALMANAK_PRIVATE_KEY=0x...
ALMANAK_GATEWAY_PRIVATE_KEY=0x...
ALMANAK_GATEWAY_AUTH_TOKEN=your_token_here
GATEWAY_AUTH_TOKEN=your_token_here
ALMANAK_BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/...
```

If you run a local gateway without auth for testing only:

```bash
ALMANAK_GATEWAY_ALLOW_INSECURE=true
```

## Run Commands

Safe dry run on managed gateway:

```bash
almanak strat run --once --dry-run
```

Use an existing gateway:

```bash
almanak strat run --once --dry-run --no-gateway --gateway-port 50130
```

Live single iteration (real execution):

```bash
almanak strat run --once --no-gateway --gateway-port 50130
```

Start standalone gateway on Base:

```bash
almanak gateway --port 50130 --chains base
```

## Notes

- Strategy logs print status and action decisions every iteration.
- State persists in `almanak_state.db` and resumes open-position context.
- This is not guaranteed-profit software. Use dry-run and small size before scaling.
