# mensajeria/notifier.py
from typing import Optional
from mensajeria.telegram import enviar_mensaje  # la función simple que ya tenés
from mensajeria.formatos import msg_parcial_ejecutado, msg_cierre_trailing

def _on(cfg: dict, key: str, default: bool = True) -> bool:
    try:
        notif = cfg.get("notify", {})
        return bool(notif.get(key, default))
    except Exception:
        return default

def safe_send(cfg: dict, texto: str) -> None:
    try:
        enviar_mensaje(cfg, texto)
    except Exception:
        # blindado: jamás se propaga error de Telegram
        pass

def parcial(cfg: dict, simbolo: str, is_long: bool, fraction: float,
            pnl_usdt: float, qty_restante: float, precio_ejecucion: float, at_r: float):
    if not _on(cfg, "partials", True):
        return
    try:
        txt = msg_parcial_ejecutado(
            simbolo=simbolo,
            side_long=is_long,
            fraction=float(fraction),
            pnl_usdt=float(pnl_usdt),
            qty_restante=float(qty_restante),
            precio_ejecucion=float(precio_ejecucion),
            at_r=float(at_r),
        )
        safe_send(cfg, txt)
    except Exception:
        # nunca detener el core por formato/clave faltante
        pass

def trailing_close(cfg: dict, simbolo: str, is_long: bool,
                   pnl_usdt: float, precio_cierre: float, distancia_pct: Optional[float] = None):
    if not _on(cfg, "trailing", True):
        return
    try:
        txt = msg_cierre_trailing(
            simbolo=simbolo,
            side_long=is_long,
            pnl_usdt=float(pnl_usdt),
            precio_cierre=float(precio_cierre),
            distancia_pct=(None if distancia_pct is None else float(distancia_pct)),
        )
        safe_send(cfg, txt)
    except Exception:
        pass
