import time
from decimal import Decimal, InvalidOperation
from typing import Any

from almanak.framework.intents import Intent
from almanak.framework.strategies.intent_strategy import IntentStrategy


class MyStrategyStrategy(IntentStrategy):
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        chain: str = "base",
        wallet_address: str = "",
        **kwargs: Any,
    ) -> None:
        cfg = config or {}
        super().__init__(config=cfg, chain=chain, wallet_address=wallet_address, **kwargs)

        self.author = cfg.get("author", "0x94t3z")
        self.base_token_symbol = str(cfg.get("base_token", "DEGEN")).strip().lstrip("$").upper()
        self.base_token_address = str(cfg.get("base_token_address", "")).strip()
        token_id = self.base_token_address if self.base_token_address.startswith("0x") else self.base_token_symbol
        self.base_token = self.base_token_symbol
        self.base_token_price_id = str(cfg.get("base_token_price_id", self.base_token_symbol)).strip() or self.base_token_symbol
        self.base_token_rsi_id = token_id
        self.base_token_balance_id = token_id
        self.base_token_trade_id = token_id
        self.quote_token_symbol = str(cfg.get("quote_token", "USDC")).strip().lstrip("$").upper()
        self.quote_token_address = str(cfg.get("quote_token_address", "")).strip()
        self.quote_token = (
            self.quote_token_address
            if self.quote_token_address.startswith("0x")
            else self.quote_token_symbol
        )
        self.swap_protocol = str(cfg.get("swap_protocol", "aerodrome")).strip().lower() or "aerodrome"
        self.base_token_decimals = int(cfg.get("base_token_decimals", 18))
        self.base_token_coingecko_id = str(cfg.get("base_token_coingecko_id", "degen-base")).strip() or None
        self._register_base_token()
        self.rsi_period = int(cfg.get("rsi_period", 14))
        self.rsi_timeframe = str(cfg.get("rsi_timeframe", "1h"))
        self.buy_rsi = self._to_decimal(cfg.get("buy_rsi", 38), Decimal("38"))
        self.trade_amount_usd = self._to_decimal(cfg.get("trade_amount_usd", 250), Decimal("250"))
        self.max_trade_amount_usd = self._to_decimal(cfg.get("max_trade_amount_usd", "0"), Decimal("0"))
        self.min_trade_amount_usd = self._to_decimal(cfg.get("min_trade_amount_usd", "1"), Decimal("1"))
        self.min_quote_reserve_usd = self._to_decimal(cfg.get("min_quote_reserve_usd", "0"), Decimal("0"))
        self.starting_capital_usd = self._to_decimal(
            cfg.get("starting_capital_usd", self.trade_amount_usd),
            self.trade_amount_usd,
        )
        self.take_profit_pct = self._to_decimal(cfg.get("take_profit_pct", "0.03"), Decimal("0.03"))
        self.stop_loss_pct = self._to_decimal(cfg.get("stop_loss_pct", "0.02"), Decimal("0.02"))
        self.max_hold_minutes = int(cfg.get("max_hold_minutes", 1440))
        self.cooldown_minutes = int(cfg.get("cooldown_minutes", 30))
        self.sell_fraction = self._to_decimal(cfg.get("sell_fraction", "1.0"), Decimal("1.0"))
        self.min_base_position = self._to_decimal(cfg.get("min_base_position", "0.000001"), Decimal("0.000001"))
        self.max_slippage = self._to_decimal(cfg.get("max_slippage", "0.005"), Decimal("0.005"))
        self.buy_max_slippage = self._to_decimal(cfg.get("buy_max_slippage", self.max_slippage), self.max_slippage)
        default_sell_slippage = self.max_slippage if self.max_slippage >= Decimal("0.03") else Decimal("0.03")
        self.sell_max_slippage = self._to_decimal(cfg.get("sell_max_slippage", default_sell_slippage), default_sell_slippage)
        self.failed_exit_max_slippage = self._to_decimal(
            cfg.get("failed_exit_max_slippage", self.sell_max_slippage),
            self.sell_max_slippage,
        )
        if self.failed_exit_max_slippage < self.sell_max_slippage:
            self.failed_exit_max_slippage = self.sell_max_slippage
        self.exit_retry_cooldown_minutes = int(cfg.get("exit_retry_cooldown_minutes", 5))
        self.exit_escalation_window_minutes = int(cfg.get("exit_escalation_window_minutes", 20))
        self.compound_profits = bool(cfg.get("compound_profits", True))
        self.compound_factor = self._to_decimal(cfg.get("compound_factor", "1.0"), Decimal("1.0"))
        self.enable_gas_guard = bool(cfg.get("enable_gas_guard", True))
        self.estimated_buy_gas_usd = self._to_decimal(cfg.get("estimated_buy_gas_usd", "0.03"), Decimal("0.03"))
        self.estimated_sell_gas_usd = self._to_decimal(cfg.get("estimated_sell_gas_usd", "0.03"), Decimal("0.03"))
        self.gas_safety_multiplier = self._to_decimal(cfg.get("gas_safety_multiplier", "2.0"), Decimal("2.0"))
        self.min_net_profit_usd = self._to_decimal(cfg.get("min_net_profit_usd", "0.03"), Decimal("0.03"))
        self.enforce_profit_only_exit = bool(cfg.get("enforce_profit_only_exit", False))

        self._entry_price: Decimal | None = None
        self._entry_ts: int | None = None
        self._last_buy_ts: int | None = None
        self._last_exit_attempt_ts: int | None = None
        self._last_exit_reason: str | None = None
        self._last_portfolio_value_usd = Decimal("0")
        self._last_total_profit_usd = Decimal("0")
        self._last_total_profit_pct = Decimal("0")

    @staticmethod
    def _to_decimal(value: Any, default: Decimal) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default

    def _extract_balance(self, balance_obj: Any) -> Decimal:
        if hasattr(balance_obj, "balance"):
            return self._to_decimal(balance_obj.balance, Decimal("0"))
        return self._to_decimal(balance_obj, Decimal("0"))

    def _balance_with_fallback(self, market: Any, *token_ids: str) -> Decimal:
        for token_id in token_ids:
            if not token_id:
                continue
            try:
                return self._extract_balance(market.balance(token_id))
            except Exception:
                continue
        return Decimal("0")

    def _extract_rsi(self, rsi_obj: Any) -> Decimal | None:
        if rsi_obj is None:
            return None
        if hasattr(rsi_obj, "value"):
            return self._to_decimal(rsi_obj.value, Decimal("0"))
        return self._to_decimal(rsi_obj, Decimal("0"))

    def _register_base_token(self) -> bool:
        if not self.base_token_address.startswith("0x"):
            return False

        try:
            from almanak.core.enums import Chain
            from almanak.framework.data.tokens.models import CHAIN_ID_MAP, ResolvedToken
            from almanak.framework.data.tokens.resolver import get_token_resolver

            chain_enum = Chain(self.chain.upper())
            chain_id = CHAIN_ID_MAP.get(chain_enum, 0)
            if chain_id == 0:
                return False

            resolver = get_token_resolver()
            resolver.register(
                ResolvedToken(
                    symbol=self.base_token_symbol,
                    address=self.base_token_address,
                    decimals=self.base_token_decimals,
                    chain=chain_enum,
                    chain_id=chain_id,
                    name=self.base_token_symbol,
                    coingecko_id=self.base_token_coingecko_id,
                    source="manual",
                    is_verified=False,
                )
            )
            return True
        except Exception as exc:
            self._print_action("WARN", f"Token register failed for {self.base_token_symbol}: {exc}")
            return False

    def _print_status(
        self,
        price: Decimal,
        quote_balance: Decimal,
        base_balance: Decimal,
        rsi: Decimal,
    ) -> None:
        print(
            f"[STATUS] {self.base_token_symbol}@{price:.8f} | RSI={rsi} | "
            f"{self.quote_token_symbol}={quote_balance:.4f} | {self.base_token_symbol}={base_balance:.6f} | "
            f"Portfolio=${self._last_portfolio_value_usd:.2f} | "
            f"Profit=${self._last_total_profit_usd:.2f} ({self._last_total_profit_pct * Decimal('100'):.2f}%)"
        )

    @staticmethod
    def _print_action(action: str, reason: str) -> None:
        print(f"[ACTION] {action}: {reason}")

    def get_persistent_state(self) -> dict[str, Any]:
        return {
            "entry_price": str(self._entry_price) if self._entry_price is not None else None,
            "entry_ts": self._entry_ts,
            "last_buy_ts": self._last_buy_ts,
            "last_exit_attempt_ts": self._last_exit_attempt_ts,
            "last_exit_reason": self._last_exit_reason,
        }

    def load_persistent_state(self, state: dict[str, Any]) -> None:
        self._entry_price = self._to_decimal(state.get("entry_price"), Decimal("0")) if state.get("entry_price") else None
        self._entry_ts = state.get("entry_ts")
        self._last_buy_ts = state.get("last_buy_ts")
        self._last_exit_attempt_ts = state.get("last_exit_attempt_ts")
        self._last_exit_reason = state.get("last_exit_reason")

    def _compute_buy_amount_usd(self, quote_balance: Decimal) -> Decimal:
        spendable = quote_balance - self.min_quote_reserve_usd
        if spendable <= 0:
            return Decimal("0")
        if not self.compound_profits:
            target = self.trade_amount_usd
        else:
            profit_component = max(Decimal("0"), self._last_total_profit_usd) * self.compound_factor
            target = self.trade_amount_usd + profit_component
        if self.max_trade_amount_usd > 0:
            target = min(target, self.max_trade_amount_usd)
        return min(target, spendable)

    def _round_trip_gas_buffer_usd(self) -> Decimal:
        return (self.estimated_buy_gas_usd + self.estimated_sell_gas_usd) * self.gas_safety_multiplier

    def _sell_gas_buffer_usd(self) -> Decimal:
        return self.estimated_sell_gas_usd * self.gas_safety_multiplier

    def _entry_passes_gas_guard(self, buy_amount_usd: Decimal) -> tuple[bool, str]:
        if not self.enable_gas_guard:
            return True, ""
        expected_gross_profit = buy_amount_usd * self.take_profit_pct
        required_profit = self._round_trip_gas_buffer_usd() + self.min_net_profit_usd
        if expected_gross_profit >= required_profit:
            return True, ""
        return (
            False,
            (
                f"Gas guard blocked buy: expected_profit=${expected_gross_profit:.4f} "
                f"< required=${required_profit:.4f}"
            ),
        )

    def _exit_passes_gas_guard(self, pnl_usd: Decimal) -> tuple[bool, str]:
        if not self.enable_gas_guard:
            return True, ""
        required_profit = self._sell_gas_buffer_usd() + self.min_net_profit_usd
        if pnl_usd >= required_profit:
            return True, ""
        return (
            False,
            (
                f"Gas guard blocked sell: pnl=${pnl_usd:.4f} "
                f"< required=${required_profit:.4f}"
            ),
        )

    def _can_retry_exit(self, now_ts: int) -> bool:
        if self._last_exit_attempt_ts is None:
            return True
        cooldown_seconds = self.exit_retry_cooldown_minutes * 60
        return (now_ts - self._last_exit_attempt_ts) >= cooldown_seconds

    def _exit_slippage_for_attempt(self, now_ts: int) -> Decimal:
        if self._last_exit_attempt_ts is None:
            return self.sell_max_slippage
        escalation_seconds = self.exit_escalation_window_minutes * 60
        if (now_ts - self._last_exit_attempt_ts) <= escalation_seconds:
            return self.failed_exit_max_slippage
        return self.sell_max_slippage

    def _build_exit_intent(
        self,
        now_ts: int,
        base_balance: Decimal,
        trigger_label: str,
        trigger_detail: str,
    ) -> Any:
        if not self._can_retry_exit(now_ts):
            wait_seconds = (self.exit_retry_cooldown_minutes * 60) - (now_ts - (self._last_exit_attempt_ts or now_ts))
            reason = (
                f"Exit cooldown active after recent {self._last_exit_reason or 'exit'} attempt; "
                f"retry in {max(wait_seconds, 0)}s"
            )
            self._print_action("HOLD", reason)
            return Intent.hold(reason=reason)

        exit_slippage = self._exit_slippage_for_attempt(now_ts)
        self._last_exit_attempt_ts = now_ts
        self._last_exit_reason = trigger_label
        self._print_action("SELL", f"{trigger_detail}; slippage={exit_slippage * Decimal('100'):.2f}%")
        return Intent.swap(
            from_token=self.base_token_trade_id,
            to_token=self.quote_token,
            amount=base_balance * self.sell_fraction,
            max_slippage=exit_slippage,
            protocol=self.swap_protocol,
            chain=self.chain,
        )

    def decide(self, market: Any) -> Any:
        try:
            price = Decimal("0")
            for price_token in (
                self.base_token_price_id,
                self.base_token_symbol,
                self.base_token_address,
            ):
                if not price_token:
                    continue
                try:
                    price = self._to_decimal(market.price(price_token), Decimal("0"))
                except Exception:
                    price = Decimal("0")
                if price > 0:
                    break
            if price <= 0:
                reason = f"No price for {self.base_token_symbol} (id={self.base_token_price_id})"
                self._print_action("HOLD", reason)
                return Intent.hold(reason=reason)

            quote_balance = self._balance_with_fallback(
                market,
                self.quote_token_symbol,
                self.quote_token,
                self.quote_token_address,
            )
            base_balance = self._balance_with_fallback(
                market,
                self.base_token_symbol,
                self.base_token_balance_id,
                self.base_token_address,
            )
            rsi = None
            for rsi_token in (self.base_token_rsi_id, self.base_token_symbol):
                try:
                    rsi = self._extract_rsi(
                        market.rsi(
                            rsi_token,
                            period=self.rsi_period,
                            timeframe=self.rsi_timeframe,
                        )
                    )
                except Exception:
                    rsi = None
                if rsi is not None:
                    break

            if rsi is None:
                reason = f"No RSI for {self.base_token_symbol}"
                self._print_action("HOLD", reason)
                return Intent.hold(reason=reason)

            self._last_portfolio_value_usd = quote_balance + (base_balance * price)
            self._last_total_profit_usd = self._last_portfolio_value_usd - self.starting_capital_usd
            if self.starting_capital_usd > 0:
                self._last_total_profit_pct = self._last_total_profit_usd / self.starting_capital_usd
            else:
                self._last_total_profit_pct = Decimal("0")

            self._print_status(price, quote_balance, base_balance, rsi)

            now_ts = int(time.time())
            position_open = base_balance >= self.min_base_position

            if not position_open and self._entry_price is not None:
                # Position has likely closed, reset entry tracking.
                self._entry_price = None
                self._entry_ts = None
                self._last_exit_attempt_ts = None
                self._last_exit_reason = None

            if position_open and self._entry_price is None:
                # Fallback when strategy restarts with an existing position.
                self._entry_price = price
                self._entry_ts = now_ts

            if position_open and self._entry_price is not None:
                entry_price = self._entry_price
                pnl_pct = (price - entry_price) / entry_price if entry_price > 0 else Decimal("0")
                pnl_usd = base_balance * (price - entry_price)
                held_minutes = (
                    (now_ts - self._entry_ts) / 60
                    if self._entry_ts is not None
                    else 0
                )

                if pnl_pct >= self.take_profit_pct:
                    ok, reason = self._exit_passes_gas_guard(pnl_usd)
                    if not ok:
                        self._print_action("HOLD", reason)
                        return Intent.hold(reason=reason)
                    return self._build_exit_intent(
                        now_ts=now_ts,
                        base_balance=base_balance,
                        trigger_label="take_profit",
                        trigger_detail=f"Take profit hit at {pnl_pct * Decimal('100'):.2f}%",
                    )

                if not self.enforce_profit_only_exit and pnl_pct <= -self.stop_loss_pct:
                    return self._build_exit_intent(
                        now_ts=now_ts,
                        base_balance=base_balance,
                        trigger_label="stop_loss",
                        trigger_detail=f"Stop loss hit at {pnl_pct * Decimal('100'):.2f}%",
                    )

                if held_minutes >= self.max_hold_minutes and pnl_pct > 0:
                    ok, reason = self._exit_passes_gas_guard(pnl_usd)
                    if not ok:
                        self._print_action("HOLD", reason)
                        return Intent.hold(reason=reason)
                    return self._build_exit_intent(
                        now_ts=now_ts,
                        base_balance=base_balance,
                        trigger_label="time_exit",
                        trigger_detail=(
                            f"Time exit after {held_minutes:.1f}m with profit {pnl_pct * Decimal('100'):.2f}%"
                        ),
                    )

                reason = (
                    f"Holding {self.base_token_symbol}: pos_pnl={pnl_pct:.4f}, "
                    f"total_profit=${self._last_total_profit_usd:.2f}, rsi={rsi}"
                )
                self._print_action("HOLD", reason)
                return Intent.hold(reason=reason)

            cooldown_ok = (
                self._last_buy_ts is None
                or (now_ts - self._last_buy_ts) >= self.cooldown_minutes * 60
            )
            if not cooldown_ok:
                reason = (
                    f"Cooldown active for {self.base_token_symbol}; "
                    f"total_profit=${self._last_total_profit_usd:.2f}"
                )
                self._print_action("HOLD", reason)
                return Intent.hold(reason=reason)

            buy_amount_usd = self._compute_buy_amount_usd(quote_balance)
            if buy_amount_usd < self.min_trade_amount_usd:
                reason = (
                    f"Insufficient {self.quote_token} for min trade: "
                    f"spendable=${buy_amount_usd:.4f}, min=${self.min_trade_amount_usd:.4f}"
                )
                self._print_action("HOLD", reason)
                return Intent.hold(reason=reason)

            if rsi < self.buy_rsi and buy_amount_usd >= self.min_trade_amount_usd:
                ok, reason = self._entry_passes_gas_guard(buy_amount_usd)
                if not ok:
                    self._print_action("HOLD", reason)
                    return Intent.hold(reason=reason)
                self._entry_price = price
                self._entry_ts = now_ts
                self._last_buy_ts = now_ts
                self._last_exit_attempt_ts = None
                self._last_exit_reason = None
                self._print_action(
                    "BUY",
                    f"RSI {rsi} below {self.buy_rsi}; deploying ${buy_amount_usd:.4f}",
                )
                return Intent.swap(
                    from_token=self.quote_token,
                    to_token=self.base_token_trade_id,
                    amount_usd=buy_amount_usd,
                    max_slippage=self.buy_max_slippage,
                    protocol=self.swap_protocol,
                    chain=self.chain,
                )

            reason = (
                f"No entry for {self.base_token_symbol} (rsi={rsi}); "
                f"total_profit=${self._last_total_profit_usd:.2f}"
            )
            self._print_action("HOLD", reason)
            return Intent.hold(reason=reason)
        except Exception as exc:
            self._print_action("ERROR", str(exc))
            return Intent.hold(reason=f"Error: {exc}")

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.__class__.__name__,
            "chain": self.chain,
            "base_token": self.base_token_symbol,
            "base_token_id": self.base_token_trade_id,
            "base_token_address": self.base_token_address if self.base_token_address else None,
            "base_token_price_id": self.base_token_price_id,
            "base_token_balance_id": self.base_token_balance_id,
            "base_token_trade_id": self.base_token_trade_id,
            "quote_token": self.quote_token,
            "quote_token_symbol": self.quote_token_symbol,
            "quote_token_address": self.quote_token_address if self.quote_token_address else None,
            "swap_protocol": self.swap_protocol,
            "compound_profits": self.compound_profits,
            "compound_factor": str(self.compound_factor),
            "max_trade_amount_usd": str(self.max_trade_amount_usd),
            "enable_gas_guard": self.enable_gas_guard,
            "estimated_buy_gas_usd": str(self.estimated_buy_gas_usd),
            "estimated_sell_gas_usd": str(self.estimated_sell_gas_usd),
            "gas_safety_multiplier": str(self.gas_safety_multiplier),
            "min_net_profit_usd": str(self.min_net_profit_usd),
            "buy_max_slippage": str(self.buy_max_slippage),
            "sell_max_slippage": str(self.sell_max_slippage),
            "failed_exit_max_slippage": str(self.failed_exit_max_slippage),
            "exit_retry_cooldown_minutes": self.exit_retry_cooldown_minutes,
            "exit_escalation_window_minutes": self.exit_escalation_window_minutes,
            "min_trade_amount_usd": str(self.min_trade_amount_usd),
            "min_quote_reserve_usd": str(self.min_quote_reserve_usd),
            "buy_rsi": str(self.buy_rsi),
            "take_profit_pct": str(self.take_profit_pct),
            "stop_loss_pct": str(self.stop_loss_pct),
            "entry_price": str(self._entry_price) if self._entry_price is not None else None,
            "last_exit_attempt_ts": self._last_exit_attempt_ts,
            "last_exit_reason": self._last_exit_reason,
            "starting_capital_usd": str(self.starting_capital_usd),
            "portfolio_value_usd": str(self._last_portfolio_value_usd),
            "total_profit_usd": str(self._last_total_profit_usd),
            "total_profit_pct": str(self._last_total_profit_pct),
        }
