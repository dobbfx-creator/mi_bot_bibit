# -*- coding: utf-8 -*-
"""
Exchange simulado para testear parciales y trailing sin tocar Bybit.
"""
class SimExchange:
    def __init__(self, qty_inicial):
        self.qty = float(qty_inicial)  # posición abierta
        self.orders = []
        self.trailing_sl = None
        self.min_qty = 0.001
        self.qty_step = 0.001
        self.tick = 0.01

    # reduce-only: cerrar en lado contrario
    def place_market(self, symbol, side_txt, qty, reduce_only=True):
        q = float(qty)
        if q < self.min_qty:
            return False, {"error": "min_qty", "min": self.min_qty}
        # ajustar al step
        q = max(self.min_qty, round(q / self.qty_step) * self.qty_step)
        q = min(q, self.qty)
        if q <= 0:
            return False, {"error": "qty_zero_after_step"}
        self.qty -= q
        self.orders.append({"symbol": symbol, "side": side_txt, "qty": q, "reduce_only": reduce_only})
        return True, {"closed": q}

    def fetch_position_for_symbol(self, symbol):
        return {"qty": self.qty}

    def round_qty_to_step(self, symbol, qty):
        return max(self.min_qty, round(float(qty) / self.qty_step) * self.qty_step)

    def set_trailing_stop(self, symbol, new_sl):
        # redondeo al tick
        new_sl = round(float(new_sl) / self.tick) * self.tick
        if self.trailing_sl is not None and new_sl <= self.trailing_sl:
            return False, {"note": "not_modified", "sl": self.trailing_sl}
        self.trailing_sl = new_sl
        return True, {"sl": self.trailing_sl}
