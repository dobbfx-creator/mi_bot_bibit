# -*- coding: utf-8 -*-
# core/core.py

# -*- coding: utf-8 -*-
import os
import json
import time
import sys
import logging
from mensajeria import notifier
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Tuple
from utils.logging_ex import get_logger, Section
from utils.settings import load_settings
LOG = get_logger("core")

# --- opcional: trazas de decisiAA3n de parcial ---
try:
    from utils.decisions import log_partial_check, log_skip
except Exception:
    def log_partial_check(*args, **kwargs):
        LOG.debug("log_partial_check (noop) %s %s", args, kwargs)
    def log_skip(reason, **kw):
        LOG.info("PARCIAL.SKIP %s %s", reason, kw)

CFG, PARTS = load_settings("config/settings.json")  # o el path que uses


# ---- rutas / imports base ----
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

# Cargar variables de entorno (.env) para Bybit DEMO/LIVE
try:
    from dotenv import load_dotenv
    load_dotenv(str(ROOT.joinpath(".env")))
except Exception:
    pass

# Riesgo
try:
    from gestion.riesgo import calcular_qty, formatear_qty, calcular_pnl, impacto_sobre_capital
except Exception:
    from riesgo import calcular_qty, formatear_qty, calcular_pnl, impacto_sobre_capital  # fallback

from mensajeria.formatos import (
    msg_entrada,  # compat (no se usa directamente, mantenido por si lo llamAAs)
    msg_tp_sl_aplicado,
    msg_heartbeat_detallado,
    msg_trailing_seguimiento,
    msg_operacion_cerrada,
)
from mensajeria.telegram import enviar_mensaje as enviar_mensaje_raw

# Estrategia
from estrategia.bollinger_vol import inicializar as estr_init, generar_senal

# Adapter Bybit
from adapters.bybit_private import (
    session,
    get_klines,
    get_last_price,
    get_balance,
    fetch_position_for_symbol,
    set_symbol_leverage,
    load_symbol_filters,
    round_qty_to_step,
    adjust_qty_by_filters,
    place_market,
    clear_tpsl,
    set_trading_stop,
)

# Persistencia
try:
    from core.estado import cargar_estado, guardar_estado
except Exception:
    def cargar_estado():
        return {"pares": {}, "ordenes_24h": 0}
    def guardar_estado(_):
        pass

# ------------------ Logging ------------------
LOG_DIR = ROOT.joinpath("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR.joinpath("bibit.log")

logger = logging.getLogger("bibit")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

# ------------------ Config ------------------

MODO = str(CFG.get("exchange", {}).get("modo", "sim")).lower().strip()  # "real" | "sim"
SIMBOLOS = CFG.get("simbolos", ["ETHUSDT", "BTCUSDT", "SOLUSDT"])

# Estado global
estado_estrategia = {}
estado_pares = {}
ordenes_24h = 0

# Cooldown trailing
TRAILING_COOLDOWN = float(CFG.get("trailing", {}).get("cooldown_seg", 45.0))

# Anti-fantasmas
MANUAL_DETECT_DEBOUNCE = float(CFG.get("anti_fantasmas", {}).get("manual_detect_debounce_s", 90.0))
POST_CLOSE_HOLDOFF     = float(CFG.get("anti_fantasmas", {}).get("post_close_holdoff_s", 45.0))
_miss_count = {}   # { symbol: int }   -> debounce para cierres
_manual_seen = {}  # { symbol: {"sig": str, "ts": float} }
_last_closed = {}  # { symbol: float }

# ------------------ Hora (Bybit 1:1) ------------------
import os, sys
from datetime import datetime, timezone
# ---- Parciales: import robusto (una sola vez) ----
try:
    from core.partials import (
        should_execute_partial,
        ejecutar_parcial_si_corresponde,
        _resolve_partials_cfg,
    )
except Exception:
    try:
        from .partials import (
            should_execute_partial,
            ejecutar_parcial_si_corresponde,
            _resolve_partials_cfg,
        )
    except Exception as e:
        raise ImportError(f"No se pudo importar core.partials ni .partials: {e}")

# Zona horaria (opcional)
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

def _tz_cfg():
    tcfg = CFG.get("tiempo", {}) if isinstance(CFG, dict) else {}
    tzname = tcfg.get("zona_horaria", "UTC")
    fmt = (tcfg.get("formato") or "utc").lower()
    return tzname, fmt


def _tz_cfg():
    tcfg = CFG.get("tiempo", {}) if isinstance(CFG, dict) else {}
    tzname = tcfg.get("zona_horaria", "UTC")
    fmt = (tcfg.get("formato") or "utc").lower()
    return tzname, fmt

def _fmt_hora_from_ms(ts_ms: int) -> str:
    tzname, fmt = _tz_cfg()
    if fmt == "utc":
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%H:%M UTC")
    if ZoneInfo:
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=ZoneInfo(tzname))
            return dt.strftime("%H:%M")
        except Exception:
            pass
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%H:%M UTC")

def _exchange_time_ms_fallback() -> int:
    try:
        from adapters.bybit_private import get_server_time_ms
        return int(get_server_time_ms())
    except Exception:
        return int(time.time() * 1000)

def _hora_exchange_str() -> str:
    return _fmt_hora_from_ms(_exchange_time_ms_fallback())

def _tf_to_interval(tf_cfg: str) -> str:
    tf = tf_cfg.lower().strip()
    if tf.endswith("m"):
        return tf[:-1]
    if tf.endswith("h"):
        return str(int(tf[:-1]) * 60)
    if tf.endswith("d"):
        return str(int(tf[:-1]) * 60 * 24)
    return tf

def _mapear_velas_bybit(bars):
    out = []
    for b in bars:
        out.append({
            "open": b["o"], "high": b["h"], "low":  b["l"],
            "close": b["c"], "volume": b["v"], "time": b["t"],
        })
    return out

# ---------- Backoff ----------
def _retry(fn: Callable, args: Tuple = (), kwargs: dict = None, *,
           max_tries: int = 5, base_delay: float = 0.5, max_delay: float = 8.0, label: str = "op"):
    if kwargs is None:
        kwargs = {}
    tries = 0; delay = base_delay; last_exc = None
    while tries < max_tries:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e; tries += 1
            if tries >= max_tries:
                logger.error("Retry agotado: %s (%s intentos): %s", label, tries, e)
                break
            jitter = (0.2 * delay)
            sleep_for = min(max_delay, delay + jitter)
            logger.warning("Fallo en %s (intento %s/%s): %s. Reintentando en %.2fs",
                           label, tries, max_tries, e, sleep_for)
            time.sleep(sleep_for)
            delay = min(max_delay, delay * 2.0)
    raise last_exc if last_exc else RuntimeError(f"{label}: fallo desconocido")

# Wrappers
def obtener_velas(simbolo: str, tf: str, n: int):
    interval = _tf_to_interval(tf)
    bars = _retry(get_klines, (simbolo, interval, n), label=f"get_klines({simbolo},{interval},{n})")
    return _mapear_velas_bybit(bars)

def enviar_mensaje(cfg: dict, texto: str):
    return _retry(enviar_mensaje_raw, (cfg, texto), label="enviar_mensaje")

# ------------------ Posiciones Bybit ------------------
def _fetch_positions_dict():
    out = []
    if MODO != "real":
        return out
    for s in SIMBOLOS:
        p = fetch_position_for_symbol(s)
        if not p:
            continue
        side = "LONG" if (p["side"].lower() == "buy") else "SHORT"
        out.append({
            "symbol": s,
            "side": side,
            "entry_price": float(p.get("avgPrice") or 0.0),
            "sl": p.get("stopLoss"),
            "tp": p.get("takeProfit"),
            "qty": float(p.get("qty") or 0.0),
        })
    return out

# ------------------ Seguridad al iniciar ------------------
def seguridad_al_iniciar():
    global estado_pares, ordenes_24h, _miss_count

    est = cargar_estado()
    estado_pares = est.get("pares", {})
    ordenes_24h = est.get("ordenes_24h", 0)
    _miss_count = {s: 0 for s in SIMBOLOS}

    resumen = []
    if MODO == "real":
        try:
            abiertas = _fetch_positions_dict()
            logger.info("Posiciones vivas (inicio): %s", len(abiertas))
        except Exception as e:
            abiertas = []
            msg = f"No se pudieron leer posiciones del exchange: {e}"
            logger.warning(msg); resumen.append(f"AAA A A A {msg}")
    else:
        abiertas = []

    from core.trailing_base import inicializar as tr_init, preparar_posicion as tr_prep
    map_ex = {str(p.get("symbol")): p for p in abiertas if p.get("symbol")}

    for sim, pos in map_ex.items():
        try:
            side = str(pos.get("side", "")).upper()
            entrada = float(pos.get("entry_price", 0.0))
            sl = pos.get("sl"); tp = pos.get("tp")

            reg = estado_pares.get(sim, {"posicion_abierta": False, "entradas": 0})
            reg.update({
                "posicion_abierta": True,
                "direccion": "COMPRA (LONG)" if side == "LONG" else "VENTA (SHORT)",
                "entrada_precio": entrada,
                "sl_pct": CFG["riesgo"]["stop_pct"],
                "tp_pct": CFG["riesgo"]["take_pct"],
                "qty": reg.get("qty") or calcular_qty(sim, entrada, CFG),
                "entradas": max(1, reg.get("entradas", 0)),
            })

            tr = reg.get("trailing")
            if not tr:
                tr = tr_init(CFG.get("trailing", {}))
                tr = tr_prep(tr, side, entrada, CFG)
            reg["trailing"] = tr

            # Alinear SL/TP si faltan o difieren > 0.1%
            stop = CFG["riesgo"]["stop_pct"] / 100.0
            take = CFG["riesgo"]["take_pct"] / 100.0
            if side == "LONG":
                sl_obj = entrada * (1 - stop); tp_obj = entrada * (1 + take)
            else:
                sl_obj = entrada * (1 + stop); tp_obj = entrada * (1 - take)

            def _diff_pct(a, b):
                try:
                    return abs((float(a) - float(b)) / float(b)) * 100.0
                except Exception:
                    return 100.0

            need_set = (sl is None or tp is None) or (_diff_pct(sl, sl_obj) > 0.1) or (_diff_pct(tp, tp_obj) > 0.1)
            if MODO == "real" and need_set:
                with Section(LOG, "Reconciliar SL/TP (arranque)", simbolo=sim, side=side, sl=sl_obj, tp=tp_obj):
                    ok, resp = set_trading_stop(sim, take_profit=tp_obj, stop_loss=sl_obj)
                if ok:
                    resumen.append(f"AAAA Recolocado SL/TP en {sim} (sl={sl_obj:.2f}, tp={tp_obj:.2f})")
                    logger.info("Reconciliado SL/TP en %s", sim)
                else:
                    # Silencioso si es not modified
                    if "not modified" in str(resp).lower():
                        logger.info("[Bybit] SL/TP ya alineados en %s", sim)
                    else:
                        resumen.append(f"AAA A A A No pude colocar SL/TP en {sim}: {resp}")
                        logger.error("Fallo set_trading_stop en %s: %s", sim, resp)

            # === Parcial al iniciar si ya está en R configurado ===
            try:
                _partial_startup_if_needed(sim, reg)
            except Exception as e:
                logger.error("PARCIAL STARTUP wrapper fallo %s: %s", sim, e)

            estado_pares[sim] = reg
        except Exception as e:
            logger.error("Fallo reconciliando %s: %s", sim, e)

    # Cierra local si no estAA en exchange
    for sim, reg in list(estado_pares.items()):
        try:
            if reg.get("posicion_abierta") and sim not in map_ex:
                reg["posicion_abierta"] = False
                estado_pares[sim] = reg
                resumen.append(f"AAA1A A A {sim}: no se encontrAA3 en exchange. Marcado como cerrado localmente.")
                logger.info("%s marcado cerrado localmente (no estAA en exchange).", sim)
        except Exception as e:
            logger.error("Marcado cerrado localmente fallo %s: %s", sim, e)

    guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})

    try:
        if resumen:
            enviar_mensaje(CFG, "AAAA  ReconciliaciAA3n al iniciar:\n" + "\n".join(resumen))
        else:
            enviar_mensaje(CFG, "AAAA  ReconciliaciAA3n al iniciar: OK (nada que corregir)")
    except Exception as e:
        logger.error("No se pudo enviar mensaje de reconciliaciAA3n: %s", e)

# ------------------ ReconciliaciAA3n periAA3dica ------------------
def _desired_sl_tp(entry: float, side: str) -> Tuple[float, float]:
    stop = CFG["riesgo"]["stop_pct"] / 100.0
    take = CFG["riesgo"]["take_pct"] / 100.0
    if side == "LONG":
        return entry * (1 - stop), entry * (1 + take)
    else:
        return entry * (1 + stop), entry * (1 - take)

def reconciliar_con_exchange_periodico():
    """Manual OPEN/CLOSE robusto + realineo SL/TP con debounce anti-fantasma."""
    global estado_pares, ordenes_24h, _miss_count
    try:
        vivas = _fetch_positions_dict() if MODO == "real" else []
        idx = {p["symbol"]: p for p in vivas}

        # 1) Aperturas manuales (con holdoff y dedupe)
        for sim, p in idx.items():
            if _last_closed.get(sim) and (time.time() - _last_closed[sim] < POST_CLOSE_HOLDOFF):
                logger.info("[%s] Ignorado 'manual detectada' por holdoff post-cierre", sim)
                continue

            reg = estado_pares.get(sim)
            if reg and reg.get("posicion_abierta", False):
                _miss_count[sim] = 0
                continue  # ya la tenemos local

            # firma de la posiciAA3n
            side = p["side"]  # "LONG"/"SHORT"
            entry_sig = round(float(p["entry_price"]), 4)
            qty_sig   = round(float(p["qty"] or 0.0), 6)
            sig = f"{side}|{entry_sig}|{qty_sig}"

            seen = _manual_seen.get(sim)
            now_ts = time.time()
            if seen and seen["sig"] == sig and (now_ts - seen["ts"] < MANUAL_DETECT_DEBOUNCE):
                logger.info("[%s] Manual detectada duplicada ignorada (%ss)", sim, int(now_ts - seen["ts"]))
                _miss_count[sim] = 0
                continue
            _manual_seen[sim] = {"sig": sig, "ts": now_ts}
            _miss_count[sim] = 0

            side_txt = "COMPRA (LONG)" if side == "LONG" else "VENTA (SHORT)"
            estado_pares[sim] = {
                "posicion_abierta": True,
                "direccion": side_txt,
                "entrada_precio": float(p["entry_price"]),
                "sl_pct": CFG["riesgo"]["stop_pct"],
                "tp_pct": CFG["riesgo"]["take_pct"],
                "entradas": 1,
                "qty": float(p["qty"] or 0.0),
                "trailing": None,
                "condiciones_al_entrar": {},
            }

            sl_obj, tp_obj = _desired_sl_tp(p["entry_price"], p["side"])
            def _diff_pct(a, b):
                try:
                    return abs((float(a) - float(b)) / float(b)) * 100.0
                except Exception:
                    return 100.0
            need_set = (p["sl"] is None or p["tp"] is None) or (_diff_pct(p["sl"], sl_obj) > 0.1) or (_diff_pct(p["tp"], tp_obj) > 0.1)

            if MODO == "real" and need_set:
                with Section(LOG, "Apertura manual: alinear SL/TP", simbolo=sim, side=side, sl=sl_obj, tp=tp_obj):
                    ok, resp = set_trading_stop(sim, take_profit=tp_obj, stop_loss=sl_obj)
                if not ok and "not modified" not in str(resp).lower():
                    logger.warning("No pude alinear SL/TP en apertura manual %s: %s", sim, resp)

            try:
                enviar_mensaje(
                    CFG,
                    (f"AAAA PosiciAA3n manual detectada\n"
                     f"SAAmbolo: {sim}\n"
                     f"DirecciAA3n: {side_txt}\n"
                     f"Entrada: {estado_pares[sim]['entrada_precio']:.2f}\n"
                     f"SL/TP: {'reajustados a 1:5' if need_set else 'OK'}")
                )
            except Exception as e:
                logger.error("No pude notificar apertura manual %s: %s", sim, e)

        # 2) Cierres manuales/externos (debounce)
        for sim, reg in list(estado_pares.items()):
            if not reg.get("posicion_abierta"):
                continue

            if sim not in idx:
                # debounce: pedir 2 lecturas seguidas
                _miss_count[sim] = _miss_count.get(sim, 0) + 1
                if _miss_count[sim] < 2:
                    continue  # esperamos confirmar
                # confirmado cierre
                reg["posicion_abierta"] = False
                estado_pares[sim] = reg
                _last_closed[sim] = time.time()
                _miss_count[sim] = 0

                try:
                    # HeurAAstica motivo + salida
                    salida = get_last_price(sim) or reg.get("entrada_precio", 0.0)
                    side = "LONG" if "COMPRA" in reg["direccion"] else "SHORT"

                    stop_pct = float(reg.get("sl_pct", CFG["riesgo"]["stop_pct"])) / 100.0
                    take_pct = float(reg.get("tp_pct", CFG["riesgo"]["take_pct"])) / 100.0
                    entry = float(reg.get("entrada_precio", salida))

                    if side == "LONG":
                        sl_obj = entry * (1 - stop_pct)
                        tp_obj = entry * (1 + take_pct)
                    else:
                        sl_obj = entry * (1 + stop_pct)
                        tp_obj = entry * (1 - take_pct)

                    f = load_symbol_filters(sim) or {}
                    tick = float((f.get("tick") or 0.0) or 0.0)
                    tol = max(tick * 2.5, entry * 0.0003)  # tolerancia

                    motivo = "Cierre manual/externo"
                    if side == "LONG":
                        if salida <= sl_obj + tol: motivo = "Stop Loss"
                        elif salida >= tp_obj - tol: motivo = "Take Profit"
                    else:
                        if salida >= sl_obj - tol: motivo = "Stop Loss"
                        elif salida <= tp_obj + tol: motivo = "Take Profit"

                    # duraciAA3n real
                    t_in = float(reg.get("ts_entry", 0.0)) or 0.0
                    dur_min = int((time.time() - t_in) / 60) if t_in > 0 else 0

                    qty = float(reg.get("qty", 0.0))
                    if side == "LONG":
                        resultado_pct = ((salida / entry) - 1.0) * 100.0
                        pnl = calcular_pnl("LONG", entry, salida, qty, CFG)
                    else:
                        resultado_pct = ((entry / salida) - 1.0) * 100.0
                        pnl = calcular_pnl("SHORT", entry, salida, qty, CFG)

                    impacto_pct = impacto_sobre_capital(pnl["neto"], CFG)
                    enviar_mensaje(
                        CFG,
                        msg_operacion_cerrada(
                            sim,
                            reg["direccion"],
                            entry,
                            salida,
                            resultado_pct,
                            pnl["neto"],
                            duracion_min=dur_min,
                            impacto_pct=impacto_pct,
                            motivo=motivo,
                        ),
                    )
                except Exception as e:
                    logger.error("No pude notificar cierre %s: %s", sim, e)
                ordenes_24h += 1
            else:
                _miss_count[sim] = 0  # hay posiciAA3n, reseteo

        # 3) AlineaciAA3n SL/TP en vivas
        for sim, p in idx.items():
            try:
                sl_obj, tp_obj = _desired_sl_tp(p["entry_price"], p["side"])
                def _diff_pct(a, b):
                    try:
                        return abs((float(a) - float(b)) / float(b)) * 100.0
                    except Exception:
                        return 100.0
                need_set = (p["sl"] is None or p["tp"] is None) or (_diff_pct(p["sl"], sl_obj) > 0.1) or (_diff_pct(p["tp"], tp_obj) > 0.1)
                if MODO == "real" and need_set:
                    with Section(LOG, "Heartbeat: alinear SL/TP", simbolo=sim, side=p["side"], sl=sl_obj, tp=tp_obj):
                        ok, resp = set_trading_stop(sim, take_profit=tp_obj, stop_loss=sl_obj)
                    if not ok and "not modified" not in str(resp).lower():
                        logger.warning("No pude alinear SL/TP en %s: %s", sim, resp)
            except Exception as e:
                logger.error("AlineaciAA3n SL/TP fallo %s: %s", sim, e)

        guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})
    except Exception as e:
        logger.error("reconciliar_con_exchange_periodico fallo: %s", e)

# ------------------ Utilidades ------------------
def _hay_posicion_en_exchange(simbolo: str) -> bool:
    if MODO != "real":
        return estado_pares.get(simbolo, {}).get("posicion_abierta", False)
    try:
        p = fetch_position_for_symbol(simbolo)
        return bool(p and float(p.get("qty", 0.0)) > 0.0)
    except Exception:
        return estado_pares.get(simbolo, {}).get("posicion_abierta", False)

def reconcile_manual_sl(symbol: str):
    if MODO != "real":
        return
    try:
        pos = fetch_position_for_symbol(symbol)
        if not pos:
            return
        sl_exch = pos.get("stopLoss")
        if not sl_exch:
            return
        reg = estado_pares.get(symbol)
        if not reg:
            return
        reg.setdefault("sl_manual", float(sl_exch))
        estado_pares[symbol] = reg
    except Exception as e:
        logger.debug("reconcile_manual_sl fallo %s: %s", symbol, e)

# --- Notificaciones (sensores no intrusivos) ---------------------------------

def _notify_partial_if_detected(CFG: dict, simbolo: str, reg: dict, precio_actual: float = 0.0):
    """
    Dispara notificaciAA3n de PARCIAL si detecta caAAda de qty sin que la posiciAA3n haya cerrado.
    No modifica la lAA3gica del core. Es 100% opcional y a prueba de fallos.
    """
    try:
        # qty actual y previa
        qty = float(reg.get("qty") or 0.0)
        prev = float(reg.get("_prev_qty", qty))
        reg["_prev_qty"] = qty  # siempre actualizar para el prAA3ximo ciclo

        # Solo si antes habAAa mAAs y ahora todavAAa queda (parcial),
        # y el parcial estAA habilitado por settings.
        if prev > 0 and qty > 0 and qty < prev and CFG.get("partials", {}).get("enabled", True):
            fraction = (prev - qty) / prev
            # SeAAal long/short
            is_long = str(reg.get("direccion", "")).upper().startswith("COMPRA")

            # Precio y pnl con fallbacks
            px = float(
                (reg.get("ultimo_precio") or reg.get("precio_entrada") or precio_actual or 0.0)
            )
            pnl_real = float(reg.get("pnl_realizado") or 0.0)

            # Gatillos configurados (si existen en tu settings)
            P_FRACTION = float(CFG.get("partials", {}).get("fraction", fraction))
            P_AT_R     = float(CFG.get("partials", {}).get("at_R", 0.0))

            notifier.parcial(
                CFG,
                simbolo=simbolo,
                is_long=is_long,
                fraction=float(P_FRACTION if P_FRACTION>0 else fraction),
                pnl_usdt=pnl_real,
                qty_restante=qty,
                precio_ejecucion=px,
                at_r=P_AT_R
            )
    except Exception:
        # Nunca frenar el loop por Telegram o por datos faltantes
        pass


def _notify_trailing_close_if_detected(CFG: dict, simbolo: str, reg: dict, precio_actual: float = 0.0):
    """
    Dispara notificaciAA3n de CIERRE POR TRAILING si detecta transiciAA3n qty>0 -> qty==0
    y hay indicios de trailing activo/marcadores. No frena el bot si algo falta.
    """
    try:
        qty = float(reg.get("qty") or 0.0)
        prev = float(reg.get("_prev_qty_tr", reg.get("qty") or 0.0))
        reg["_prev_qty_tr"] = qty  # snapshot para prAA3xima vuelta

        # CerrAA3 (prev>0 y ahora 0) y estaba trailing activo (o algAAon flag/razAA3n)
        trailing_activo = bool(reg.get("trailing_activo") or reg.get("trailing_active"))
        razon_cierre = str(reg.get("close_reason", "")).lower()
        cerro_por_trailing = (qty == 0 and prev > 0) and (trailing_activo or "trail" in razon_cierre)

        if cerro_por_trailing and CFG.get("trailing", {}).get("enabled", True):
            is_long = str(reg.get("direccion", "")).upper().startswith("COMPRA")
            pnl_real = float(reg.get("pnl_realizado") or 0.0)
            px_cierre = float(
                (reg.get("precio_cierre") or reg.get("ultimo_precio") or precio_actual or 0.0)
            )
            notifier.trailing_close(
                CFG,
                simbolo=simbolo,
                is_long=is_long,
                pnl_usdt=pnl_real,
                precio_cierre=px_cierre,
                distancia_pct=None  # si tenAAs un campo con la distancia del trailing, pasalo acAA
            )
    except Exception:
        pass
# ----------------------------------------------------------------------------- 

# ----------- Diag a Telegram (opcional, sin romper el loop) ------------------
def enviar_diag(cfg, title, **datos):
    from mensajeria.telegram import enviar_mensaje_raw
    lines = [f"AAAAa {title}"]
    for k,v in datos.items():
        lines.append(f"- {k}: {v}")
    try:
        enviar_mensaje_raw(cfg, "\n".join(lines))
        return True
    except Exception as e:
        LOG.exception("No pude enviar diag: %s", e)
        return False

def _ejecutar_parcial_si_corresponde(simbolo: str, reg: dict, precio_actual: float):
    """
    Delega la ejecución del PARCIAL al módulo external (partials.py),
    inyectando CFG/MODO/adapters/notifier/persistencia.
    """
    try:
        # aseguramos que el dict global refleje el reg actualizado
        estado_pares[simbolo] = reg

        return ejecutar_parcial_si_corresponde(
            simbolo=simbolo,
            reg=reg,
            precio_actual=float(precio_actual),
            CFG=CFG,
            MODO=MODO,
            place_market=place_market,
            fetch_position_for_symbol=fetch_position_for_symbol,
            round_qty_to_step=round_qty_to_step,
            notifier=notifier,
            persist=lambda sym, r: guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h}),
        )
    except Exception as e:
        logger.error("ejecutar_parcial_si_corresponde (delegado) fallo %s: %s", simbolo, e)
        return False





def _partial_step(sim, reg, precio):
    """Chequea, ejecuta y loguea el PARCIAL una sola vez por ciclo."""
    # 1) Decidir si corresponde
    try:
        ok, info = should_execute_partial(reg, float(precio), CFG)
    except Exception as e:
        try:
            logger.debug("should_execute_partial fallo %s: %s", sim, e)
        except Exception:
            pass
        return

    # 2) Resolver at_R y fraction reales
    try:
        at_R_res, frac_res = _resolve_partials_cfg(CFG)
    except Exception:
        at_R_res, frac_res = 0.0, 0.0

    # 3) Si no corresponde, traza y salir
    if not ok:
        try:
            motivo = (info or {}).get("reason", "desconocido")
            logger.info(
                "PARCIAL NO (motivo=%s): sym=%s r_now=%.3f at_R=%.3f",
                motivo, sim, float((info or {}).get("r_now", 0.0)), float(at_R_res)
            )
        except Exception:
            pass
        return

    # 4) BLINDAJE min_qty/step (traza previa; el ajuste final lo hace el executor)
    try:
        pos = fetch_position_for_symbol(sim) if "fetch_position_for_symbol" in globals() else {"qty": reg.get("qty", 0.0)}
        qty_open = float(pos.get("qty", reg.get("qty", 0.0)) or 0.0)
        target = qty_open * float(frac_res)

        step = 0.0
        try:
            step = round_qty_to_step(sim, 1.0) - round_qty_to_step(sim, 0.0) if "round_qty_to_step" in globals() else 0.0
        except Exception:
            pass

        if step > 0:
            adj = max(step, round(target / step) * step)
        else:
            adj = target

        logger.info("PARCIAL CHECK: sym=%s open=%.6f fraction=%.2f target=%.6f adj=%.6f step=%.6f",
                    sim, qty_open, float(frac_res), target, adj, step)
    except Exception:
        pass

    # 5) Ejecutar parcial (reduce-only en real + persist + notificación)
    try:
        aplicado = ejecutar_parcial_si_corresponde(
            simbolo=sim,
            reg=reg,
            precio_actual=float(precio),
            CFG=CFG,
            MODO=MODO,
            place_market=place_market if "place_market" in globals() else None,
            fetch_position_for_symbol=fetch_position_for_symbol if "fetch_position_for_symbol" in globals() else None,
            round_qty_to_step=round_qty_to_step if "round_qty_to_step" in globals() else None,
            notifier=notifier if "notifier" in globals() else None,
            persist=lambda sym, r: guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h}) if "guardar_estado" in globals() else None,
        )
    except Exception as e:
        try:
            logger.error("Parcial loop fallo %s: %s", sim, e)
        except Exception:
            pass
        return

    # 6) Log final coherente
    try:
        if aplicado:
            logger.info(
                "PARCIAL PLACED/FILLED: sym=%s r_now=%.3f at_R=%.3f fraction=%.2f qty_rest=%.6f",
                sim,
                float((info or {}).get("r_now", 0.0)),
                float(at_R_res),
                float(frac_res),
                float(reg.get("qty") or 0.0),
            )
        else:
            logger.info(
                "PARCIAL SKIPPED: sym=%s r_now=%.3f at_R=%.3f fraction=%.2f (qty_cerrar=0 o orden no colocada)",
                sim,
                float((info or {}).get("r_now", 0.0)),
                float(at_R_res),
                float(frac_res),
            )
    except Exception:
        pass

def _actualizar_estado_por_senal(simbolo: str, senal: dict):
    if senal.get("accion") not in ("BUY", "SELL"):
        return

    reg = estado_pares.get(simbolo, {"posicion_abierta": False, "entradas": 0})
    if reg.get("posicion_abierta", False):
        return  # anti-piramidado local

    if _hay_posicion_en_exchange(simbolo):
        logger.info(f"[{simbolo}] Bloqueado por anti-piramidado: ya hay posiciA An viva.")
        return

    direccion_txt = "COMPRA (LONG)" if senal["accion"] == "BUY" else "VENTA (SHORT)"
    direccion_tr = "LONG" if senal["accion"] == "BUY" else "SHORT"
    side_bybit = "Buy" if senal["accion"] == "BUY" else "Sell"

    from core.trailing_base import inicializar as tr_init, preparar_posicion as tr_prep
    tr_estado = tr_init(CFG.get("trailing", {}))
    tr_estado = tr_prep(tr_estado, direccion_tr, senal["precio"], CFG)

    qty_calc = calcular_qty(simbolo, senal["precio"], CFG)
    ok_adj, qty_norm, det_adj = adjust_qty_by_filters(simbolo, qty_calc)
    if not ok_adj:
        logger.error("Qty rechazada por filtros (%s): %s -> %s", simbolo, qty_calc, det_adj)
        return

    qty_txt = formatear_qty(simbolo, qty_norm, CFG)
    _ = float(qty_txt)

    entry_price = float(senal["precio"])
    if MODO == "real":
        try:
            set_symbol_leverage(simbolo, lev=int(CFG.get("futuros", {}).get("leverage", 10)))
        except Exception as e:
            logger.warning("No pude setear leverage en %s: %s", simbolo, e)

        ok, resp = place_market(simbolo, side_bybit, qty_norm)
        if not ok:
            logger.error("Fallo orden MARKET %s: %s", simbolo, resp)
            return

        pos = fetch_position_for_symbol(simbolo)
        if not pos or float(pos.get("qty", 0.0)) == 0.0:
            logger.warning("[%s] No hay posiciA An tras place_order; no anuncio entrada.", simbolo)
            return

        entry_price = float(pos.get("avgPrice") or entry_price)
        qty_norm = float(pos.get("qty") or qty_norm)

    # Estado base
    estado_pares[simbolo] = {
        "posicion_abierta": True,
        "direccion": direccion_txt,
        "entrada_precio": entry_price,
        "sl_pct": CFG["riesgo"]["stop_pct"],
        "tp_pct": CFG["riesgo"]["take_pct"],
        "entradas": reg.get("entradas", 0) + 1,
        "trailing": tr_estado,
        "qty": qty_norm,
        "condiciones_al_entrar": senal.get("condiciones", {}),
    }

    # Hora del exchange + condiciones cuantitativas
    cond = senal.get("condiciones", {}) or {}
    vol = cond.get("volumen", {})
    ab = cond.get("ancho_bandas", {})
    bs = cond.get("banda_superior", {})
    ema = cond.get("ema200", {})
    adx = cond.get("adx", {})
    exp = cond.get("expansion", {})

    ts_entry_ms = _exchange_time_ms_fallback()
    estado_pares[simbolo]["ts_entry"] = float(ts_entry_ms) / 1000.0
    guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})

    cond_lines = []
    if ema and ema.get("precio") is not None and ema.get("ema") is not None:
        ok = ema.get("ok", False)
        cond_lines.append(f"{'✅' if ok else '❌'} EMA200 {'ok' if ok else 'no cumple'} (precio {ema['precio']:.2f} vs EMA {ema['ema']:.2f})")
    if adx and adx.get("valor") is not None and adx.get("min_req") is not None:
        ok = adx.get("ok", False)
        cond_lines.append(f"{'✅' if ok else '❌'} ADX {adx['valor']:.2f} {'>=' if ok else '<'} {adx['min_req']:.0f}")
    if exp and exp.get("width_pct") is not None and exp.get("promedio_pct") is not None and exp.get("mult_req") is not None:
        ok = exp.get("ok", False)
        if ok:
            cond_lines.append(f"✅ Expansión de bandas: {exp['width_pct']:.2f}% > {exp['promedio_pct']:.2f}% x {exp['mult_req']:.1f}")
        else:
            cond_lines.append(f"❌ Expansión de bandas: {exp['width_pct']:.2f}% <= {exp['promedio_pct']:.2f}% x {exp['mult_req']:.1f}")
    if vol and vol.get("ratio") is not None and vol.get("min_req") is not None:
        cond_lines.append(f"{'✅' if vol.get('ok', False) else '❌'} Volumen {'suficiente' if vol.get('ok', False) else 'insuficiente'} ({vol['ratio']:.2f} de {vol['min_req']:.2f} requerido)")
    if ab and ab.get("width_pct") is not None and ab.get("min_req_pct") is not None:
        cond_lines.append(f"{'✅' if ab.get('ok', False) else '❌'} Ancho de bandas {'suficiente' if ab.get('ok', False) else 'insuficiente'} ({ab['width_pct']:.2f}% de {ab['min_req_pct']:.2f}% requerido)")
    if bs and "cierre_por_encima" in bs:
        cond_lines.append("✅ Cierre por encima de la banda superior" if bs["cierre_por_encima"] else "❌ Cierre por encima de la banda superior")    
    hora_txt = _fmt_hora_from_ms(ts_entry_ms)
    texto_entrada = (
        f"🚀 Entrada | {simbolo}\n"
        f"{'Compra alcista' if senal['accion'] == 'BUY' else 'Venta bajista'} 📈\n"
        f"Precio: {entry_price:,.2f}\n"
        f"Tamaño: {float(qty_norm):g}\n"
        f"Stop Loss: {CFG['riesgo']['stop_pct']:.2f}%\n"
        f"Take Profit: {CFG['riesgo']['take_pct']:.2f}%\n"
        f"Riesgo: {CFG['riesgo'].get('riesgo_usdt',10.0)} USDT\n"
        f"Tendencia 1h: {senal.get('tendencia_1h','N/A')}\n"
        f"Apalancamiento: x{int(CFG.get('futuros', {}).get('leverage', 10))}\n"
    )
    if cond_lines:
        texto_entrada += "\n" + "\n".join(cond_lines) + "\n"
    texto_entrada += f"Hora: {hora_txt}"

    try:
        enviar_mensaje(CFG, texto_entrada)
    except Exception as e:
        logger.error("No se pudo enviar msg_entrada extendido %s: %s", simbolo, e)

    # Colocar SL/TP
    if senal["accion"] == "BUY":
        sl_precio = entry_price * (1 - CFG["riesgo"]["stop_pct"] / 100.0)
        tp_precio = entry_price * (1 + CFG["riesgo"]["take_pct"] / 100.0)
    else:
        sl_precio = entry_price * (1 + CFG["riesgo"]["stop_pct"] / 100.0)
        tp_precio = entry_price * (1 - CFG["riesgo"]["take_pct"] / 100.0)
    if MODO == "real":
        try:
            ok, resp = set_trading_stop(simbolo, take_profit=tp_precio, stop_loss=sl_precio)
            if not ok and "not modified" not in str(resp).lower():
                logger.error("set_trading_stop fallo %s: %s", simbolo, resp)
        except Exception as e:
            logger.error("set_trading_stop error %s: %s", simbolo, e)
        if not ok and "not modified" not in str(resp).lower():
            logger.error("set_trading_stop fallo %s: %s", simbolo, resp)

    try:
        enviar_mensaje(
            CFG,
            msg_tp_sl_aplicado(
                simbolo,
                CFG["riesgo"]["stop_pct"],
                sl_precio,
                CFG["riesgo"]["take_pct"],
                tp_precio,
                CFG["riesgo"]["relacion"],
                CFG["riesgo"].get("riesgo_usdt", 10.0),
            ),
        )
    except Exception as e:
        logger.error("No se pudo enviar msg_tp_sl_aplicado %s: %s", simbolo, e)


# ------------------ ClasificaciAA3n HEARTBEAT ------------------
def _clasificar_para_heartbeat(senal_por_simbolo: dict):
    operando, disponibles, bloqueados = [], [], []
    for simbolo, s in senal_por_simbolo.items():
        cond = s.get("condiciones", {})
        ok_vol   = cond.get("volumen", {}).get("ok", False)
        ok_ancho = cond.get("ancho_bandas", {}).get("ok", False)

        reconcile_manual_sl(simbolo)

        reg = estado_pares.get(simbolo, {"entradas": 0, "posicion_abierta": False})
        if reg.get("posicion_abierta", False):
            cond_entrar = reg.get("condiciones_al_entrar") or cond
            operando.append({
                "simbolo": simbolo,
                "entradas": reg.get("entradas", 0),
                "posicion_abierta": True,
                "direccion": reg.get("direccion", "COMPRA (LONG)"),
                "entrada_precio": reg.get("entrada_precio", s.get("precio", 0.0)),
                "sl_pct": reg.get("sl_pct", CFG["riesgo"]["stop_pct"]),
                "tp_pct": reg.get("tp_pct", CFG["riesgo"]["take_pct"]),
                "condiciones": cond_entrar,
            })
        else:
            if ok_ancho and ok_vol:
                disponibles.append({"simbolo": simbolo, "entradas": reg.get("entradas", 0), "condiciones": cond})
            else:
                bloqueados.append({
                    "simbolo": simbolo,
                    "entradas": reg.get("entradas", 0),
                    "condiciones": cond,
                    "ultimo_intento_utc": _hora_exchange_str(),
                })
    return operando, disponibles, bloqueados

def _enviar_heartbeat_con_estado(senal_por_simbolo: dict):
    operando, disponibles, bloqueados = _clasificar_para_heartbeat(senal_por_simbolo)
    texto = msg_heartbeat_detallado(
        capital_total=CFG.get("capital", {}).get("total_usdt", 0.0),
        hora_utc=_hora_exchange_str(),
        operando=operando,
        disponibles=disponibles,
        bloqueados=bloqueados,
        total_ordenes_24h=ordenes_24h,
    )
    try:
        enviar_mensaje(CFG, texto)
    except Exception as e:
        logger.error("No se pudo enviar HEARTBEAT: %s", e)

# ------------------ Loop principal ------------------

def _partial_startup_if_needed(sim: str, reg: dict):
    """
    Ejecuta parcial al arrancar si la posición ya cumple el trigger (at_R / trigger_R).
    No rompe el loop si falla algo.
    """
    try:
        # Precio actual para evaluar R_now
        try:
            precio_actual = float(get_last_price(sim))
        except Exception:
            precio_actual = float(reg.get("entrada_precio", 0.0))

        ok, info = should_execute_partial(reg, precio_actual, CFG)
        if not ok:
            logger.info(
                "PARCIAL STARTUP NO: sym=%s motivo=%s r_now=%.3f at_R=%.3f",
                sim,
                (info or {}).get("reason", "below_threshold"),
                float((info or {}).get("r_now", 0.0)),
                float(_resolve_partials_cfg(CFG)[0]),
            )
            return False

        aplicado = ejecutar_parcial_si_corresponde(
            simbolo=sim,
            reg=reg,
            precio_actual=precio_actual,
            CFG=CFG,
            MODO=MODO,
            place_market=place_market if "place_market" in globals() else None,
            fetch_position_for_symbol=fetch_position_for_symbol if "fetch_position_for_symbol" in globals() else None,
            round_qty_to_step=round_qty_to_step if "round_qty_to_step" in globals() else None,
            notifier=notifier if "notifier" in globals() else None,
            persist=lambda s, r: guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})
        )

        logger.info(
            "%s: sym=%s r_now=%.3f at_R=%.3f fraction=%.2f qty_rest=%.6f",
            "PARCIAL STARTUP PLACED" if aplicado else "PARCIAL STARTUP SKIPPED",
            sim,
            float((info or {}).get("r_now", 0.0)),
            float(_resolve_partials_cfg(CFG)[0]),
            float(_resolve_partials_cfg(CFG)[1]),
            float(reg.get("qty") or 0.0),
        )
        return aplicado
    except Exception as e:
        logger.error("PARCIAL STARTUP fallo %s: %s", sim, e)
        return False


def loop():
    global ordenes_24h, estado_pares

    # Inicializar estrategia
    for sim in SIMBOLOS:
        try:
            estado_estrategia[sim] = estr_init(CFG.get("estrategia", {}))
        except Exception as e:
            logger.error("estr_init fallo %s: %s", sim, e)

    # ReconciliaciAA3n de arranque
    try:
        seguridad_al_iniciar()
    except Exception as e:
        logger.error("seguridad_al_iniciar fallo: %s", e)

    _enviar_heartbeat_con_estado({})
    ultimo_hb = time.time()
    intervalo = int(CFG.get("heartbeat", {}).get("cada_minutos", 30)) * 60

    ultimo_sync = time.time()
    sync_interval = 15  # s

    from core.trailing_base import inicializar as tr_init, preparar_posicion as tr_prep, actualizar as tr_update

    while True:
        try:
            senal_por_simbolo = {}

            # 1) SeAAales
            for sim in SIMBOLOS:
                try:
                    velas = obtener_velas(sim, CFG["estrategia"]["tf"], 250)
                except Exception as e:
                    logger.error("obtener_velas() fallo %s: %s", sim, e)
                    continue

                try:
                    s = generar_senal(velas, estado_estrategia.get(sim, {}), CFG)
                    senal_por_simbolo[sim] = s
                    _actualizar_estado_por_senal(sim, s)
                except Exception as e:
                    logger.error("generar_senal/_actualizar_estado fallo %s: %s", sim, e)

            # 2) Trailing + (SIM: cierres por TP/SL)
            now = time.time()
            for sim, reg in list(estado_pares.items()):
                try:
                    if not reg.get("posicion_abierta"):
                        continue

                    direccion = "LONG" if "COMPRA" in reg["direccion"] else "SHORT"
                    try:
                        velas_sim = obtener_velas(sim, CFG["estrategia"]["tf"], 250)
                        precio = velas_sim[-1]["close"]
                        # === Sensores de notificaciones (parcial / trailing) ===
                        _notify_partial_if_detected(CFG, sim, reg, float(precio))
                        _notify_trailing_close_if_detected(CFG, sim, reg, float(precio))
                        # === fin sensores ===
                        # ---- Diag del parcial (R/MFE y motivo de skip) ----
                        _partial_step(sim, reg, float(precio))
                    except Exception as e:
                        logger.error("obtener_velas() fallo %s: %s", sim, e)
                        continue

                    tr_estado = reg.get("trailing")
                    if tr_estado is None:
                        tr_estado = tr_init(CFG.get("trailing", {}))
                        tr_estado = tr_prep(tr_estado, direccion, reg["entrada_precio"], CFG)

                    upd = tr_update(tr_estado, precio, CFG)
                    tr_estado.update({"activo": upd["activo"], "sl": upd["sl"], "tp": upd["tp"]})
                    reg["trailing"] = tr_estado

                    # ---------------- Trailing Stop (solo notifica si se aplicAA3) ----------------
                    umbral = float(_cfg_section(CFG, 'trailing').get("min_mov_sl_pct", 0.05))
                    prev_notif_sl = reg["trailing"].get("ultimo_sl_notificado")
                    prev_ts = reg["trailing"].get("ultimo_ts_notif", 0.0)
                    nuevo_sl = upd["sl"]
                    logger.info("TRAILING CHECK: sym=%s last_sl=%s next_sl=%s min_move=%.4f%% buffer=%.4f%%", sim, str(prev_notif_sl), str(nuevo_sl), float(CFG.get("trailing", {}).get("min_mov_sl_pct", 0.05)), float(CFG.get("trailing", {}).get("buffer_pct", 0.0)))

                    def _round_to_tick(sym, price):
                        try:
                            f = load_symbol_filters(sym) or {}
                            tick = float(f.get("tick") or 0.0)
                            if tick and tick > 0:
                                return round(round(price / tick) * tick, 8)
                        except Exception:
                            pass
                        return round(price, 8)

                    def _monotono(side_txt, prev_sl, new_sl):
                        if prev_sl is None:
                            return True
                        if "COMPRA" in side_txt:
                            return new_sl >= prev_sl
                        else:
                            return new_sl <= prev_sl

                    aplica_candidato = False
                    if upd["movido"] and nuevo_sl is not None:
                        if prev_notif_sl is not None and prev_notif_sl > 0:
                            delta_pct = abs((nuevo_sl - prev_notif_sl) / prev_notif_sl) * 100.0
                            if delta_pct >= umbral:
                                aplica_candidato = True
                        else:
                            aplica_candidato = True

                    if aplica_candidato and (now - float(prev_ts) < TRAILING_COOLDOWN):
                        aplica_candidato = False
                    if aplica_candidato and not _monotono(reg.get("direccion", ""), prev_notif_sl, nuevo_sl):
                        aplica_candidato = False

                    if aplica_candidato:
                        try:
                            nuevo_sl_ex = _round_to_tick(sim, float(nuevo_sl))

                            aplicado_en_exchange = False
                            if MODO == "real":
                                with Section(LOG, "Trailing mover SL", simbolo=sim, nuevo_sl=nuevo_sl_ex):
                                    ok_set, resp = set_trading_stop(sim, take_profit=None, stop_loss=nuevo_sl_ex)
                                if ok_set:
                                    aplicado_en_exchange = True
                                else:
                                    if "not modified" in str(resp).lower():
                                        logger.info("[Bybit] trailing no cambiAA3 en %s: %s", sim, resp)
                                    else:
                                        logger.warning("[Bybit] fallo al mover SL trailing en %s: %s", sim, resp)
                            else:
                                aplicado_en_exchange = True  # en SIM

                            if aplicado_en_exchange:
                                pivote_tf = _cfg_section(CFG, 'trailing').get("pivote_tf", "15m")
                                pivote_tf_txt = "15 minutos" if pivote_tf == "15m" else pivote_tf
                                enviar_mensaje(
                                    CFG,
                                    msg_trailing_seguimiento(
                                        sim, pivote_tf_txt, _cfg_section(CFG, 'trailing')["buffer_pct"], nuevo_sl_ex
                                    ) + f"\nHora: {_hora_exchange_str()}"
                                )

                                reg["trailing"]["ultimo_sl_notificado"] = float(nuevo_sl_ex)
                                reg["trailing"]["ultimo_ts_notif"] = now
                                guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})

                        except Exception as e:
                            logger.error("No se pudo aplicar/enviar trailing %s: %s", sim, e)
                    else:
                        logger.info("TRAILING SKIPPED: sym=%s reason=not_modified_or_below_min_move", sim)

                    # CIERRES SOLO EN SIM
                    if MODO != "real":
                        sl, tp = upd["sl"], upd["tp"]
                        cerro, motivo, salida = False, "", precio

                        if direccion == "LONG":
                            if tp is not None and precio >= tp:
                                cerro, motivo, salida = True, "Take Profit", tp
                            elif sl is not None and precio <= sl:
                                cerro, motivo, salida = True, "Stop Loss", sl
                        else:
                            if tp is not None and precio <= tp:
                                cerro, motivo, salida = True, "Take Profit", tp
                            elif sl is not None and precio >= sl:
                                cerro, motivo, salida = True, "Stop Loss", sl

                        if cerro:
                            entrada = reg["entrada_precio"]
                            qty = float(reg.get("qty", 0.0))
                            if direccion == "LONG":
                                resultado_pct = ((salida / entrada) - 1.0) * 100.0
                                pnl = calcular_pnl("LONG", entrada, salida, qty, CFG)
                            else:
                                resultado_pct = ((entrada / salida) - 1.0) * 100.0
                                pnl = calcular_pnl("SHORT", entrada, salida, qty, CFG)

                            impacto_pct = impacto_sobre_capital(pnl["neto"], CFG)
                            try:
                                enviar_mensaje(
                                    CFG,
                                    msg_operacion_cerrada(
                                        sim,
                                        reg["direccion"],
                                        entrada,
                                        salida,
                                        resultado_pct,
                                        pnl["neto"],
                                        duracion_min=64,
                                        impacto_pct=impacto_pct,
                                        motivo=motivo,
                                    ),
                                )
                            except Exception as e:
                                logger.error("No se pudo enviar cierre %s: %s", sim, e)

                            logger.info("CIERRE (SIM) %s %s entrada=%.6f salida=%.6f pnl_neto=%.2f",
                                        sim, motivo, entrada, salida, pnl["neto"])
                            reg["posicion_abierta"] = False
                            estado_pares[sim] = reg
                            ordenes_24h += 1
                            _last_closed[sim] = time.time()
                            guardar_estado({"pares": estado_pares, "ordenes_24h": ordenes_24h})

                except Exception as e:
                    logger.error("Loop trailing/cierre fallo %s: %s", sim, e)

            # 3) Heartbeat
            if time.time() - ultimo_hb >= intervalo:
                _enviar_heartbeat_con_estado(senal_por_simbolo)
                ultimo_hb = time.time()

            # 4) ReconciliaciAA3n periAA3dica con exchange
            if MODO == "real" and (time.time() - ultimo_sync >= sync_interval):
                reconciliar_con_exchange_periodico()
                ultimo_sync = time.time()

            time.sleep(5)

        except Exception as e:
            logger.exception("IteraciAA3n principal fallo: %s", e)
            time.sleep(2.0)

def main():
    try:
        loop()
    except KeyboardInterrupt:
        print("AAA1A A A Bot detenido por el usuario.")
    except Exception as e:
        logger.exception(f"FATAL: {e}")
        try:
            enviar_mensaje(CFG, "?? Error cr atico en el bot. Revisando logs y reintentando")
        except Exception:
            pass
def _cfg_section(cfg, name, plural_fallback=True, default=None):
    if default is None:
        default = {}
    try:
        v = cfg.get(name)
        if isinstance(v, dict):
            return v
        if plural_fallback:
            alt = f"{name}s"
            v = cfg.get(alt)
            if isinstance(v, dict):
                return v
    except Exception:
        pass
    return default


if __name__ == "__main__":
    print(f"CORE EN EJECUCIÓN: {__file__}")
    main()
