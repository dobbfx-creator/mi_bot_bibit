NON-DESTRUCTIVE PATCH (v1)
==========================
Objetivo: agregar *llamadas* a notificaciones de parcial y cierre por trailing **sin tocar ni reemplazar** tus archivos `mensajeria/formatos.py` y `mensajeria/eventos.py`.

TUS ARCHIVOS ACTUALES YA ESTÁN BIEN
-----------------------------------
- `mensajeria/eventos.py` define `_Notifier` con:
    - `parcial(...)`
    - `trailing_close(...)`
- `mensajeria/formatos.py` ya trae:
    - `msg_parcial_ejecutado(...)`
    - `msg_cierre_trailing(...)`
    - y variantes `*_fmt`

Por lo tanto, **NO reemplaces** esos archivos. Solo hay que "enganchar" las llamadas desde `core.py`.

PASO 1 — Import en tu core
---------------------------
En `core/core.py`, cerca del resto de imports (una sola vez):
    from mensajeria.eventos import notifier as EV

PASO 2 — Aviso de PARCIAL ejecutada
-----------------------------------
En el bloque donde YA detectás y / o ejecutás la parcial (cuando se cumple `partials.enabled` y llega a `at_R`), agregá inmediatamente después de realizar el update de cantidades/PnL:

    try:
        EV.parcial(
            CFG,
            simbolo=symbol,
            is_long=(side in ('LONG','BUY','COMPRA',True)),
            fraction=float(CFG.get('partials',{}).get('fraction', 0.5)),
            pnl_usdt=float(pnl_realizado_usdt),
            qty_restante=float(qty_restante),
            precio_ejecucion=float(exec_price),
            at_r=float(CFG.get('partials',{}).get('at_R', 0.5)),
        )
    except Exception as e:
        logger.warning(f"notifier.parcial fallo: {e}")

Variables sugeridas:
- `symbol`: símbolo actual (p.ej. 'BTCUSDT')
- `side`: texto bool o str de dirección
- `pnl_realizado_usdt`: PnL realizado por la parcial
- `qty_restante`: cantidad que quedó abierta
- `exec_price`: precio al que se ejecutó la parcial

PASO 3 — Aviso de CIERRE por TRAILING
-------------------------------------
En el bloque donde **cerrás** por trailing (cuando toca el stop dinámico / BE), agregá:

    try:
        EV.trailing_close(
            CFG,
            simbolo=symbol,
            is_long=(side in ('LONG','BUY','COMPRA',True)),
            pnl_usdt=float(pnl_cerrado_usdt),
            precio_cierre=float(exit_price),
            distancia_pct=float(distancia_pct) if 'distancia_pct' in locals() else None,
        )
    except Exception as e:
        logger.warning(f"notifier.trailing_close fallo: {e}")

Variables sugeridas:
- `exit_price`: precio de salida por trailing
- `pnl_cerrado_usdt`: PnL total realizado al cierre
- `distancia_pct` (opcional): distancia del SL al precio al momento del cierre

PASO 4 — Smoke test de mensajería (opcional)
--------------------------------------------
Para verificar el envío a Telegram sin esperar señales de mercado:
    cd C:\backtest_bibit_1to1\tests
    python smoke_notify.py

Deberías recibir **dos** mensajes: "Parcial ejecutada (SMOKE)" y "Cierre por Trailing (SMOKE)".

Notas de robustez
-----------------
- `eventos._send` ya intenta `mensajeria.telegram.enviar_mensaje_raw` si existe, y si no, **envía directo a la API** de Telegram usando `bot_token` y `chat_id` del `settings.json`.
- Nada de esto rompe el core si falla el envío: loguea y sigue.
