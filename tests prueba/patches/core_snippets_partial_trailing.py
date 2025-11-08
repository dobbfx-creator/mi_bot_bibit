# -- patches/core_snippets_partial_trailing.py (SOLO REFERENCIA) --
# IMPORT único (arriba del archivo core.py, junto a otros imports):
from mensajeria.eventos import notifier as EV

# Dentro de tu lógica donde se ejecuta la PARCIAL (post-ejecución):
try:
    EV.parcial(
        CFG,
        simbolo=symbol,
        is_long=(side in ('LONG','BUY','COMPRA', True)),
        fraction=float(CFG.get('partials',{}).get('fraction', 0.5)),
        pnl_usdt=float(pnl_realizado_usdt),
        qty_restante=float(qty_restante),
        precio_ejecucion=float(exec_price),
        at_r=float(CFG.get('partials',{}).get('at_R', 0.5)),
    )
except Exception as e:
    logger.warning(f"notifier.parcial fallo: {e}")

# Dentro de tu lógica donde cierras por TRAILING (en el momento del cierre):
try:
    EV.trailing_close(
        CFG,
        simbolo=symbol,
        is_long=(side in ('LONG','BUY','COMPRA', True)),
        pnl_usdt=float(pnl_cerrado_usdt),
        precio_cierre=float(exit_price),
        distancia_pct=float(distancia_pct) if 'distancia_pct' in locals() else None,
    )
except Exception as e:
    logger.warning(f"notifier.trailing_close fallo: {e}")
