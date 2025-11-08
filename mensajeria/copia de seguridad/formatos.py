
# -*- coding: utf-8 -*-
"""
Mensajería de formatos para BiBIT - compatible con runner y con demo.
Incluye: Entrada, TP/SL aplicado, Heartbeat detallado, Trailing, Cierre, Posición manual, Parcial.
Admite alias y variaciones de nombres de parámetros que se usaron en distintos lugares.
"""

from typing import Any, Dict, List, Iterable, Optional, Union

Number = Union[int, float]

# -------------------------- utilidades de formato --------------------------

def _fmt_num(n: Any, dec: int = 2) -> str:
    """Formatea números con separador de miles y decimales. Tolerante a strings."""
    if isinstance(n, str):
        # Quitar 'x' o comillas comunes de inputs como 'x10' o "111,452.00"
        ns = n.strip().lower().replace('x', '').replace(',', '')
        try:
            n = float(ns)
        except Exception:
            return n  # devolver tal cual si no es número
    try:
        return f"{float(n):,.{dec}f}"
    except Exception:
        return str(n)

def _fmt_pct(p: Any, dec: int = 2) -> str:
    if p is None:
        return "--"
    if isinstance(p, str):
        s = p.strip().replace('%', '')
        try:
            p = float(s)
        except Exception:
            return p
    return f"{float(p):.{dec}f}%"

def _fmt_qty(q: Any) -> str:
    if isinstance(q, str):
        try:
            q = float(q)
        except Exception:
            return q
    # Cantidades cortas sin ceros innecesarios
    if float(q).is_integer():
        return f"{int(q)}"
    return f"{float(q):g}"

def _fmt_hora(h: Optional[str]) -> str:
    if not h:
        return "(test)"
    # Añadir sufijo UTC si parece una hora HH:MM sin sufijo
    if all(c.isdigit() or c==':' for c in h) and "UTC" not in h.upper():
        return f"{h} UTC"
    return h

def _bool_icon(ok: Optional[bool]) -> str:
    return "✅" if ok else "❌"

def _direccion_txt(direccion: Optional[str], side: Optional[str]=None) -> str:
    # Normaliza texto de dirección a "COMPRA (LONG)" / "VENTA (SHORT)"
    t = (direccion or side or "").strip().lower()
    if "long" in t or "compra" in t or t == "buy":
        return "COMPRA (LONG)"
    if "short" in t or "venta" in t or t == "sell":
        return "VENTA (SHORT)"
    # fallback
    return direccion or side or "—"

def _apalancamiento_str(apalancamiento: Any=None, leverage: Any=None) -> str:
    val = apalancamiento if apalancamiento is not None else leverage
    if val is None or val == "":
        return "x10"
    s = str(val).strip().lower()
    if s.startswith('x'):
        s = s[1:]
    try:
        iv = int(float(s))
        return f"x{iv}"
    except Exception:
        return f"x{val}"

# -------------------------- bloques para heartbeat --------------------------

def _linea_operando(it: Dict[str, Any]) -> str:
    simb = it.get("simbolo") or it.get("symbol") or "--"
    entradas = it.get("entradas") or it.get("entries") or 0
    pos_ok = it.get("posicion_abierta") or it.get("open", True)
    dir_txt = _direccion_txt(it.get("direccion"), it.get("side"))
    entrada = _fmt_num(it.get("entrada") or it.get("entry") or it.get("entry_price"))
    sl_pct = _fmt_pct(it.get("sl_pct") if it.get("sl_pct") is not None else it.get("stop_loss_pct", 1.0))
    tp_pct = _fmt_pct(it.get("tp_pct") if it.get("tp_pct") is not None else it.get("take_profit_pct", 5.0))

    cond = it.get("condiciones", {}) or {}
    bb_break = cond.get("bb_break")
    vol_ok = cond.get("vol_ok")
    vol_val = cond.get("vol_val")
    vol_req = cond.get("vol_req")
    ancho_ok = cond.get("ancho_ok")
    ancho_val = cond.get("ancho_val")
    ancho_req = cond.get("ancho_req")

    lineas = [
        f"- {simb} | Entradas: {entradas} | Posición: {'✅' if pos_ok else '❌'}",
        f"  Dirección: {dir_txt}",
        f"  Entrada: {entrada} USDT",
        f"  Stop Loss: {sl_pct} | Take Profit: {tp_pct}",
        "  Condiciones al entrar:",
        f"  {_bool_icon(bb_break)} Cierre por encima de la banda superior",
        f"  {_bool_icon(vol_ok)} Volumen suficiente ({_fmt_num(vol_val,2)} de {_fmt_num(vol_req,2)} requerido)" if vol_val is not None and vol_req is not None else f"  {_bool_icon(vol_ok)} Volumen suficiente",
        f"  {_bool_icon(ancho_ok)} Ancho de bandas suficiente ({_fmt_num(ancho_val,2)}% de {_fmt_num(ancho_req,2)}% requerido)" if ancho_val is not None and ancho_req is not None else f"  {_bool_icon(ancho_ok)} Ancho de bandas suficiente",
    ]
    return "\n".join(lineas)

def _bloque_lista_pos(lista: Any, titulo_icono: str) -> str:
    if isinstance(lista, str):
        if lista.strip():
            return f"{titulo_icono}\n{lista.strip()}"
        return f"{titulo_icono}\n(ninguno)"
    if not lista:
        return f"{titulo_icono}\n(ninguno)"
    # lista de dicts
    return f"{titulo_icono}\n" + "\n".join(_linea_operando(it) for it in lista)

# -------------------------- mensajes públicos --------------------------

def msg_entrada(
    simbolo: str,
    precio_entrada: Any = None,
    tamanio: Any = None,
    stop_loss_pct: Any = None,
    take_profit_pct: Any = None,
    riesgo_usdt: Any = None,
    tendencia_txt: Optional[str] = None,
    apalancamiento: Any = None,
    hora: Optional[str] = None,
    # alias
    entry_price: Any = None,
    size: Any = None,
    sl_pct: Any = None,
    tp_pct: Any = None,
    direccion: Optional[str] = None,
    side: Optional[str] = None,
    **_
) -> str:
    precio = precio_entrada if precio_entrada is not None else entry_price
    tam = tamanio if tamanio is not None else size
    sl = stop_loss_pct if stop_loss_pct is not None else sl_pct
    tp = take_profit_pct if take_profit_pct is not None else tp_pct
    dir_txt = _direccion_txt(direccion, side)

    partes = [
        f"🚀 Entrada | {simbolo}",
        f"{'Compra alcista 📈' if 'LONG' in dir_txt else 'Venta bajista 📉'}",
        f"Precio: {_fmt_num(precio,2)}",
    ]
    if tam is not None:
        partes.append(f"Tamaño: {_fmt_qty(tam)}")
    if sl is not None:
        partes.append(f"Stop Loss: {_fmt_pct(sl)}")
    if tp is not None:
        partes.append(f"Take Profit: {_fmt_pct(tp)}")
    if riesgo_usdt is not None:
        partes.append(f"Riesgo: {_fmt_num(riesgo_usdt,2)} USDT")
    if tendencia_txt:
        partes.append(f"Tendencia 1h: {tendencia_txt}")
    partes.append(f"Apalancamiento: {_apalancamiento_str(apalancamiento)}")
    if hora is not None:
        partes.append(f"Hora: {_fmt_hora(hora)}")
    return "\n".join(partes)

def msg_tp_sl_aplicado(
    simbolo: str,
    sl_precio: Any,
    tp_precio: Any,
    riesgo_usdt: Any = None,
    relacion_txt: Optional[str] = None,
    stop_loss_pct: Any = None,
    take_profit_pct: Any = None,
    **_
) -> str:
    lineas = [
        f"🛡️ TP/SL aplicado | {simbolo}",
    ]
    if stop_loss_pct is not None:
        lineas.append(f"Stop Loss: {_fmt_pct(stop_loss_pct)} a {_fmt_num(sl_precio,2)}")
    else:
        lineas.append(f"Stop Loss: {_fmt_num(sl_precio,2)}")
    if take_profit_pct is not None:
        lineas.append(f"Take Profit: {_fmt_pct(take_profit_pct)} a {_fmt_num(tp_precio,2)}")
    else:
        lineas.append(f"Take Profit: {_fmt_num(tp_precio,2)}")
    if relacion_txt:
        lineas.append(f"Relación: {relacion_txt}")
    if riesgo_usdt is not None:
        lineas.append(f"Riesgo: {_fmt_num(riesgo_usdt,2)} USDT")
    return "\n".join(lineas)

# Alias con firma explícita (no usar *args para que el runner lo detecte)
def msg_tplsl_aplicado(
    simbolo: str,
    sl_precio: Any,
    tp_precio: Any,
    riesgo_usdt: Any = None,
    relacion_txt: Optional[str] = None,
    stop_loss_pct: Any = None,
    take_profit_pct: Any = None,
    **kw
) -> str:
    return msg_tp_sl_aplicado(
        simbolo=simbolo,
        sl_precio=sl_precio,
        tp_precio=tp_precio,
        riesgo_usdt=riesgo_usdt,
        relacion_txt=relacion_txt,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        **kw
    )

def msg_heartbeat_detallado(
    hora_utc: str,
    total_ordenes_24h: int,
    bloqueados: Any,
    operando: Any,
    disponibles: Any,
    capital_total: Any,
    **_
) -> str:
    partes = [
        "🔄 HEARTBEAT – 30 min",
        f"Capital total: {_fmt_num(capital_total,2)} USDT",
        f"Hora: {_fmt_hora(hora_utc)}",
        "",
        "Estado de los pares:",
        "",
        _bloque_lista_pos(operando, "📈 Operando (posición abierta)"),
        "",
        _bloque_lista_pos(disponibles, "✅ Disponibles (sin entrada actual)"),
        "",
        _bloque_lista_pos(bloqueados, "⛔ Bloqueados"),
        "",
        f"Total de órdenes ejecutadas en 24h: {total_ordenes_24h}",
    ]
    return "\n".join(partes)

def msg_trailing_move(
    simbolo: str,
    timeframe_txt: str = "15 minutos",
    buffer_pct: Any = 0.15,
    nuevo_sl: Any = None,
    **_
) -> str:
    lineas = [
        f"🔧 Trailing seguimiento | {simbolo}",
        f"Pivote: {timeframe_txt}",
        f"Buffer: {_fmt_pct(buffer_pct)}",
    ]
    if nuevo_sl is not None:
        lineas.append(f"Stop Loss movido a: {_fmt_num(nuevo_sl,2)}")
    return "\n".join(lineas)

def msg_cierre(
    simbolo: str,
    direccion: Optional[str] = None,
    entrada: Any = None,
    salida: Any = None,
    resultado_pct: Any = None,
    pnl_usdt: Any = None,
    duracion_min: Optional[int] = None,
    impacto_pct: Any = None,
    motivo: str = "Stop Loss",
    side: Optional[str] = None,
    **_
) -> str:
    dir_txt = _direccion_txt(direccion, side)
    lineas = [
        "📉 Operación CERRADA",
        f"Símbolo: {simbolo}",
        f"Dirección: {dir_txt}",
    ]
    if entrada is not None:
        lineas.append(f"Entrada: {_fmt_num(entrada,2)}")
    if salida is not None:
        lineas.append(f"Salida: {_fmt_num(salida,2)}")
    if resultado_pct is not None and pnl_usdt is not None:
        lineas.append(f"Resultado: {_fmt_pct(resultado_pct)} ({_fmt_num(pnl_usdt,2)} USDT neto)")
    elif pnl_usdt is not None:
        lineas.append(f"Resultado: {_fmt_num(pnl_usdt,2)} USDT neto")
    if duracion_min is not None:
        lineas.append(f"Duración: {duracion_min} minutos")
    if impacto_pct is not None:
        lineas.append(f"Impacto: {_fmt_pct(impacto_pct)} del capital")
    if motivo:
        lineas.append(f"Motivo de cierre: {motivo}")
    return "\n".join(lineas)

def msg_posicion_manual_detectada(
    simbolo: str,
    direccion: Optional[str] = None,
    entrada: Any = None,
    sltp_ok: Optional[bool] = True,
    side: Optional[str] = None,
    **_
) -> str:
    dir_txt = _direccion_txt(direccion, side)
    lineas = [
        "📎 Posición manual detectada",
        f"Símbolo: {simbolo}",
        f"Dirección: {dir_txt}",
    ]
    if entrada is not None:
        lineas.append(f"Entrada: {_fmt_num(entrada,2)}")
    lineas.append("SL/TP: OK" if sltp_ok else "SL/TP: PENDIENTE")
    return "\n".join(lineas)

def msg_parcial(
    simbolo: str,
    direccion: Optional[str] = None,
    fraccion: Any = None,
    precio: Any = None,
    qty_restante: Any = None,
    pnl_realizado: Any = None,
    gatillo_txt: Optional[str] = None,
    side: Optional[str] = None,
    at_R: Any = None,
    **_
) -> str:
    dir_txt = _direccion_txt(direccion, side).split()[-1]  # LONG/SHORT
    if gatillo_txt is None and at_R is not None:
        gatillo_txt = f"{at_R}R"
    lineas = [
        "✅ Parcial ejecutado",
        f"Símbolo: {simbolo}",
        f"Dirección: {dir_txt}",
    ]
    if fraccion is not None:
        # aceptar 0.5 o 50%
        try:
            f = float(str(fraccion).replace('%',''))
            f_val = f if f > 1 else f*100
            lineas.append(f"Fracción: {f_val:.0f}%")
        except Exception:
            lineas.append(f"Fracción: {fraccion}")
    if precio is not None:
        lineas.append(f"Precio: {_fmt_num(precio,2)}")
    if qty_restante is not None:
        lineas.append(f"Qty restante: {_fmt_qty(qty_restante)}")
    if pnl_realizado is not None:
        lineas.append(f"PnL realizado: {_fmt_num(pnl_realizado,2)} USDT")
    if gatillo_txt:
        lineas.append(f"Gatillo: {gatillo_txt}")
    return "\n".join(lineas)

# === ⬇⬇⬇ APPEND START: Compat & Mensajes 1:1 (no borra nada) ⬇⬇⬇ ===
# Estas funciones se agregan al final de formatos.py.
# No eliminan ni modifican las funciones existentes; solo suman wrappers compatibles
# y formateadores con exactamente el estilo de mensajes que pidió el usuario.

def _pct(x):
    try:
        if x is None: return None
        return float(x)
    except Exception:
        try:
            # admite "1%" o "1.0%"
            s = str(x).replace('%','').strip()
            return float(s)
        except Exception:
            return None

def _num(x):
    try:
        return float(x)
    except Exception:
        try:
            # admite "x10" => 10
            s = str(x).lower().strip().replace('x','')
            return float(s)
        except Exception:
            return None

def _fmt_pct(p):
    if p is None: return "—"
    return f"{p:.2f}%"

def _fmt_money(u):
    if u is None: return "—"
    # miles con separador ',' estilo 111,452.00
    return f"{u:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def _fmt_qty(q):
    if q is None: return "—"
    # quitar ceros sobrantes
    s = f"{q:.8f}".rstrip('0').rstrip('.')
    return s

def _fmt_hora(h):
    # acepta "07:30" o "07:30 UTC" o (test)
    s = str(h).strip()
    if "UTC" in s or "test" in s: 
        return s
    return f"{s} UTC"

def _bool_to_ok(b):
    return "OK" if bool(b) else "—"

def msg_entrada(simbolo, direccion_txt, precio_entrada, tamanio, stop_loss_pct=None, take_profit_pct=None, riesgo_usdt=None, tendencia_1h=None, apalancamiento=None, hora=None):
    """🚀 Entrada | {simbolo} … estilo: Compra alcista, etc."""
    p = _num(precio_entrada)
    t = _num(tamanio)
    sl = _pct(stop_loss_pct)
    tp = _pct(take_profit_pct)
    r  = _num(riesgo_usdt)
    lev = _num(apalancamiento)
    partes = [
        f"Fabi bot BiBIT:",
        f"🚀 Entrada | {simbolo}",
        f"{direccion_txt} 📈",
        f"Precio: {_fmt_money(p)}",
        f"Tamaño: {_fmt_qty(t)}",
    ]
    if sl is not None: partes.append(f"Stop Loss: {_fmt_pct(sl)}")
    if tp is not None: partes.append(f"Take Profit: {_fmt_pct(tp)}")
    if r  is not None: partes.append(f"Riesgo: {int(r) if r.is_integer() else r} USDT")
    if tendencia_1h:   partes.append(f"Tendencia 1h: {tendencia_1h}")
    if lev is not None: partes.append(f"Apalancamiento: x{int(lev) if lev.is_integer() else lev}")
    if hora is not None: partes.append(f"Hora: {_fmt_hora(hora)}")
    return "\n".join(partes)

def msg_tp_sl_aplicado(simbolo, stop_loss_pct, take_profit_pct, sl_precio, tp_precio, relacion_txt, riesgo_usdt):
    """🛡️ TP/SL aplicado | {simbolo} … exacto al formato solicitado"""
    slp = _pct(stop_loss_pct)
    tpp = _pct(take_profit_pct)
    slv = _num(sl_precio)
    tpv = _num(tp_precio)
    r   = _num(riesgo_usdt)
    return "\n".join([
        "Fabi bot BiBIT:",
        f"🛡️ TP/SL aplicado | {simbolo}",
        f"Stop Loss: {_fmt_pct(slp)} a {_fmt_money(slv)}",
        f"Take Profit: {_fmt_pct(tpp)} a {_fmt_money(tpv)}",
        f"Relación: {relacion_txt}",
        f"Riesgo: {int(r) if r and r.is_integer() else (int(r) if r is not None else '—')} USDT",
    ])

# Alias flexible para el runner que te daba error con msg_tplsl_aplicado
def msg_tplsl_aplicado(*args, **kwargs):
    return msg_tp_sl_aplicado(*args, **kwargs)

def _formatea_condiciones(cond):
    # cond: dict con flags y valores
    if not isinstance(cond, dict):
        return ""
    lines = []
    def yesno(b): return "✅" if b else "❌"
    if "bb_break" in cond:
        lines.append(f"  {yesno(cond['bb_break'])} Cierre por encima de la banda superior")
    if "vol_ok" in cond:
        v = cond.get("vol_val"); req = cond.get("vol_req")
        if v is not None and req is not None:
            lines.append(f"  {yesno(cond['vol_ok'])} Volumen suficiente ({v:.2f} de {req:.2f} requerido)")
    if "ancho_ok" in cond:
        v = cond.get("ancho_val"); req = cond.get("ancho_req")
        if v is not None and req is not None:
            lines.append(f"  {yesno(cond['ancho_ok'])} Ancho de bandas suficiente ({v:.2f}% de {req:.2f}% requerido)")
    return "\n".join(lines)

def msg_heartbeat_detallado(hora_utc, operando, disponibles, bloqueados, capital_total, total_ordenes_24h):
    """🔄 HEARTBEAT – 30 min … con bloques Operando/Disponibles/Bloqueados como en tus ejemplos"""
    cap = _num(capital_total)
    lines = [
        "Fabi bot BiBIT:",
        "🔄 HEARTBEAT – 30 min",
        f"Capital total: {_fmt_money(cap)} USDT",
        f"Hora: {_fmt_hora(hora_utc)}",
        "",
        "Estado de los pares:",
        "",
        "📈 Operando (posición abierta)",
    ]
    # operando: lista de dicts
    for it in (operando or []):
        simb = it.get("simbolo") or it.get("symbol") or "—"
        ent  = it.get("entradas")
        ok   = it.get("posicion_abierta", True)
        dirx = it.get("direccion") or it.get("direccion_txt") or "—"
        entrada = _num(it.get("entrada") or it.get("precio_entrada"))
        slp = _pct(it.get("sl_pct"))
        tpp = _pct(it.get("tp_pct"))
        lines += [
            f"- {simb} | Entradas: {ent} | Posición: {'✅' if ok else '❌'}",
            f"  Dirección: {dirx}",
            f"  Entrada: {_fmt_money(entrada)} USDT",
            f"  Stop Loss: {_fmt_pct(slp)} | Take Profit: {_fmt_pct(tpp)}",
            "  Condiciones al entrar:"
        ]
        cond = it.get("condiciones", {}) or {}
        cond_txt = _formatea_condiciones(cond)
        if cond_txt:
            lines.append(cond_txt)
        else:
            lines.append("  —")
        lines.append("")
    # Disponibles
    lines.append("✅ Disponibles (sin entrada actual)")
    if isinstance(disponibles, str):
        lines.append(disponibles)
    else:
        for it in (disponibles or []):
            lines.append(f"- {it}")
    lines.append("")
    # Bloqueados
    lines.append("⛔ Bloqueados")
    if isinstance(bloqueados, str):
        lines.append(bloqueados)
    else:
        for it in (bloqueados or []):
            lines.append(f"- {it}")
    lines += ["", f"Total de órdenes ejecutadas en 24h: {int(total_ordenes_24h)}"]
    return "\n".join(lines)

def msg_trailing_seguimiento(simbolo, pivote_min, buffer_pct, nuevo_sl):
    """🔧 Trailing seguimiento | {simbolo} …"""
    bf = _pct(buffer_pct)
    sl = _num(nuevo_sl)
    return "\n".join([
        "Fabi bot BiBIT:",
        f"🔧 Trailing seguimiento | {simbolo}",
        f"Pivote: {int(_num(pivote_min))} minutos",
        f"Buffer: {_fmt_pct(bf)}",
        f"Stop Loss movido a: {_fmt_money(sl)}",
    ])

# Alias flexible por si el llamador usa otro nombre
def msg_trailing_move(*args, **kwargs):
    return msg_trailing_seguimiento(*args, **kwargs)

def msg_tsl_be(simbolo, nuevo_sl):
    sl = _num(nuevo_sl)
    return "\n".join([
        "Fabi bot BiBIT:",
        "🔒 TSL movido a BE",
        f"Símbolo: {simbolo}",
        f"Nuevo SL: {_fmt_money(sl)} (BE)",
    ])

def msg_posicion_manual_detectada(simbolo, direccion_txt, entrada, sl_tp_ok=True):
    ent = _num(entrada)
    return "\n".join([
        "Fabi bot BiBIT:",
        "📎 Posición manual detectada",
        f"Símbolo: {simbolo}",
        f"Dirección: {direccion_txt}",
        f"Entrada: {_fmt_money(ent)}",
        f"SL/TP: {_bool_to_ok(sl_tp_ok)}",
    ])

def msg_parcial_ejecutado(simbolo, direccion_txt, fraccion, pnl_realizado_usdt, qty_restante, precio_ejecucion, nivel_r):
    """✅ Parcial ejecutado | BTCUSDT … exactamente como en tu ejemplo largo"""
    frac_pct = _pct(fraccion*100 if fraccion and fraccion<=1 else fraccion)  # admite 0.5 o 50
    pnl = _num(pnl_realizado_usdt)
    qty = _num(qty_restante)
    px  = _num(precio_ejecucion)
    # Nivel R puede venir como 0.5 / "0.5R"
    try:
        rnum = float(str(nivel_r).replace('R','').strip())
    except:
        rnum = None
    nivel_txt = f"{rnum:.2f}R" if rnum is not None else str(nivel_r)
    return "\n".join([
        "Fabi bot BiBIT:",
        f"✅ Parcial ejecutado | {simbolo}",
        f"Dirección: {direccion_txt}",
        f"Fracción: {frac_pct/100:.2f}" if frac_pct and frac_pct>1 else f"Fracción: {frac_pct:.2f}" if frac_pct is not None else "Fracción: —",
        f"Ganancia realizada: {_fmt_money(pnl)} USDT 💰",
        f"Cantidad restante: {_fmt_qty(qty)}",
        f"Precio ejecución: {_fmt_money(px)}",
        f"Nivel alcanzado: {nivel_txt} 🎯",
    ])

def msg_cierre(simbolo, direccion_txt, precio_entrada, precio_salida, resultado_pct, pnl_usdt, duracion_min, impacto_pct, motivo):
    pe = _num(precio_entrada)
    ps = _num(precio_salida)
    rp = _pct(resultado_pct)
    pn = _num(pnl_usdt)
    im = _pct(impacto_pct)
    return "\n".join([
        "Fabi bot BiBIT:",
        "📉 Operación CERRADA",
        f"Símbolo: {simbolo}",
        f"Dirección: {direccion_txt}",
        f"Entrada: {_fmt_money(pe)}",
        f"Salida: {_fmt_money(ps)}",
        f"Resultado: {_fmt_pct(rp)} ({_fmt_money(pn)} USDT neto)",
        f"Duración: {int(_num(duracion_min))} minutos",
        f"Impacto: {_fmt_pct(im)} del capital",
        f"Motivo de cierre: {motivo}",
    ])
# === ⬆⬆⬆  APPEND END  ⬆⬆⬆ ===
