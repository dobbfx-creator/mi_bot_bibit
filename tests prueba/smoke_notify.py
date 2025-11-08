# tests/smoke_notify.py
# Envia dos mensajes de prueba usando tu settings.json real
import json, os, sys
from pathlib import Path

# Ajusta si tu settings está en otro path
BASE = Path(__file__).resolve().parents[1]
settings_path = BASE / "config" / "settings.json"
if not settings_path.exists():
    print("No encuentro config/settings.json")
    sys.exit(1)

CFG = json.loads(settings_path.read_text(encoding="utf-8"))

from mensajeria.eventos import notifier as EV

# Mensaje 1: parcial
EV.parcial(
    CFG,
    simbolo="BTCUSDT",
    is_long=True,
    fraction=0.5,
    pnl_usdt=12.34,
    qty_restante=0.0021,
    precio_ejecucion=108000.00,
    at_r=0.5,
)

# Mensaje 2: trailing close
EV.trailing_close(
    CFG,
    simbolo="BTCUSDT",
    is_long=True,
    pnl_usdt=25.67,
    precio_cierre=107500.0,
    distancia_pct=0.15,
)

print("Enviados 2 mensajes de SMOKE a Telegram (revisá el chat).")
