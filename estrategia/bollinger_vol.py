# -*- coding: utf-8 -*-
"""
Generador de señal con filtros cableados al JSON (sección 'estrategia').

- Usa SOLO la sección cfg_estrategia que le pasa backtest.py
- Soporta toggles/valores:
    usar_ema200, ema_len
    use_ema200_slope, ema200_slope_min_pct_per_bar
    usar_adx, adx_len, adx_min, use_adx_rising, adx_delta_min
    usar_squeeze, bb_len, bb_mult, bb_width_ma_len, squeeze_mult
    usar_rsi, rsi_len, rsi_long_min, rsi_short_max, use_rsi_guard, rsi_delta_min, rsi_overbought
    use_min_dist_ema200, min_dist_ema200_pct
    use_breakout_retest, breakout_retest_min_atr_mult, confirm_wait_bars
    use_atr, atr_period   (para guards que dependen de ATR)
"""

import math
import numpy as np
import pandas as pd

# =============== Indicadores base ===============

def _ema(s: pd.Series, n: int):
    return s.ewm(span=max(1, int(n)), adjust=False).mean()

def _rsi(close: pd.Series, n: int = 14):
    n = max(2, int(n))
    delta = close.diff()
    up = delta.clip(lower=0.0)
    dn = -delta.clip(upper=0.0)
    ma_up = up.ewm(alpha=1/n, adjust=False).mean()
    ma_dn = dn.ewm(alpha=1/n, adjust=False).mean()
    rs = ma_up / ma_dn.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    n = max(1, int(n))
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    """
    ADX clásico (suavizado simple). Devuelve Series con ADX.
    """
    n = max(2, int(n))
    up = high.diff()
    dn = -low.diff()

    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr = pd.concat([
        (high - low),
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(n, min_periods=n).mean()
    plus_di  = 100 * pd.Series(plus_dm, index=high.index).rolling(n, min_periods=n).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(n, min_periods=n).mean() / atr.replace(0, np.nan)

    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) ) * 100
    adx = dx.rolling(n, min_periods=n).mean()
    return adx.fillna(0), plus_di.fillna(0), minus_di.fillna(0)

def _bb(close: pd.Series, n: int = 20, mult: float = 2.0):
    n = max(2, int(n))
    mult = float(mult)
    ma = close.rolling(n, min_periods=n).mean()
    std = close.rolling(n, min_periods=n).std(ddof=0)
    up = ma + mult*std
    lo = ma - mult*std
    width = (up - lo).abs()
    bbw = (width / ma.replace(0, np.nan)).abs()  # ancho normalizado
    return ma, up, lo, bbw.fillna(0)

# =============== Helpers de condición ===============

def _pct_slope(series: pd.Series):
    """% por barra, aproximado: (x - x[-1]) / x[-1] * 100."""
    return (series - series.shift(1)) / series.shift(1) * 100.0

def _dist_pct(a, b):
    return (a - b) / b * 100.0 if b else 0.0

def _highest(high: pd.Series, n: int):
    return high.rolling(n, min_periods=n).max()

def _lowest(low: pd.Series, n: int):
    return low.rolling(n, min_periods=n).min()

# =============== Señal principal ===============

def _generar_senal_core(rows, _ctx, cfg_estrategia: dict):
    """
    rows: lista de dicts con keys: ts, open, high, low, close, volume, time (UTC)
    cfg_estrategia: dict con TODAS las llaves de 'estrategia' (ya viene saneado por backtest.py)

    Return:
        {} si no hay señal
        {"accion": "BUY"/"SELL", "precio": close_actual} si hay señal
    """
    if not rows or len(rows) < 250:
        return {}

    df = pd.DataFrame(rows)
    # Asegurar columnas
    for c in ("open","high","low","close"):
        if c not in df.columns:
            return {}

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    # === Leer cfg
    E = cfg_estrategia or {}

    # Básicos BB
    bb_len     = int(E.get("bb_len", 20))
    bb_mult    = float(E.get("bb_mult", 2.0))
    bbw_ma_len = int(E.get("bb_width_ma_len", 50))
    squeeze_mult = float(E.get("squeeze_mult", 1.0))
    usar_squeeze = bool(E.get("usar_squeeze", False))

    # EMA200 + pendiente + distancia
    usar_ema200 = bool(E.get("usar_ema200", True))
    ema_len = int(E.get("ema_len", 200))
    use_ema200_slope = bool(E.get("use_ema200_slope", False))
    ema200_slope_min = float(E.get("ema200_slope_min_pct_per_bar", 0.0))
    use_min_dist_ema200 = bool(E.get("use_min_dist_ema200", False))
    min_dist_ema200_pct = float(E.get("min_dist_ema200_pct", 0.0))

    # ADX
    usar_adx = bool(E.get("usar_adx", False))
    adx_len  = int(E.get("adx_len", 14))
    adx_min  = float(E.get("adx_min", 0.0))
    use_adx_rising = bool(E.get("use_adx_rising", False))
    adx_delta_min  = float(E.get("adx_delta_min", 0.0))

    # RSI + guards
    usar_rsi = bool(E.get("usar_rsi", False))
    rsi_len = int(E.get("rsi_len", 14))
    rsi_long_min  = float(E.get("rsi_long_min", 0.0))
    rsi_short_max = float(E.get("rsi_short_max", 100.0))
    use_rsi_guard = bool(E.get("use_rsi_guard", False))
    rsi_delta_min = float(E.get("rsi_delta_min", 0.0))
    rsi_overbought = float(E.get("rsi_overbought", 100.0))

    # Breakout + retest + confirmación
    use_breakout_retest = bool(E.get("use_breakout_retest", False))
    breakout_retest_min_atr_mult = float(E.get("breakout_retest_min_atr_mult", 0.0))
    confirm_wait_bars = int(E.get("confirm_wait_bars", 0))

    # ATR
    use_atr = bool(E.get("use_atr", False))
    atr_period = int(E.get("atr_period", 14))

    # === Cálculos
    ma, bb_up, bb_lo, bbw = _bb(close, bb_len, bb_mult)
    bbw_ma = bbw.rolling(bbw_ma_len, min_periods=bbw_ma_len).mean()

    ema = _ema(close, ema_len) if usar_ema200 or use_ema200_slope or use_min_dist_ema200 else pd.Series(index=close.index, dtype=float)
    ema_slope_pct = _pct_slope(ema) if use_ema200_slope else pd.Series(index=close.index, dtype=float)

    adx, plus_di, minus_di = _adx(high, low, close, adx_len) if usar_adx else (pd.Series([0]*len(close)), None, None)

    rsi = _rsi(close, rsi_len) if (usar_rsi or use_rsi_guard) else pd.Series([50]*len(close))
    rsi_delta = rsi.diff()

    atr_abs = _atr(high, low, close, atr_period) if (use_atr or use_breakout_retest) else pd.Series([np.nan]*len(close))
    atr_pct = atr_abs / close.replace(0, np.nan)

    i = len(close) - 1

    # === Filtros comunes (aplican a LONG/SHORT según corresponda)

    def cond_ema_long():
        if not usar_ema200: return True
        if pd.isna(ema.iloc[i]): return False
        if close.iloc[i] <= ema.iloc[i]: return False
        if use_ema200_slope and ema_slope_pct.iloc[i] < ema200_slope_min: return False
        if use_min_dist_ema200 and abs(_dist_pct(close.iloc[i], ema.iloc[i])) < min_dist_ema200_pct: return False
        return True

    def cond_ema_short():
        if not usar_ema200: return True
        if pd.isna(ema.iloc[i]): return False
        if close.iloc[i] >= ema.iloc[i]: return False
        if use_ema200_slope and ema_slope_pct.iloc[i] > -ema200_slope_min: return False
        if use_min_dist_ema200 and abs(_dist_pct(close.iloc[i], ema.iloc[i])) < min_dist_ema200_pct: return False
        return True

    def cond_adx_long():
        if not usar_adx: return True
        if adx.iloc[i] < adx_min: return False
        if use_adx_rising:
            if (adx.iloc[i] - adx.iloc[i-1]) < adx_delta_min: return False
        return True

    def cond_adx_short():
        if not usar_adx: return True
        if adx.iloc[i] < adx_min: return False
        if use_adx_rising:
            if (adx.iloc[i] - adx.iloc[i-1]) < adx_delta_min: return False
        return True

    def cond_squeeze_long():
        if not usar_squeeze: return True
        if pd.isna(bbw_ma.iloc[i]) or bbw_ma.iloc[i] == 0: return False
        # expansión: ancho actual comparado con su media
        if (bbw.iloc[i] / bbw_ma.iloc[i]) < squeeze_mult: return False
        return True

    def cond_squeeze_short():
        # igual lógica para cortos
        return cond_squeeze_long()

    def cond_rsi_long():
        if not (usar_rsi or use_rsi_guard): return True
        if usar_rsi and rsi.iloc[i] < rsi_long_min: return False
        if use_rsi_guard:
            if rsi_delta.iloc[i] < rsi_delta_min: return False
            if rsi.iloc[i] > rsi_overbought: return False
        return True

    def cond_rsi_short():
        if not (usar_rsi or use_rsi_guard): return True
        if usar_rsi and rsi.iloc[i] > rsi_short_max: return False
        if use_rsi_guard:
            if -rsi_delta.iloc[i] < rsi_delta_min: return False
            # (opcional) Evitar sobreventa extrema para short: no lo forzamos
        return True

    def cond_breakout_retest_long():
        if not use_breakout_retest: return True
        bars = max(1, confirm_wait_bars)
        if i < bars+2: return False
        # Breakout: cierre por encima de la banda superior
        if close.iloc[i-bars] <= bb_up.iloc[i-bars]: 
            return False
        # Retest: en las últimas 'bars' velas, un pullback "controlado" y luego reconquista
        # Usamos ATR para cuantificar retest si está disponible
        if breakout_retest_min_atr_mult > 0 and not pd.isna(atr_abs.iloc[i]):
            # precio cayó al menos X*ATR desde el breakout y luego cerró arriba de la MA BB
            min_pull = close.iloc[i-bars:i].min()
            if (close.iloc[i-bars] - min_pull) < breakout_retest_min_atr_mult * atr_abs.iloc[i-bars]:
                return False
            if close.iloc[i] <= ma.iloc[i]:
                return False
        else:
            # Versión simple: que haya tocado la banda superior o la media y vuelva a cerrar fuerte
            if (low.iloc[i-bars:i].min() > ma.iloc[i-bars:i].min()):
                return False
            if close.iloc[i] <= ma.iloc[i]:
                return False
        return True

    def cond_breakout_retest_short():
        if not use_breakout_retest: return True
        bars = max(1, confirm_wait_bars)
        if i < bars+2: return False
        # Breakout abajo: cierre por debajo de la banda inferior
        if close.iloc[i-bars] >= bb_lo.iloc[i-bars]:
            return False
        if breakout_retest_min_atr_mult > 0 and not pd.isna(atr_abs.iloc[i]):
            max_pull = close.iloc[i-bars:i].max()
            if (max_pull - close.iloc[i-bars]) < breakout_retest_min_atr_mult * atr_abs.iloc[i-bars]:
                return False
            if close.iloc[i] >= ma.iloc[i]:
                return False
        else:
            if (high.iloc[i-bars:i].max() < ma.iloc[i-bars:i].max()):
                return False
            if close.iloc[i] >= ma.iloc[i]:
                return False
        return True

    # === Disparadores (muy simples) basados en BB + confirmación
    def trigger_long():
        # Señal básica: cierre actual por encima de la banda superior (momentum)
        if close.iloc[i] <= bb_up.iloc[i]: 
            return False
        # Confirmación mínima: que la vela anterior ya estuviera presionando (opcional suave)
        return True

    def trigger_short():
        if close.iloc[i] >= bb_lo.iloc[i]: 
            return False
        return True

    # === Evaluación LONG
    if (trigger_long() 
        and cond_ema_long()
        and cond_adx_long()
        and cond_squeeze_long()
        and cond_rsi_long()
        and cond_breakout_retest_long()):
        return {"accion": "BUY", "precio": float(close.iloc[i])}

    # === Evaluación SHORT
    if (trigger_short()
        and cond_ema_short()
        and cond_adx_short()
        and cond_squeeze_short()
        and cond_rsi_short()
        and cond_breakout_retest_short()):
        return {"accion": "SELL", "precio": float(close.iloc[i])}

    return {}


# ======== Compat layer (bot/backtest) ========
def inicializar(cfg_or_state: dict | None = None):
    """Compat: el bot espera estr_init(cfg_estrategia); el backtest no usa estado. Devolvemos dict vacío."""
    return {}

def generar_senal(rows_or_velas, estado=None, cfg=None):
    """
    Compatibilidad doble:
    - Backtest: generar_senal(rows, ctx, cfg_estrategia)
    - Bot/core: generar_senal(velas, estado, CFG)  -> usamos CFG["estrategia"]
    Devuelve {"accion": "BUY"/"SELL", "precio": float} o {}.
    """
    # Detectar cfg de estrategia
    cfg_estrategia = None
    if isinstance(cfg, dict) and "estrategia" in cfg:
        cfg_estrategia = cfg.get("estrategia", {})
    elif isinstance(cfg, dict):
        cfg_estrategia = cfg
    else:
        cfg_estrategia = {}

    rows = rows_or_velas
    # Aceptar DataFrame, lista de dicts o cualquier cosa convertible a DataFrame en _generar_senal_core
    try:
        out = _generar_senal_core(rows, estado or {}, cfg_estrategia)
        if not isinstance(out, dict):
            return {}
        # Normalizar claves esperadas por core/backtest
        if "accion" in out and out.get("precio") is None:
            # precio último cierre si no vino
            try:
                import pandas as _pd
                _df = _pd.DataFrame(rows)
                if "close" in _df.columns and len(_df)>0:
                    out["precio"] = float(_df["close"].iloc[-1])
            except Exception:
                pass
        return out
    except TypeError:
        # Intento alternativo sin estado
        return _generar_senal_core(rows, {}, cfg_estrategia)
