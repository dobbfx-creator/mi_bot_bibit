# -*- coding: utf-8 -*-
from typing import Any, Dict, Tuple, Callable

def _as_dict(x):
    try:
        return dict(x)
    except Exception:
        return {}

def _pick_partials_view(cfg: Any):
    try:
        p = (cfg or {}).get("partials", {})
        return dict(p) if isinstance(p, dict) else {}
    except Exception:
        return {}

def _resolve_partials_cfg(cfg: Any) -> Tuple[float, float]:
    """
    Devuelve (at_R, fraction) resolviendo:
      - NUEVO: trigger_mode='R_multiple' + trigger_R; qty_mode='percent_of_open' + qty_value
      - LEGADO: at_R + fraction
      - Defaults si faltan: at_R=1.0, fraction=0.5
    """
    parts = _pick_partials_view(cfg) or {}

    trigger_mode = str(parts.get("trigger_mode") or "").strip().lower()
    qty_mode     = str(parts.get("qty_mode") or "").strip().lower()

    at_R = None
    fraction = None

    if trigger_mode == "r_multiple":
        try:
            at_R = float(parts.get("trigger_R"))
        except Exception:
            at_R = None

    if qty_mode == "percent_of_open":
        try:
            fraction = float(parts.get("qty_value")) / 100.0
        except Exception:
            fraction = None

    if at_R is None:
        try:
            at_R = float(parts.get("at_R"))
        except Exception:
            at_R = 0.0

    if fraction is None:
        try:
            fraction = float(parts.get("fraction"))
        except Exception:
            fraction = 0.0

    if at_R <= 0:
        at_R = 1.0
    if fraction <= 0:
        fraction = 0.5
    if fraction > 1.0:
        fraction = 1.0
    return at_R, fraction

def should_execute_partial(reg: Dict, precio_actual: float, CFG: Any) -> Tuple[bool, Dict]:
    """
    Calcula r_now y decide si disparar según (at_R, fraction).
    Espera en reg:
      - 'direccion': 'COMPRA' o 'VENTA'
      - 'entrada_precio': float
      - 'sl_pct': % respecto a entrada
      - 'qty': cantidad abierta
    """
    at_R, fraction = _resolve_partials_cfg(CFG)
    side_long = str(reg.get("direccion", "")).upper().startswith("COMPRA")
    entrada = float(reg.get("entrada_precio") or 0.0)
    sl_pct  = float(reg.get("sl_pct") or 0.0) / 100.0
    qty_actual = float(reg.get("qty") or 0.0)

    # riesgo en precio desde entrada a SL
    risk = entrada * sl_pct if entrada and sl_pct else 0.0
    r_now = 0.0
    if entrada and risk:
        if side_long:
            r_now = (float(precio_actual) - entrada) / risk
        else:
            r_now = (entrada - float(precio_actual)) / risk

    ok = r_now >= float(at_R)
    info = {
        "r_now": float(r_now),
        "fraction": float(fraction),
        "entrada": float(entrada),
        "side_long": bool(side_long),
        "qty_actual": float(qty_actual),
        "at_R": float(at_R)
    }
    return ok, info

def _idempotence_mark_done(reg: Dict):
    reg["partial_done"] = True

def ejecutar_parcial_si_corresponde(
    simbolo: str,
    reg: Dict,
    precio_actual: float,
    CFG: Any = None,
    MODO: str = "sim",
    *,
    place_market=None,
    fetch_position_for_symbol=None,
    round_qty_to_step=None,
    notifier=None,
    persist: Callable[[str, Dict], None] = None
) -> bool:
    try:
        ok, info = should_execute_partial(reg, precio_actual, CFG)
        if not ok:
            return False

        fraction   = float(info["fraction"])
        side_long  = bool(info["side_long"])
        qty_actual = float(info["qty_actual"])

        # calcular qty a cerrar con step/min
        def _calc_qty_cerrar(simbolo: str, qty_open: float, fraction: float, round_qty_to_step):
            qty_target = max(0.0, float(qty_open) * float(fraction))
            try:
                if callable(round_qty_to_step):
                    qty_rounded = round_qty_to_step(simbolo, qty_target)
                else:
                    qty_rounded = float(f"{qty_target:.8f}")
            except Exception:
                qty_rounded = float(f"{qty_target:.8f}")
            if qty_rounded <= 0 and qty_target > 0:
                try:
                    qty_rounded = float(f"{qty_target:.8f}")
                    if callable(round_qty_to_step):
                        qty_rounded = round_qty_to_step(simbolo, qty_rounded)
                except Exception:
                    pass
            return max(0.0, qty_rounded), {"target": qty_target, "rounded": qty_rounded}

        qty_cerrar, _qinfo = _calc_qty_cerrar(simbolo, qty_actual, fraction, round_qty_to_step)

        # Ajustar a qty viva del exchange (solo REAL)
        try:
            if (MODO or "").lower() == "real" and callable(fetch_position_for_symbol):
                pos = fetch_position_for_symbol(simbolo)
                if pos:
                    qpos = float(pos.get("qty") or 0.0)
                    if qpos > 0:
                        qty_cerrar = min(qty_cerrar, qpos)
        except Exception:
            pass

        # Ajustar a step de nuevo por si cambió
        try:
            if callable(round_qty_to_step):
                qty_cerrar = round_qty_to_step(simbolo, qty_cerrar)
        except Exception:
            pass

        # Si queda en 0, marcar y explicar SKIPPED
        if qty_cerrar <= 0:
            try:
                import logging; logging.getLogger('bibit').info(
                    "PARCIAL SKIPPED: sym=%s r_now=%.3f (qty_cerrar=0 tras step/min_qty)",
                    simbolo, float(info.get("r_now", 0.0))
                )
            except Exception:
                pass
            _idempotence_mark_done(reg)
            try:
                if callable(persist):
                    persist(simbolo, reg)
            except Exception:
                pass
            return False

        aplicado = True
        if (MODO or "").lower() == "real":
            side_txt = "sell" if side_long else "buy"  # reduce-only => lado contrario
            ok_pm, resp = False, {}
            try:
                # 1) Intento con reduce_only=True
                try:
                    ok_pm, resp = place_market(simbolo, side_txt, qty_cerrar, reduce_only=True)
                except TypeError:
                    ok_pm, resp = place_market(simbolo, side_txt, qty_cerrar)

                if not ok_pm:
                    import logging
                    logging.getLogger('bibit').info(
                        "PARCIAL PLACE FAIL (reduce_only=True): sym=%s side=%s qty=%.8f resp=%s",
                        simbolo, side_txt, float(qty_cerrar), str(resp)
                    )
                    # 2) Reintento sin reduce_only si el motivo lo sugiere
                    motivo = (str(resp) or "").lower()
                    if "reduce" in motivo or "flag" in motivo or "not supported" in motivo:
                        try:
                            ok_pm, resp = place_market(simbolo, side_txt, qty_cerrar, reduce_only=False)
                        except TypeError:
                            ok_pm, resp = place_market(simbolo, side_txt, qty_cerrar)
                        logging.getLogger('bibit').info(
                            "PARCIAL RETRY (sin reduce_only): sym=%s ok=%s resp=%s",
                            simbolo, ok_pm, str(resp)
                        )
            except Exception as e:
                ok_pm, resp = False, {"error": f"exception:{e}"}

            if not ok_pm:
                aplicado = False
        else:
            # SIM: descontar localmente
            reg["qty"] = max(0.0, qty_actual - qty_cerrar)

        if not aplicado:
            try:
                import logging; logging.getLogger('bibit').info(
                    "PARCIAL SKIPPED: sym=%s r_now=%.3f (orden no colocada)",
                    simbolo, float(info.get("r_now", 0.0))
                )
            except Exception:
                pass
            return False

        # ÉXITO
        _idempotence_mark_done(reg)
        try:
            if callable(persist):
                persist(simbolo, reg)
        except Exception:
            pass

        # Notificación + log EXEC
        try:
            import logging; logging.getLogger('bibit').info(
                "PARCIAL EXEC: sym=%s open=%.6f frac=%.2f qty_final=%.6f",
                simbolo, float(info.get("qty_actual", 0.0)), float(info.get("fraction", 0.0)), float(qty_cerrar)
            )
        except Exception:
            pass
        try:
            if notifier:
                at_R_resolved, _ = _resolve_partials_cfg(CFG)
                notifier.parcial(
                    _as_dict(CFG) if CFG is not None else {},
                    simbolo=simbolo,
                    is_long=bool(info.get("side_long")),
                    fraction=float(info.get("fraction")),
                    pnl_usdt=float(reg.get("pnl_realizado") or 0.0),
                    qty_restante=float(reg.get("qty") or 0.0),
                    precio_ejecucion=float(precio_actual or info.get("entrada") or 0.0),
                    at_r=float(at_R_resolved),
                )
        except Exception:
            pass

        return True
    except Exception:
        return False
