# -*- coding: utf-8 -*-
"""
Adapter Bybit (DEMO/TESTNET/LIVE) para Fabi bot BiBIT.
Compatibilidad retro: expone round_qty_to_step y adjust_qty_by_filters.
"""

import os, math
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

# ---- ENV ----
BYBIT_ENV         = (os.getenv("BYBIT_ENV") or "DEMO").upper()     # DEMO | TESTNET | LIVE
BYBIT_API_KEY     = os.getenv("BYBIT_API_KEY") or os.getenv("BYBIT_KEY")
BYBIT_API_SECRET  = os.getenv("BYBIT_API_SECRET") or os.getenv("BYBIT_SECRET")
BYBIT_ACCOUNT     = (os.getenv("BYBIT_ACCOUNT") or "UNIFIED").upper()
BYBIT_SETTLE      = (os.getenv("BYBIT_SETTLE") or "USDT").upper()

# ---- PyBit session ----
from pybit.unified_trading import HTTP

def _make_session():
    if BYBIT_ENV == "DEMO":
        try:
            return HTTP(demo=True, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
        except TypeError:
            return HTTP(endpoint="https://api-demo.bybit.com",
                        api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
    if BYBIT_ENV == "TESTNET":
        return HTTP(testnet=True, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
    return HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

session = _make_session()

# ---- Cache de filtros por instrumento ----
_instrument_filters = {}  # symbol -> {"min_qty": float, "step": float, "max_qty": float, "tick": float}

def load_symbol_filters(symbol: str):
    """Consulta y cachea min_qty/qtyStep/max_qty/tick (linear)."""
    if symbol in _instrument_filters:
        return _instrument_filters[symbol]
    try:
        r = session.get_instruments_info(category="linear", symbol=symbol)
        lst = r["result"]["list"]
        if not lst:
            return None
        it   = lst[0]
        lot  = it.get("lotSizeFilter", {}) or {}
        pfx  = it.get("priceFilter", {}) or {}
        minq = float(lot.get("minOrderQty", "0") or "0")
        maxq = float(lot.get("maxOrderQty", "0") or "0")
        step = float(lot.get("qtyStep", "0.001") or "0.001")
        tick = float(pfx.get("tickSize", "0.0") or "0.0")
        _instrument_filters[symbol] = {"min_qty": minq, "step": step, "max_qty": maxq, "tick": tick}
        return _instrument_filters[symbol]
    except Exception:
        return None

# ---------- Herramientas de cuantización ----------
def _decimals_from_increment(incr: float) -> int:
    if incr is None or incr <= 0:
        return 8
    q = Decimal(str(incr))
    return max(0, -q.as_tuple().exponent)

def quantize_price(price: float, tick: float) -> str:
    if price is None:
        return ""
    if tick is None or tick <= 0:
        return f"{price:.8f}"
    q = Decimal(str(tick)); p = Decimal(str(price))
    decs  = _decimals_from_increment(tick)
    steps = (p / q).quantize(Decimal("1"), rounding=ROUND_DOWN)
    snapped = (steps * q).quantize(Decimal(10) ** -decs, rounding=ROUND_DOWN)
    return format(snapped, "f")

def quantize_qty(qty: float, step: float, min_qty: float) -> str:
    """
    Pisa qty al múltiplo exacto de step (FLOOR) y respeta min_qty.
    Devuelve string con los decimales exactos del step (sin colas binarias).
    """
    if qty is None:
        qty = 0.0
    if step is None or step <= 0:
        q = Decimal(str(qty)).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        q = max(q, Decimal(str(min_qty or 0)))
        return format(q, "f")
    q_step = Decimal(str(step))
    q_qty  = Decimal(str(qty))
    decs   = _decimals_from_increment(step)
    steps = (q_qty / q_step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    snapped = (steps * q_step).quantize(Decimal(10) ** -decs, rounding=ROUND_DOWN)
    minq = Decimal(str(min_qty or 0))
    if snapped < minq:
        snapped = minq.quantize(Decimal(10) ** -decs, rounding=ROUND_DOWN)
    return format(snapped, "f")

# ---------- Compatibilidad retro ----------
def round_qty_to_step(qty: float, step: float) -> float:
    """Compat con core antiguo (Decimal para evitar colas binarias)."""
    if step is None or step <= 0:
        step = 0.001
    q_step = Decimal(str(step))
    q_qty  = Decimal(str(qty if qty is not None else 0.0))
    steps = (q_qty / q_step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    snapped = steps * q_step
    return float(snapped)

def adjust_qty_by_filters(symbol: str, qty: float):
    """Devuelve (ok, qty_ajustada, detalle) usando filtros del símbolo."""
    f = load_symbol_filters(symbol)
    if not f:
        q2 = max(round(qty or 0.0, 3), 0.001)
        return (q2 > 0), q2, "fallback (sin filtros)"
    step = float(f["step"]); minq = float(f["min_qty"]); maxq = float(f["max_qty"])
    q_txt = quantize_qty(qty or 0.0, step, minq)
    q2 = float(q_txt)
    if maxq and q2 > maxq:
        return False, 0.0, f"qty>{maxq}"
    return True, q2, f"min={minq} step={step}"

# ---------- Mercados / datos ----------
def get_klines(symbol, interval="15", limit=5):
    try:
        r = session.get_kline(category="linear", symbol=symbol, interval=str(interval), limit=limit)
        out = []
        for it in r["result"]["list"][::-1]:
            out.append({"t": int(it[0])//1000, "o": float(it[1]), "h": float(it[2]),
                        "l": float(it[3]), "c": float(it[4]), "v": float(it[5])})
        return out
    except Exception:
        return []

def get_last_price(symbol) -> float:
    try:
        r = session.get_tickers(category="linear", symbol=symbol)
        lst = r["result"]["list"]
        if lst:
            return float(lst[0]["lastPrice"])
    except Exception:
        pass
    bars = get_klines(symbol, interval="15", limit=1)
    return float(bars[-1]["c"]) if bars else 0.0

# ---------- Cuenta / posiciones ----------
def get_balance() -> float:
    try:
        r = session.get_wallet_balance(accountType=BYBIT_ACCOUNT, coin=BYBIT_SETTLE)
        return float(r["result"]["list"][0]["coin"][0]["walletBalance"])
    except Exception:
        return 0.0

def fetch_position_for_symbol(symbol: str):
    try:
        r = session.get_positions(category="linear", symbol=symbol)
        lst = r["result"]["list"]
        if not lst:
            return None
        it  = lst[0]
        qty_raw = it.get("size") or it.get("positionValue") or 0
        try:
            qty = float(qty_raw)
        except Exception:
            qty = 0.0
        if qty <= 0.0:
            return None
        side  = "Buy" if it["side"].lower()=="buy" else "Sell"
        price = float(it.get("avgPrice") or it.get("avgEntryPrice") or 0)

        sl_raw = it.get("stopLoss"); tp_raw = it.get("takeProfit")
        sl_val = None; tp_val = None
        try:
            if sl_raw not in (None, "", "0", 0):
                sl_val = float(sl_raw)
        except Exception:
            sl_val = None
        try:
            if tp_raw not in (None, "", "0", 0):
                tp_val = float(tp_raw)
        except Exception:
            tp_val = None

        return {"side": side, "qty": qty, "avgPrice": price, "stopLoss": sl_val, "takeProfit": tp_val}
    except Exception:
        return None

def set_symbol_leverage(symbol, lev: int = 10):
    try:
        session.set_leverage(category="linear", symbol=symbol,
                             buyLeverage=str(lev), sellLeverage=str(lev))
        try:
            session.switch_position_mode(category="linear", mode=0)
        except Exception:
            pass
        try:
            session.set_margin_mode(category="linear", symbol=symbol, tradeMode=1)  # 1=Isolated
        except Exception:
            pass
    except Exception:
        pass

# ---------- Órdenes & TPSL ----------
def place_market(symbol: str, side: str, qty: float):
    """
    Orden market con qty ajustada/serializada (sin colas binarias).
    Devuelve (ok, resp|msg).
    """
    f = load_symbol_filters(symbol) or {"min_qty": 0.0, "step": 0.001}
    step = float(f.get("step", 0.001)); minq = float(f.get("min_qty", 0.0))
    try:
        qty_txt = quantize_qty(qty, step, minq)
        r = session.place_order(category="linear", symbol=symbol, side=side,
                                orderType="Market", qty=qty_txt, timeInForce="GTC", reduceOnly=False)
        return True, r
    except Exception as e:
        msg = str(e)
        if "Qty invalid" in msg or "10001" in msg:
            det = f"(requisitos: min={f.get('min_qty')} step={f.get('step')})"
            return False, f"Qty invalid {det} -> qty_enviada={qty_txt}. {msg}"
        return False, msg

def clear_tpsl(symbol: str):
    try:
        session.set_trading_stop(category="linear", symbol=symbol, takeProfit="", stopLoss="")
    except Exception:
        pass

def set_trading_stop(symbol: str, take_profit: float = None, stop_loss: float = None):
    """
    SL/TP con validación por lado y cuantización por tickSize.
    + Regla MONOTÓNICA: NUNCA bajar SL (respeta manual más alto en LONG / más bajo en SHORT).
    Downgrade de 'not modified (34040)' a OK lógico.
    """
    try:
        f = load_symbol_filters(symbol) or {}
        tick = float(f.get("tick") or 0.0)

        tp_val = None if take_profit is None else float(take_profit)
        sl_val = None if stop_loss  is None else float(stop_loss)

        # leer posición para lado/base y SL actual
        pos = fetch_position_for_symbol(symbol)
        base = 0.0; side = None; current_sl = None
        if pos:
            base = float(pos.get("avgPrice") or 0.0) or float(get_last_price(symbol) or 0.0)
            side_raw = str(pos.get("side", "")).lower()
            side = "LONG" if side_raw == "buy" else "SHORT"
            try:
                if pos.get("stopLoss") not in (None, "", "0", 0):
                    current_sl = float(pos.get("stopLoss"))
            except Exception:
                current_sl = None

        # validación por lado (clamp)
        if base > 0 and side:
            epsilon = max(tick, base * 1e-6) if tick > 0 else max(0.0, base * 1e-6)
            if side == "LONG":
                if sl_val is not None and sl_val >= base:
                    sl_val = base - epsilon
                if tp_val is not None and tp_val <= base:
                    tp_val = base + epsilon
            else:  # SHORT
                if sl_val is not None and sl_val <= base:
                    sl_val = base + epsilon
                if tp_val is not None and tp_val >= base:
                    tp_val = base - epsilon

        # regla MONOTÓNICA
        if current_sl is not None and sl_val is not None:
            if side == "LONG" and sl_val < current_sl:
                sl_val = current_sl
            elif side == "SHORT" and sl_val > current_sl:
                sl_val = current_sl

        # cuantización por tick
        tp_txt = "" if tp_val is None else quantize_price(tp_val, tick)
        sl_txt = "" if sl_val is None else quantize_price(sl_val, tick)

        resp = session.set_trading_stop(category="linear", symbol=symbol,
                                        takeProfit=tp_txt, stopLoss=sl_txt)

        try:
            ret_code = str(resp.get("retCode", ""))
            ret_msg  = str(resp.get("retMsg", "")).lower()
            ok = (ret_code == "0") or (ret_msg in ("ok", "success"))
            if not ok:
                if "not modified" in ret_msg or ret_code in ("34040",):
                    return True, resp
            return ok, resp
        except Exception:
            return True, resp

    except Exception as e:
        return False, f"exception: {e}"
