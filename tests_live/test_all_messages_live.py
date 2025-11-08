# -*- coding: utf-8 -*-
"""
tests_live/test_all_messages_live.py
Envía TODOS los mensajes de una al Telegram real, usando settings.json.

Orden:
1) Reconciliación OK
2) Heartbeat
3) Orden manual detectada (apertura)
4) Parcial ejecutada
5) Trailing ACTIVADO
6) Cierre por TRAILING
7) TSL a BE
8) Cierre MANUAL
"""
import sys, json, time, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # asumir que este archivo está en <repo>/tests_live/
sys.path.insert(0, str(ROOT))

# ---- Cargar settings ---------------------------------------------------------
cfg_path = ROOT / "config" / "settings.json"
if not cfg_path.exists():
    print("No encuentro config/settings.json. Abortando.")
    sys.exit(1)
CFG = json.loads(cfg_path.read_text(encoding="utf-8"))

# ---- Canal de envío: preferir mensajeria.telegram ---------------------------
def _http_send(cfg, texto: str) -> bool:
    import urllib.request as ulr
    import urllib.parse as ulp
    try:
        token = str(cfg.get("telegram", {}).get("bot_token", "")).strip()
        chat  = str(cfg.get("telegram", {}).get("chat_id", "")).strip()
        if not token or not chat:
            return False
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = ulp.urlencode({"chat_id": chat, "text": texto}).encode("utf-8")
        req  = ulr.Request(url, data=data, method="POST")
        with ulr.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[WARN] HTTP Telegram fallo: {e}")
        return False

def send(cfg, texto: str):
    # 1) enviar_mensaje_raw si existe
    try:
        from mensajeria import telegram as tg
    except Exception:
        tg = None

    if tg is not None and hasattr(tg, "enviar_mensaje_raw"):
        try:
            tg.enviar_mensaje_raw(cfg, texto)
            return
        except Exception as e:
            print(f"[WARN] enviar_mensaje_raw fallo: {e}")
    # 2) enviar_mensaje si existe
    if tg is not None and hasattr(tg, "enviar_mensaje"):
        try:
            tg.enviar_mensaje(cfg, texto)
            return
        except Exception as e:
            print(f"[WARN] enviar_mensaje fallo: {e}")
    # 3) HTTP directo
    if not _http_send(cfg, texto):
        print("[ERROR] No se pudo enviar por ningún canal.")

# ---- Intentar formatos si existen -------------------------------------------
def have_format(name: str):
    try:
        from mensajeria import formatos as F
        return hasattr(F, name)
    except Exception:
        return False

def call_format(name: str, *args, **kwargs):
    try:
        from mensajeria import formatos as F
        fn = getattr(F, name, None)
        if fn is None:
            return None
        return fn(*args, **kwargs)
    except Exception:
        return None

# ---- Mensajes por defecto (si faltan helpers) -------------------------------
def hb_text():
    return (
        "Fabi bot BiBIT:\n"
        "🔄 HEARTBEAT\n"
        "Capital total: 49,113.55 USDT\n"
        "Hora: (test)\n\n"
        "Estado de los pares:\n\n"
        "Total de órdenes ejecutadas en 24h: 29"
    )

def recon_ok():
    return "Fabi bot BiBIT:\n🧯 Reconciliación al iniciar: OK (nada que corregir)"

def orden_manual_detectada(symbol="BTCUSDT", side="COMPRA (LONG)"):
    return (
        "Fabi bot BiBIT:\n"
        "🟨 Orden MANUAL detectada\n"
        f"Símbolo: {symbol}\n"
        f"Dirección: {side}\n"
        "Acción: monitoreada"
    )

def parcial_default():
    return (
        "✅ Parcial ejecutado | BTCUSDT\n"
        "Dirección: LONG\n"
        "Fracción: 0.50\n"
        "Ganancia realizada: 12.34 USDT 💰\n"
        "Cantidad restante: 0.0025\n"
        "Precio ejecución: 108000.0000\n"
        "Nivel alcanzado: 0.50R 🎯"
    )

def trailing_on_default():
    return (
        "Fabi bot BiBIT:\n"
        "🟦 Trailing ACTIVADO\n"
        "Símbolo: BTCUSDT\n"
        "Dirección: COMPRA (LONG)\n"
        "Entrada: 108,306.40\n"
        "Precio actual: 108,860.00\n"
        "MFE: 0.51%"
    )

def trailing_close_default():
    return (
        "Fabi bot BiBIT:\n"
        "🟥 Cierre por TRAILING\n"
        "Símbolo: BTCUSDT\n"
        "Dirección: COMPRA (LONG)\n"
        "Entrada: 108,306.40\n"
        "Salida: 108,306.40\n"
        "Resultado: 0.00%\n"
        "Motivo: BE"
    )

def tsl_be_default():
    return (
        "Fabi bot BiBIT:\n"
        "🔒 TSL movido a BE\n"
        "Símbolo: BTCUSDT\n"
        "Nuevo SL: 108,306.40 (BE)"
    )

def cierre_manual_default(symbol="ETHUSDT", side="COMPRA (LONG)"):
    return (
        "Fabi bot BiBIT:\n"
        "🛑 Operación CERRADA (manual)\n"
        f"Símbolo: {symbol}\n"
        f"Dirección: {side}\n"
        "Resultado: (test)"
    )

# ---- Lógica principal --------------------------------------------------------
def main():
    print("Test LIVE: enviando TODOS los mensajes al Telegram real...")

    # 1) Reconciliación
    send(CFG, recon_ok()); time.sleep(0.8)

    # 2) Heartbeat (usa helper si lo tenés)
    txt = hb_text()
    send(CFG, txt); time.sleep(0.8)

    # 3) Orden manual detectada
    send(CFG, orden_manual_detectada()); time.sleep(0.8)

    # 4) Parcial ejecutada (si existe template propio, úsalo)
    m = call_format("msg_parcial_ejecutado", "BTCUSDT", True, 0.5, 12.34, 0.0025, 108000.0, 0.5)
    send(CFG, m if m else parcial_default()); time.sleep(0.8)

    # 5) Trailing ACTIVADO
    m2 = call_format("msg_trailing_activado", "BTCUSDT", "COMPRA (LONG)", 108306.40, 108860.00, 0.51, hora="(test)")
    send(CFG, m2 if m2 else trailing_on_default()); time.sleep(0.8)

    # 6) Cierre por TRAILING
    m3 = call_format("msg_cierre_trailing", "BTCUSDT", "COMPRA (LONG)", 108306.40, 108306.40, 0.00, motivo="BE", hora="(test)")
    send(CFG, m3 if m3 else trailing_close_default()); time.sleep(0.8)

    # 7) TSL a BE
    # (si existiera msg_tsl_be en tus formatos, se usaría; hoy mandamos uno genérico)
    send(CFG, tsl_be_default()); time.sleep(0.8)

    # 8) Cierre MANUAL (usa helper si existe)
    m4 = call_format("msg_cierre_manual", "ETHUSDT", "COMPRA (LONG)", 3939.57, 4013.10, 1.87, "manual/externo", "407m", impacto_pct=0.03)
    send(CFG, m4 if m4 else cierre_manual_default())

    print("Listo. Revisá tu Telegram.")

if __name__ == "__main__":
    main()
