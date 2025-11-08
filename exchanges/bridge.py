# exchanges/bridge.py
from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass
class BridgeResult:
    ok: bool
    reason: str = ""
    filled_qty: float | None = None
    avg_price: float | None = None

class ExchangeBridge:
    """
    Puente mínimo y seguro. Por defecto DRY_RUN (no manda órdenes reales).
    Cuando definas claves y quieras testnet real, switcheás EXCHANGE_MODE=BYBIT_TESTNET.
    """
    def __init__(self):
        self.mode = os.getenv("EXCHANGE_MODE", "DRY_RUN").upper()
        # Lectura opcional de credenciales
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")

    def close_partial_market(self, symbol: str, side_long: bool, fraction: float,
                             qty_total: float, reduce_only: bool = True) -> BridgeResult:
        """
        Cierra 'fraction' de la posición por mercado.
        - DRY_RUN: simula y devuelve ok=True.
        - BYBIT_TESTNET: acá luego enchufamos la llamada real (próximo paso).
        """
        try:
            if not (0 < fraction < 1):
                return BridgeResult(False, "fraction fuera de rango (0..1)")
            qty_close = round(qty_total * fraction, 6)
            if qty_close <= 0:
                return BridgeResult(False, "qty_close <= 0")

            if self.mode == "DRY_RUN":
                # Simulación segura: no toca exchange
                print(f"[DRY_RUN] close_partial_market {symbol} "
                      f"{'SELL' if side_long else 'BUY'} qty={qty_close} reduce_only={reduce_only}")
                return BridgeResult(True, filled_qty=qty_close, avg_price=None)

            elif self.mode == "BYBIT_TESTNET":
                # TODO: implementar llamada real Bybit testnet (próximo micro-paso).
                # Por ahora devolvemos simulación marcada:
                print(f"[SIM-BYBIT] (pendiente impl) cerrar parcial {symbol} qty={qty_close}")
                return BridgeResult(True, filled_qty=qty_close, avg_price=None)

            else:
                return BridgeResult(False, f"Modo no soportado: {self.mode}")

        except Exception as e:
            return BridgeResult(False, f"Exception: {e}")
