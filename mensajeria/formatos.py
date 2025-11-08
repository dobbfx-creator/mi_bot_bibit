# -*- coding: utf-8 -*-
# Formatos de mensajes en español, sin símbolos raros.

from typing import List, Dict, Any, Optional

def _fmt_num(x, dec=2):
    try:
        return f"{float(x):,.{dec}f}"
    except Exception:
        return str(x)

def _fmt_pct(x, dec=2):
    try:
        return f"{float(x):.{dec}f}%"
    except Exception:
        return str(x)

def _linea_condiciones(cond: Dict[str, Any]) -> List[str]:
    lineas = []

    # Volumen relativo
    vol = cond.get("volumen", {})
    if vol:
        ratio = vol.get("ratio"); req = vol.get("min_req"); ok = vol.get("ok", False)
        if ratio is not None and req is not None:
            lineas.append(
                f"{'✅' if ok else '❌'} Volumen {'suficiente' if ok else 'insuficiente'} ({ratio:.2f} de {req:.2f} requerido)"
            )

    # Ancho de bandas
    ab = cond.get("ancho_bandas", {})
    if ab:
        width = ab.get("width_pct"); req = ab.get("min_req_pct"); ok = ab.get("ok", False)
        if width is not None and req is not None:
            lineas.append(
                f"{'✅' if ok else '❌'} Ancho de bandas {'suficiente' if ok else 'insuficiente'} ({width:.2f}% de {req:.2f}% requerido)"
            )

    # Cierre por encima de banda superior (si aplica)
    bs = cond.get("banda_superior", {})
    if bs and "cierre_por_encima" in bs:
        lineas.append(
            "✅ Cierre por encima de la banda superior" if bs["cierre_por_encima"]
            else "❌ Cierre por encima de la banda superior"
        )

    # EMA200
    ema = cond.get("ema200", {})
    if ema:
        ok = ema.get("ok", False); precio = ema.get("precio"); ema_val = ema.get("ema")
        if precio is not None and ema_val is not None:
            lineas.append(
                f"{'✅' if ok else '❌'} EMA200 {'ok' if ok else 'no cumple'} (precio {precio:.2f} vs EMA {ema_val:.2f})"
            )

    # EMA200 Slope
    slope = cond.get("ema200_slope", {})
    if slope:
        ok = slope.get("ok", True)
        val = slope.get("valor_pct_bar"); req = slope.get("min_req_pct_bar")
        if val is not None and req is not None:
            lineas.append(
                f"{'✅' if ok else '❌'} Pendiente EMA200: {val:.3f}%/vela (mín {req:.3f}%/vela)"
            )

    # RSI Guard
    rsi = cond.get("rsi_guard", {})
    if rsi:
        ok = rsi.get("ok", True)
        rv = rsi.get("rsi"); d = rsi.get("delta")
        min_long = rsi.get("min_long"); max_short = rsi.get("max_short"); dmin = rsi.get("delta_min"); ob = rsi.get("overbought")
        base = f"RSI {rv:.2f}" if rv is not None else "RSI"
        extras = []
        if d is not None: extras.append(f"Δ {d:.2f} (mín {dmin})")
        if min_long is not None: extras.append(f"long ≥ {min_long}")
        if max_short is not None: extras.append(f"short ≤ {max_short}")
        if ob is not None: extras.append(f"OB ≤ {ob}")
        joined = " | ".join(extras) if extras else ""
        lineas.append(f"{'✅' if ok else '❌'} {base}{(' – ' + joined) if joined else ''}")

    # ADX
    adx = cond.get("adx", {})
    if adx:
        val = adx.get("valor"); req = adx.get("min_req"); ok = adx.get("ok", False)
        if val is not None and req is not None:
            lineas.append(f"{'✅' if ok else '❌'} ADX {val:.2f} {'≥' if ok else '<'} {req:.0f}")

    # ADX Rising
    adxr = cond.get("adx_rising", {})
    if adxr:
        ok = adxr.get("ok", True); cur = adxr.get("actual"); prev = adxr.get("previo"); dmin = adxr.get("delta_min")
        if None not in (cur, prev, dmin):
            lineas.append(f"{'✅' if ok else '❌'} ADX subiendo: {cur:.2f} - {prev:.2f} (mín Δ {dmin:.2f})")

    # Expansión
    exp = cond.get("expansion", {})
    if exp:
        ok = exp.get("ok", False); width = exp.get("width_pct"); prom = exp.get("promedio_pct"); mult = exp.get("mult_req")
        if None not in (width, prom, mult):
            lineas.append(f"{'✅' if ok else '❌'} Expansión de bandas: {width:.2f}% {'>' if ok else '≤'} {prom:.2f}% x {mult:.1f}")

    # Distancia mínima a EMA200
    md = cond.get("min_dist_ema200", {})
    if md:
        ok = md.get("ok", True); dist = md.get("dist_pct"); mreq = md.get("min_req_pct")
        if dist is not None and mreq is not None:
            lineas.append(f"{'✅' if ok else '❌'} Distancia a EMA200: {dist:.3f}% {'≥' if ok else '<'} {mreq:.3f}%")

    # Retest por ATR
    br = cond.get("breakout_retest", {})
    if br:
        ok = br.get("ok", True); am = br.get("atr_mult_req"); cb = br.get("confirm_bars")
        if am is not None and cb is not None:
            lineas.append(f"{'✅' if ok else '❌'} Retest por ATR: mult {am:.2f}, confirm {int(cb)} vela(s)")

    # ATR (dato)
    atr_info = cond.get("atr", {})
    if atr_info and atr_info.get("valor") is not None:
        lineas.append(f"ATR({int(atr_info.get('periodo', 14))}): {atr_info['valor']:.2f}")

    # ATR guard (si lo usás)
    atrg = cond.get("atr_guard", {})
    if atrg:
        lineas.append(f"{'✅' if atrg.get('ok', True) else '❌'} Guard ATR")

    return lineas

# ---------------------------------------------------------------------
# ENTRADA
# ---------------------------------------------------------------------

def msg_entrada_ext(
    simbolo: str,
    direccion_txt: str,
    precio_entrada: float,
    tamanio: float,
    stop_pct: float,
    take_pct: float,
    riesgo_usdt: float,
    tendencia_1h: str,
    apalancamiento: int,
    condiciones: Optional[Dict[str, Any]] = None,
    hora_utc: Optional[str] = None
    ) -> str:
    lineas = []
    lineas.append(f"Entrada | {simbolo}")
    lineas.append(f"Dirección: {direccion_txt}")
    lineas.append(f"Precio: {_fmt_num(precio_entrada, 2)}")
    lineas.append(f"Tamaño: {tamanio:g}")
    lineas.append(f"Stop Loss: {_fmt_pct(stop_pct, 2)}")
    lineas.append(f"Take Profit: {_fmt_pct(take_pct, 2)}")
    lineas.append(f"Riesgo: {riesgo_usdt:g} USDT")
    lineas.append(f"Tendencia 1h: {tendencia_1h}")
    lineas.append(f"Apalancamiento: x{int(apalancamiento)}")

    if condiciones:
        lineas.append("")
        lineas.extend(_linea_condiciones(condiciones))

    if hora_utc:
        lineas.append(f"Hora: {hora_utc}")

    return "\n".join(lineas)

# Compat: entrada básica
def msg_entrada(simbolo: str, direccion_txt: str, precio_entrada: float, tamanio: float, apalancamiento: int, hora_utc: Optional[str] = None) -> str:
    lineas = [
        f"Entrada | {simbolo}",
        f"Dirección: {direccion_txt}",
        f"Precio: {_fmt_num(precio_entrada, 2)}",
        f"Tamaño: {tamanio:g}",
        f"Apalancamiento: x{int(apalancamiento)}",
    ]
    if hora_utc:
        lineas.append(f"Hora: {hora_utc}")
    return "\n".join(lineas)

def msg_tp_sl_aplicado(simbolo: str, sl_pct: float, sl_precio: float, tp_pct: float, tp_precio: float, relacion: str, riesgo_usdt: float) -> str:
    return (
        f"TP/SL aplicado | {simbolo}\n"
        f"Stop Loss: {_fmt_pct(sl_pct, 2)} a {_fmt_num(sl_precio, 2)}\n"
        f"Take Profit: {_fmt_pct(tp_pct, 2)} a {_fmt_num(tp_precio, 2)}\n"
        f"Relación: {relacion}\n"
        f"Riesgo: {riesgo_usdt:g} USDT"
    )

# ---------------------------------------------------------------------
# HEARTBEAT
# ---------------------------------------------------------------------

def _bloque_operando(operando: List[Dict[str, Any]]) -> str:
    if not operando:
        return ""
    out = ["📈 Operando (posición abierta)"]
    for it in operando:
        cond = it.get("condiciones", {}) or {}
        lineas_cond = _linea_condiciones(cond)
        out.append(f"- {it.get('simbolo')} | Entradas: {it.get('entradas', 0)} | Posición: ✅")
        out.append(f"  Dirección: {it.get('direccion', '—')}")
        out.append(f"  Entrada: {_fmt_num(it.get('entrada_precio', 0.0), 2)} USDT")
        out.append(f"  Stop Loss: {_fmt_pct(it.get('sl_pct', 0.0), 2)} | Take Profit: {_fmt_pct(it.get('tp_pct', 0.0), 2)}")
        if lineas_cond:
            out.append("  Condiciones al entrar:")
            for ln in lineas_cond:
                out.append("  " + ln)
    return "\n".join(out)

def _bloque_disponibles(disponibles: List[Dict[str, Any]]) -> str:
    if not disponibles:
        return ""
    out = ["✅ Disponibles (sin entrada actual)"]
    for it in disponibles:
        cond = it.get("condiciones", {}) or {}
        lineas_cond = _linea_condiciones(cond)
        out.append(f"- {it.get('simbolo')} | Entradas: {it.get('entradas', 0)} | Posición: ❌")
        if lineas_cond:
            out.append("  Condiciones:")
            for ln in lineas_cond:
                out.append("  " + ln)
    return "\n".join(out)

def _bloque_bloqueados(bloqueados: List[Dict[str, Any]]) -> str:
    if not bloqueados:
        return ""
    out = ["⛔ Bloqueados"]
    for it in bloqueados:
        cond = it.get("condiciones", {}) or {}
        lineas_cond = _linea_condiciones(cond)
        out.append(f"- {it.get('simbolo')} | Entradas: {it.get('entradas', 0)}")
        if it.get("ultimo_intento_utc"):
            out.append(f"  Último intento: {it['ultimo_intento_utc']}")
        if lineas_cond:
            out.append("  Condiciones:")
            for ln in lineas_cond:
                out.append("  " + ln)
    return "\n".join(out)

def msg_heartbeat_detallado(
    capital_total: float,
    hora_utc: Optional[str],
    operando: List[Dict[str, Any]],
    disponibles: List[Dict[str, Any]],
    bloqueados: List[Dict[str, Any]],
    total_ordenes_24h: int
) -> str:
    partes = []
    partes.append("🔄 HEARTBEAT")
    partes.append(f"Capital total: {_fmt_num(capital_total, 2)} USDT")
    if hora_utc:
        partes.append(f"Hora: {hora_utc}")
    partes.append("")
    partes.append("Estado de los pares:")
    partes.append("")

    bloque = _bloque_operando(operando)
    if bloque:
        partes.append(bloque)
        partes.append("")

    bloque = _bloque_disponibles(disponibles)
    if bloque:
        partes.append(bloque)
        partes.append("")

    bloque = _bloque_bloqueados(bloqueados)
    if bloque:
        partes.append(bloque)
        partes.append("")

    partes.append(f"Total de órdenes ejecutadas en 24h: {int(total_ordenes_24h)}")
    return "\n".join(partes)
    
# ---------------------------------------------------------------------
# TRAILING y CIERRES
# ---------------------------------------------------------------------

def msg_trailing_seguimiento(simbolo: str, pivote_tf_txt: str, buffer_pct: float, nuevo_sl: float) -> str:
    return (
        f"Trailing seguimiento | {simbolo}\n"
        f"Pivote: {pivote_tf_txt}\n"
        f"Buffer: {_fmt_pct(buffer_pct, 2)}\n"
        f"Stop Loss movido a: {_fmt_num(nuevo_sl, 2)}"
    )

def msg_operacion_cerrada(
    simbolo: str,
    direccion: str,
    precio_entrada: float,
    precio_salida: float,
    resultado_pct: float,
    pnl_neto_usdt: float,
    duracion_min: int,
    impacto_pct: float,
    motivo: str
) -> str:
    res = f"{resultado_pct:.2f}%"
    pnl = f"{pnl_neto_usdt:.2f} USDT"
    imp = f"{impacto_pct:.2f}%"
    return (
        f"Operación CERRADA\n"
        f"Símbolo: {simbolo}\n"
        f"Dirección: {direccion}\n"
        f"Entrada: {_fmt_num(precio_entrada, 2)}\n"
        f"Salida: {_fmt_num(precio_salida, 2)}\n"
        f"Resultado: {res} ({pnl} neto)\n"
        f"Duración: {int(duracion_min)} minutos\n"
        f"Impacto: {imp} del capital\n"
        f"Motivo de cierre: {motivo}"
    )
def msg_trailing_modo(simbolo, modo, motivo, hora):
    return (
        "🎯 Trailing: modo cambiado\n"
        f"Símbolo: {simbolo}\n"
        f"Nuevo modo: {modo}\n"
        f"Motivo: {motivo}\n"
        f"Hora: {hora}"
    )


def msg_trailing_aplicado(simbolo, modo, base_desc, pivot_tf, sl_nuevo, sl_anterior, distancia, hora):
    return (
        "🔧 Trailing aplicado\n"
        f"Símbolo: {simbolo}\n"
        f"Modo: {modo}\n"
        f"Base: {base_desc}\n"
        f"Pivote: {pivot_tf}\n"
        f"SL nuevo: {sl_nuevo:.2f}\n"
        f"SL anterior: {sl_anterior:.2f}\n"
        f"Distancia a precio: {distancia:.2f}%\n"
        f"Hora: {hora}"
    )


def msg_trailing_lock(simbolo, sl_nuevo, mfe_pullback_pct, lock_pct, hora):
    return (
        "🔧 Trailing aplicado\n"
        f"Símbolo: {simbolo}\n"
        "Modo: Agresivo (lock activado)\n"
        f"Retroceso MFE: {mfe_pullback_pct}%\n"
        f"SL nuevo: {sl_nuevo:.2f}\n"
        f"Ganancia asegurada: {lock_pct}%\n"
        f"Hora: {hora}"
    )


def msg_trailing_estado(enabled, modo_inicial, hora):
    return (
        "⚙️ Trailing inteligente\n"
        f"Estado: {'Activado' if enabled else 'Desactivado'}\n"
        f"Modo actual: {modo_inicial}\n"
        f"Hora: {hora}"
    )



# ======================
# Notificaciones nuevas
# ======================

def _fmt_side(side_long: bool) -> str:
    return "LONG" if side_long else "SHORT"

def msg_parcial_ejecutado(simbolo: str, side_long: bool, fraction: float, pnl_usdt: float,
                          qty_restante: float, precio_ejecucion: float, at_r: float) -> str:
    lineas = [
        f"✅ Parcial ejecutado | {simbolo}",
        f"Dirección: {_fmt_side(side_long)}",
        f"Fracción: {fraction:.2f}",
        f"Ganancia realizada: {pnl_usdt:.2f} USDT 💰",
        f"Cantidad restante: {qty_restante:g}",
        f"Precio ejecución: {precio_ejecucion:.4f}",
        f"Nivel alcanzado: {at_r:.2f}R 🎯",
    ]
    return "\n".join(lineas)

def msg_cierre_trailing(simbolo: str, side_long: bool, precio_entrada: float, precio_salida: float,
                        pnl_pct: float, pnl_usdt: float, duracion_str: str, motivo: str = "Trailing Stop") -> str:
    signo = "+" if pnl_pct >= 0 else ""
    lineas = [
        f"🔔 Cierre por {motivo} | {simbolo}",
        f"Dirección: {_fmt_side(side_long)}",
        f"Entrada: {precio_entrada:.4f}",
        f"Salida: {precio_salida:.4f}",
        f"Resultado: {signo}{pnl_pct:.2f}% ({pnl_usdt:.2f} USDT)",
        f"Duración: {duracion_str} ⏱️",
    ]
    return "\n".join(lineas)

def msg_parcial_ejecutada_fmt(symbol: str, side: str, pct: float, price: float | None, pnl_pct: float | None, ts: str | None = None) -> str:
    t = ts or ""
    px = f"{price:.4f}" if isinstance(price, (int, float)) else "—"
    pnl = f"{pnl_pct:.2f}%" if isinstance(pnl_pct, (int, float)) else "—"
    return (
        f"✅ Parcial ejecutada {pct:.0f}% | {symbol} [{side}]\n"
        f"Precio: {px} | PnL: {pnl}\n"
        f"{t}"
    ).strip()

def msg_cierre_trailing_fmt(symbol: str, side: str, price: float | None, pnl_pct: float | None, reason: str = "TSL", ts: str | None = None) -> str:
    t = ts or ""
    px = f"{price:.4f}" if isinstance(price, (int, float)) else "—"
    pnl = f"{pnl_pct:.2f}%" if isinstance(pnl_pct, (int, float)) else "—"
    return (
        f"🔒 Cierre por trailing | {symbol} [{side}]\n"
        f"Salida: {px} | PnL: {pnl} | Motivo: {reason}\n"
        f"{t}"
    ).strip()

