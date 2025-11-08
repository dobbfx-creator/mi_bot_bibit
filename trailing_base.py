# trailing_base.py
# Lógica de Trailing y Breakeven robusto (versión estable Fabián)

def preparar_posicion(side, entry, stop):
    """
    Crea el estado inicial del trailing.
    side: "long" o "short"
    entry: precio de entrada
    stop: stop inicial
    """
    return {
        "side": side.lower(),
        "entry": float(entry),
        "stop": float(stop),
        "peak": float(entry),
        "be_moved": False     # indica si ya movimos el stop a BE
    }


def actualizar_trailing(state, price, rr_trigger=1.0, rr_distance=0.5):
    """
    state: dict del trailing (ver preparar_posicion)
    price: último precio
    rr_trigger: R donde pasamos a breakeven (ej: 1.0R)
    rr_distance: distancia del trailing (ej: 0.5R)
    """

    entry = state["entry"]
    stop = state["stop"]
    side = state["side"]

    # riesgo inicial
    risk = abs(entry - stop)
    if risk <= 0:
        return state["stop"], state  # no hay trailing posible

    # calcular RR actual
    if side == "long":
        rr = (price - entry) / risk
    else:
        rr = (entry - price) / risk

    # 1) Mover a BE si llegó al RR de activación
    if rr >= rr_trigger and not state["be_moved"]:
        new_stop = entry
        if (side == "long" and new_stop > stop) or (side == "short" and new_stop < stop):
            stop = new_stop
        state["be_moved"] = True
        state["stop"] = stop
        return stop, state

    # Si todavía no movimos a BE → no hacemos trailing todavía
    if not state["be_moved"]:
        return stop, state

    # 2) Actualizar peak / trough
    if side == "long":
        state["peak"] = max(state["peak"], price)
        new_stop = state["peak"] - (rr_distance * risk)

        # No retroceder el SL, solo acercarlo
        if new_stop > stop:
            stop = new_stop

    else:  # short
        state["peak"] = min(state["peak"], price)
        new_stop = state["peak"] + (rr_distance * risk)

        # No retroceder el SL, solo acercarlo
        if new_stop < stop:
            stop = new_stop

    state["stop"] = stop
    return stop, state
