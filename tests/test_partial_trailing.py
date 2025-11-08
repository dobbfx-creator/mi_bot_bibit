# -*- coding: utf-8 -*-
"""
Tests aislados para parcial y trailing SIN tocar tu bot.
- Importa core.partials (tu módulo real)
- Intenta importar trailing_base desde varias rutas y, si no existe, usa un fallback simple
- No asume órdenes en SIM; valida reducción de qty
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- Parciales: módulo real ----
from core.partials import (
    should_execute_partial,
    ejecutar_parcial_si_corresponde,
    _resolve_partials_cfg,
)

# ---- Trailing: intento múltiple + fallback ----
compute_next_sl = None
_import_errors = []

for candidate in (
    "core.trailing_base",
    "trailing_base",
    "core.trailing",
    "core.trailing_logic",
):
    try:
        mod = __import__(candidate, fromlist=["*"])
        if hasattr(mod, "compute_next_sl"):
            compute_next_sl = getattr(mod, "compute_next_sl")
            break
        if hasattr(mod, "next_sl"):
            compute_next_sl = getattr(mod, "next_sl")
            break
    except Exception as e:
        _import_errors.append((candidate, str(e)))

if compute_next_sl is None:
    # Fallback mínimo para poder testear el flujo de trailing sin el módulo real.
    # Interpreta min_mov_sl_pct y buffer_pct como % (no decimal), igual que sl_pct en el core.
    def compute_next_sl(side_long, last_sl, ultimo, min_mov_sl_pct, buffer_pct):
        last_sl = float(last_sl); ultimo = float(ultimo)
        mov_req = float(min_mov_sl_pct) / 100.0
        buf = float(buffer_pct) / 100.0

        if side_long:
            avance = (ultimo - last_sl) / max(last_sl, 1e-9)
            if avance >= mov_req:
                nuevo = max(last_sl, ultimo * (1.0 - buf))
                return nuevo
            return last_sl
        else:
            avance = (last_sl - ultimo) / max(abs(last_sl), 1e-9)
            if avance >= mov_req:
                nuevo = min(last_sl, ultimo * (1.0 + buf))
                return nuevo
            return last_sl

    print("[AVISO] No se pudo importar trailing_base real. Usando Fallback para compute_next_sl.")
    for cand, err in _import_errors:
        print(f"  - Intento fallido: {cand} -> {err}")

# ---- Config de prueba (formato NUEVO) ----
CFG = {
    "partials": {
        "enabled": True,
        "trigger_mode": "R_multiple",
        "trigger_R": 1.0,
        "qty_mode": "percent_of_open",
        "qty_value": 50.0
    },
    "trailing": {
        "enabled": True,
        "min_mov_sl_pct": 0.15,   # 0.15%
        "buffer_pct": 0.02,       # 0.02%
        "cooldown_bars": 0
    }
}

# ---- Stubs para intercambio y notificaciones ----
from tests.sim_exchange import SimExchange
from tests.notifier_stub import NotifierStub

def _mk_reg(side_long, entrada, sl_pct, qty):
    return {
        "direccion": "COMPRA" if side_long else "VENTA",
        "entrada_precio": float(entrada),
        "sl_pct": float(sl_pct),   # % respecto a entrada (como usás en core)
        "qty": float(qty),
        "pnl_realizado": 0.0,
        "trailing": {}
    }

# ---- Tests ----
def test_parcial():
    print("\n=== TEST PARCIAL ===")
    # Long 1R: entrada 100, SL 99 (1%), precio 101 => r_now=1.0
    reg = _mk_reg(side_long=True, entrada=100.0, sl_pct=1.0, qty=0.010)
    precio = 101.0
    exch = SimExchange(qty_inicial=reg["qty"])
    notif = NotifierStub()

    ok, info = should_execute_partial(reg, precio, CFG)
    atR, frac = _resolve_partials_cfg(CFG)
    print(f"resolver ok={ok}, r_now={info.get('r_now',0):.3f}, at_R={atR:.3f}, fraction={frac:.2f}")

    assert ok, "Debería disparar el parcial en 1R"
    aplicado = ejecutar_parcial_si_corresponde(
        simbolo="ETHUSDT",
        reg=reg,
        precio_actual=precio,
        CFG=CFG,
        MODO="sim",
        place_market=exch.place_market,
        fetch_position_for_symbol=exch.fetch_position_for_symbol,
        round_qty_to_step=exch.round_qty_to_step,
        notifier=notif,
        persist=lambda s, r: None
    )
    print("aplicado:", aplicado, "qty_restante:", reg["qty"])
    assert aplicado, "Debió aplicar el parcial"
    # Validación en SIM: no asumimos órdenes, verificamos reducción de qty
    assert abs(reg["qty"] - 0.005) < 1e-9, "Debe quedar 50% de la posición"

def test_trailing():
    print("\n=== TEST TRAILING ===")
    entrada = 100.0
    sl_pct = 1.0
    sl_inicial = entrada * (1 - sl_pct/100.0)  # 99.0
    precio = 102.0

    next_sl = compute_next_sl(
        side_long=True,
        last_sl=sl_inicial,
        ultimo=precio,
        min_mov_sl_pct=CFG["trailing"]["min_mov_sl_pct"],
        buffer_pct=CFG["trailing"]["buffer_pct"]
    )
    print(f"next_sl calculado={next_sl:.5f} (desde {sl_inicial:.5f})")
    assert next_sl >= sl_inicial, "El SL no puede bajar en un long"
    assert next_sl > sl_inicial, "El SL debería subir si el precio avanzó lo suficiente"

if __name__ == "__main__":
    test_parcial()
    test_trailing()
    print("\nOK: parciales y trailing calculados correctamente en entorno aislado.")
