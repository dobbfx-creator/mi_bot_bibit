# gestion/riesgo.py
from typing import Dict

def _round_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return (value // step) * step  # redondeo hacia abajo al múltiplo del step

def _fmt_decimals_for_step(step: float) -> int:
    s = f"{step:.10f}".rstrip("0")
    if "." in s:
        return len(s.split(".")[1])
    return 0

def calcular_qty(simbolo: str, precio_entrada: float, cfg: Dict) -> float:
    """
    Satisface dos restricciones simultáneas:
    A) Riesgo (USDT) al SL: riesgo_usdt = stop_pct * notional  =>  qty_riesgo = riesgo_usdt / (stop_pct * precio)
    B) Notional objetivo por margen y apalancamiento:
       notional_obj = leverage * target_margin_usdt           =>  qty_notional = notional_obj / precio
    Se usa la más conservadora: min(qty_riesgo, qty_notional), luego se ajusta por step y min_qty.
    """
    riesgo_cfg = cfg.get("riesgo", {})
    fut_cfg = cfg.get("futuros", {})
    prec = cfg.get("precision", {}).get(simbolo, {})

    stop_pct = float(riesgo_cfg.get("stop_pct", 1.0)) / 100.0
    riesgo_usdt = float(riesgo_cfg.get("riesgo_usdt", 10.0))

    leverage = float(fut_cfg.get("leverage", 10))
    target_margin = float(fut_cfg.get("target_margin_usdt", 100.0))
    notional_obj = leverage * target_margin  # ≈ 1000 USDT con 10x*100

    qty_riesgo = riesgo_usdt / max(stop_pct * float(precio_entrada), 1e-9)
    qty_notional = notional_obj / max(float(precio_entrada), 1e-9)
    qty_bruta = min(qty_riesgo, qty_notional)

    step = float(prec.get("qty_step", 0.001))
    min_qty = float(prec.get("min_qty", step))
    qty = _round_step(qty_bruta, step)
    if qty < min_qty:
        qty = _round_step(min_qty, step)
    return qty

def formatear_qty(simbolo: str, qty: float, cfg: Dict) -> str:
    """Formatea qty según el step, evitando números larguísimos."""
    prec = cfg.get("precision", {}).get(simbolo, {})
    step = float(prec.get("qty_step", 0.001))
    decs = _fmt_decimals_for_step(step)
    return f"{qty:.{decs}f}"

def calcular_pnl(direccion_long_o_short: str, entrada: float, salida: float, qty: float, cfg: Dict) -> Dict[str, float]:
    """
    PnL bruto en USDT - fees (ida+vuelta).
    fee_rate: por lado (ej: 0.0006 = 6 bps taker).
    """
    fee_rate = float(cfg.get("fees", {}).get("taker_rate", 0.0006))
    if direccion_long_o_short.upper() == "LONG":
        pnl_bruto = qty * (float(salida) - float(entrada))
        notional_in = qty * float(entrada)
        notional_out = qty * float(salida)
    else:
        pnl_bruto = qty * (float(entrada) - float(salida))
        notional_in = qty * float(entrada)
        notional_out = qty * float(salida)

    fees = (notional_in + notional_out) * fee_rate
    pnl_neto = pnl_bruto - fees
    return {"bruto": pnl_bruto, "neto": pnl_neto, "fees": fees}

def impacto_sobre_capital(pnl_neto_usdt: float, cfg: Dict) -> float:
    capital_total = float(cfg.get("capital", {}).get("total_usdt", 1000.0))
    if capital_total <= 0:
        return 0.0
    return (float(pnl_neto_usdt) / capital_total) * 100.0
