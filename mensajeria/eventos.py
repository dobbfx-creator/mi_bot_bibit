
# -*- coding: utf-8 -*-
"""
mensajeria/eventos.py
---------------------
Notifier liviano y SIN dependencias del core (evita import circular).
Usa mensajeria.telegram.enviar_mensaje_raw si está disponible;
si no, cae a HTTP directo contra el API de Telegram.

Expone: `notifier.parcial(...)` y `notifier.trailing_close(...)`
que son invocados por core.py para avisos automáticos.
"""

from typing import Optional
import urllib.request as _ulreq
import urllib.parse as _ulparse

# ---- HTTP fallback a Telegram ------------------------------------------------
def _http_send(cfg: dict, texto: str) -> bool:
    try:
        tgc = (cfg or {}).get("telegram", {}) if isinstance(cfg, dict) else {}
        token = str(tgc.get("bot_token", "")).strip()
        chat  = str(tgc.get("chat_id", "")).strip()
        if not token or not chat:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = _ulparse.urlencode({"chat_id": chat, "text": str(texto)}).encode("utf-8")
        req  = _ulreq.Request(url, data=data, method="POST")
        with _ulreq.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception:
        return False

# ---- Envío principal (preferir módulo telegram si existe) -------------------
def _send(cfg: dict, texto: str) -> bool:
    try:
        from . import telegram as _tg
    except Exception:
        _tg = None

    # Preferir enviar_mensaje_raw si existe
    if _tg is not None and hasattr(_tg, "enviar_mensaje_raw"):
        try:
            r = _tg.enviar_mensaje_raw(cfg, texto)
            return bool(r) if r is not None else True
        except Exception:
            pass
    # Fallback a enviar_mensaje (si existe)
    if _tg is not None and hasattr(_tg, "enviar_mensaje"):
        try:
            _tg.enviar_mensaje(cfg, texto)
            return True
        except Exception:
            pass
    # Fallback HTTP directo
    return _http_send(cfg, texto)

# ---- Formatos (no rompe si no existen helpers en formatos.py) ---------------
def _mk_msg_parcial(simbolo: str, is_long: bool, fraction: float,
                    pnl_usdt: float, qty_restante: float, precio_ejecucion: float,
                    at_r: Optional[float]) -> str:
    dir_txt = "COMPRA (LONG)" if is_long else "VENTA (SHORT)"
    frac_pct = max(0.0, min(1.0, float(fraction))) * 100.0
    extra = f"\nGatillo: {at_r}R" if (at_r is not None) else ""
    return (
        f"➗ Parcial ejecutada\n"
        f"Símbolo: {simbolo}\n"
        f"Dirección: {dir_txt}\n"
        f"Fracción: {frac_pct:.0f}%\n"
        f"Precio: {precio_ejecucion:,.2f}\n"
        f"Realizado: {pnl_usdt:.2f} USDT\n"
        f"Qty restante: {qty_restante:g}{extra}"
    )

def _mk_msg_trailing_close(simbolo: str, is_long: bool, pnl_usdt: float,
                           precio_cierre: float, distancia_pct: Optional[float]) -> str:
    dir_txt = "COMPRA (LONG)" if is_long else "VENTA (SHORT)"
    dist = f"\nDistancia trailing: {distancia_pct:.2f}%" if (distancia_pct is not None) else ""
    return (
        f"🏁 Cierre por Trailing\n"
        f"Símbolo: {simbolo}\n"
        f"Dirección: {dir_txt}\n"
        f"Cierre: {precio_cierre:,.2f}\n"
        f"Realizado: {pnl_usdt:.2f} USDT{dist}"
    )

# ---- API pública ------------------------------------------------------------
class _Notifier:
    def parcial(self, cfg: dict, *, simbolo: str, is_long: bool, fraction: float,
                pnl_usdt: float, qty_restante: float, precio_ejecucion: float,
                at_r: Optional[float] = None):
        """
        Enviar mensaje de PARCIAL ejecutada.
        """
        try:
            # Si existen helpers en formatos.py, úsalos
            try:
                from .formatos import msg_parcial_ejecutado as _tpl
                texto = _tpl(simbolo, is_long, fraction, pnl_usdt, qty_restante, precio_ejecucion, at_r)
            except Exception:
                texto = _mk_msg_parcial(simbolo, is_long, fraction, pnl_usdt, qty_restante, precio_ejecucion, at_r)
            _send(cfg, texto)
        except Exception:
            # Nunca romper el bot por un aviso
            pass

    def trailing_close(self, cfg: dict, *, simbolo: str, is_long: bool, pnl_usdt: float,
                       precio_cierre: float, distancia_pct: Optional[float] = None):
        """
        Enviar mensaje de CIERRE por trailing.
        """
        try:
            # Si existen helpers en formatos.py, úsalos
            try:
                from .formatos import msg_cierre_trailing as _tpl
                texto = _tpl(simbolo, is_long, pnl_usdt, precio_cierre, distancia_pct)
            except Exception:
                texto = _mk_msg_trailing_close(simbolo, is_long, pnl_usdt, precio_cierre, distancia_pct)
            _send(cfg, texto)
        except Exception:
            pass

notifier = _Notifier()
