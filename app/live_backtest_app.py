# live_backtest_app.py — UI PRO estilo Binance + full perillas + XLSX ORDENADO + RESUMEN
# Ejecutar: streamlit run live_backtest_app.py

import streamlit as st

# === FAB: session init for persistent curves and config ===
try:
    import streamlit as _st_fab_sess
    if "equity_prev" not in _st_fab_sess.session_state:
        _st_fab_sess.session_state["equity_prev"] = None
    if "equity_curr" not in _st_fab_sess.session_state:
        _st_fab_sess.session_state["equity_curr"] = None
    if "metrics_prev" not in _st_fab_sess.session_state:
        _st_fab_sess.session_state["metrics_prev"] = None
    if "metrics_curr" not in _st_fab_sess.session_state:
        _st_fab_sess.session_state["metrics_curr"] = None
    if "last_config_used" not in _st_fab_sess.session_state:
        _st_fab_sess.session_state["last_config_used"] = None
except Exception:
    pass

import json, copy, glob, time, shutil, datetime, sys, subprocess, os
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from io import BytesIO

st.set_page_config(page_title="Live Backtest", page_icon="📈", layout="wide")
ROOT = Path(__file__).resolve().parent

# ==================== IMPORT BACKTEST ====================
try:
    import backtest as bt
    HAVE_BT, IMPORT_ERR = True, ""
except Exception as e:
    bt = None
    HAVE_BT, IMPORT_ERR = False, str(e)

# ==================== THEME / CSS (Binance PRO) ====================
BINANCE_CSS = """
<style>
.block-container { padding-top: 0.4rem; padding-bottom: 0.8rem; }
header[data-testid="stHeader"] { height: 0px; }
h1,h2,h3,h4 { letter-spacing:.2px; margin-top:0.1rem; }

/* Header */
.header-wrap { display:flex; flex-wrap:wrap; gap:.5rem 1rem; align-items:center; }
.header-wrap .title { font-size:22px; font-weight:700; color:#EAECEF; }
.header-chip { display:inline-flex; align-items:center; gap:.45rem; padding:.2rem .6rem;
  border:1px solid #1E2329; border-radius:999px; background:#0F1318; color:#EAECEF; font-size:12px; }
.header-chip.green { border-color:#0ECB81; color:#0ECB81; }

/* Cards */
.card { background:#12161C; border:1px solid #1E2329; border-radius:16px; padding:14px; }
.card-tight { padding:10px; }

/* Buttons */
.stButton > button { height:42px; border-radius:12px; border:1px solid #1E2329; background:#1A1F26; color:#EAECEF; }
.stButton > button:hover { background:#2B3139; }
.btn-primary > button { background:#0ECB81; color:#0B0E11; font-weight:700; border:none; }
.btn-primary > button:hover { filter:brightness(0.95); }

/* Metrics */
.metric { display:grid; grid-template-columns:auto auto; gap:.25rem .75rem; }
.metric .k { color:#9BA3AF; font-size:12px; }
.metric .v { color:#EAECEF; font-weight:700; }

/* Tables */
thead tr th { background:#12161C !important; }
tbody tr:hover { background:#0F1318 !important; }

/* Divider */
.hr { height:1px; background:#1E2329; border-radius:1px; margin:.75rem 0; }

/* Section title */
.s-title { font-weight:700; color:#EAECEF; font-size:18px; margin-bottom:.5rem; }
</style>
"""
st.markdown(BINANCE_CSS, unsafe_allow_html=True)

# ==================== HELPERS ====================
def load_settings(path=ROOT/"settings.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_df(symbol="ETHUSDT", tf="15m", since="2025-01-01"):
    """Lee el CSV más nuevo en cache/ que matchee símbolo/TF. No descarga nada."""
    cache_dir = ROOT / "cache"
    if not cache_dir.exists():
        return None, "No existe la carpeta cache/ (corré backtest.py una vez).", None
    patt = f"ohlcv_{symbol.replace('USDT','-USDT')}_{tf}_*.csv"
    files = sorted(glob.glob(str(cache_dir / patt)))
    if not files:
        return None, f"No hay CSVs {patt}. Generá cache con backtest.py.", None
    files.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    path = Path(files[0])

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return None, f"No pude leer {path.name}: {e}", path

    # normalizar tiempo
    if "ts" in df.columns:
        df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    elif "time" in df.columns:
        if pd.api.types.is_integer_dtype(df["time"]):
            df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        else:
            df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    else:
        return None, f"El CSV {path.name} no tiene columna ts/time.", path

    # desde 'since' si aplica
    try:
        since_ts = pd.to_datetime(since, utc=True)
        df = df[df["time"] >= since_ts].reset_index(drop=True)
    except Exception:
        pass

    for c in ("open","high","low","close","volume"):
        if c not in df.columns:
            return None, f"El CSV {path.name} no tiene '{c}'. Re-generalo con backtest.py.", path

    return df, None, path

def apply_last_n_days(df, n_days):
    if df is None or df.empty or not n_days or n_days <= 0:
        return df
    cutoff = df["time"].max() - pd.Timedelta(days=int(n_days))
    return df[df["time"] >= cutoff].reset_index(drop=True)

def run_backtest_live(cfg_ui, df_override=None, status=None):
    if not HAVE_BT:
        return None, f"No se pudo importar backtest.py: {IMPORT_ERR}"
    t0 = time.time()
    status and status.write("🔹 Normalizando configuración…")
    CFGN = bt.normalize_cfg(cfg_ui)
    CFGN.setdefault("capital", {})["total_usdt"] = float(cfg_ui.get("capital",{}).get("total_usdt",500.0))

    symbol = cfg_ui.get("simbolos", ["ETHUSDT"])[0]
    tf     = CFGN.get("estrategia", {}).get("tf", "15m")
    since  = cfg_ui.get("since", "2025-01-01")

    if df_override is None:
        status and status.write("🔹 Leyendo cache…")
        df, err, used_path = ensure_df(symbol, tf, since)
        if err:
            return None, f"{err} (símbolo={symbol}, tf={tf})"
    else:
        df = df_override.copy(); used_path=None

    if df is None or df.empty:
        return None, "No se cargaron velas desde cache."

    status and status.write(f"✅ Datos OK · filas: {len(df)}")
    t1 = time.time()
    try:
        trades, audit, eq = bt.run_symbol_on_df(symbol, tf, df, CFGN)
    except Exception as e:
        return None, f"Error en run_symbol_on_df: {e}"
    t2 = time.time()
    status and status.write(f"✅ run_symbol_on_df OK en {t2-t1:.2f}s (total {t2-t0:.2f}s)")

    df_eq = pd.DataFrame(eq, columns=["time","equity"])
    if not df_eq.empty:
        df_eq["time"] = pd.to_datetime(df_eq["time"], utc=True).dt.tz_convert(None)

    return {
        "trades": pd.DataFrame(trades),
        "equity": df_eq,
        "audit": audit,
        "used_path": used_path
    }, None

# --------- CSV->DataFrame ordenado (sirve de base para Excel) ---------
def prepare_trades_csv(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename_map = {
        "motivo": "exit_reason",
        "Motivo": "exit_reason",
        "Motivo salida": "exit_reason",
        "Motivo_salida": "exit_reason",
        "reason": "exit_reason",
        "Tipo": "exit_reason",
        "Side": "side",
        "side": "side",
        "qty": "qty",
        "quantity": "qty",
        "amount": "qty",
        "entry_qty": "qty",
        "price_in": "price_entry",
        "price_out": "price_exit",
        "entry_price": "price_entry",
        "exit_price": "price_exit",
        "precio_entrada": "price_entry",
        "precio_salida": "price_exit",
        "pnl_pct": "pnl_pct",
        "pnl%": "pnl_pct",
        "PnL%": "pnl_pct",
        "ret_pct": "pnl_pct",
        "pnl": "pnl",
        "PnL": "pnl",
        "ret_usdt": "pnl",
        "symbol": "symbol",
        "Símbolo": "symbol",
        "ts_entry": "ts_entry",
        "ts_exit": "ts_exit",
        "t_entry": "ts_entry",
        "t_exit": "ts_exit",
        "open_time": "ts_entry",
        "close_time": "ts_exit",
    }
    for k, v in list(rename_map.items()):
        if k in df.columns:
            df.rename(columns={k: v}, inplace=True)

    for c in ("ts_entry", "ts_exit"):
        if c in df.columns:
            try:
                df[c] = pd.to_datetime(df[c], unit="ms", errors="coerce").dt.tz_localize("UTC").dt.tz_convert(None)
            except Exception:
                df[c] = pd.to_datetime(df[c], errors="coerce")

    if "exit_reason" in df.columns:
        df["exit_reason"] = df["exit_reason"].astype(str).str.upper().str.strip()

    for c in ("qty","price_entry","price_exit","pnl","pnl_pct"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    preferred = [
        "symbol","side","qty",
        "price_entry","price_exit",
        "pnl","pnl_pct",
        "ts_entry","ts_exit",
        "exit_reason"
    ]
    ordered = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[ordered]

    if "ts_entry" in df.columns:
        df = df.sort_values("ts_entry").reset_index(drop=True)

    return df.fillna("")

# ---------- XLSX con formato y hoja Resumen ----------
def df_to_pretty_xlsx(df: pd.DataFrame, resumen: dict) -> bytes:
    # Renombrar encabezados a español
    rename_es = {
        "symbol": "Símbolo",
        "side": "Dirección",
        "qty": "Cantidad",
        "price_entry": "Entrada",
        "price_exit": "Salida",
        "pnl": "PnL (USDT)",
        "pnl_pct": "PnL (%)",
        "ts_entry": "Fecha Entrada",
        "ts_exit": "Fecha Salida",
        "exit_reason": "Motivo",
    }
    df_es = df.rename(columns={k: v for k, v in rename_es.items() if k in df.columns}).copy()

    # Preparar writer
    output = BytesIO()
    engine = None
    try:
        engine = "xlsxwriter"
        writer = pd.ExcelWriter(output, engine=engine)
    except Exception:
        engine = "openpyxl"
        writer = pd.ExcelWriter(output, engine=engine)

    # ---- Hoja Trades ----
    sheet_trades = "Trades"
    df_es.to_excel(writer, index=False, sheet_name=sheet_trades)

    if engine == "xlsxwriter":
        wb  = writer.book
        ws  = writer.sheets[sheet_trades]
        fmt_hdr = wb.add_format({"bold": True, "align": "center", "valign":"vcenter",
                                 "border":1, "bg_color":"#eaeaea"})
        fmt_c   = wb.add_format({"align": "center", "valign":"vcenter", "border":1})
        fmt_n2  = wb.add_format({"align": "center", "valign":"vcenter", "border":1, "num_format":"0.00"})
        fmt_n4  = wb.add_format({"align": "center", "valign":"vcenter", "border":1, "num_format":"0.0000"})

        # Encabezados
        for col, col_name in enumerate(df_es.columns, start=1):
            ws.write(1, col-1, col_name, fmt_hdr)

        # Celdas
        nrows, ncols = df_es.shape
        for r in range(nrows):
            for c in range(ncols):
                val = df_es.iat[r, c]
                # elegir formato
                if isinstance(val, (int, float)):
                    fmt = fmt_n2 if col_name not in ("Cantidad",) else fmt_n4
                else:
                    fmt = fmt_c
                ws.write(r+2, c, val, fmt)

        # Ancho de columnas
        for i, c in enumerate(df_es.columns):
            maxlen = max([len(str(c))] + [len(str(x)) for x in df_es[c].astype(str).tolist()])
            ws.set_column(i, i, min(maxlen+2, 28))

        # Freeze header
        ws.freeze_panes(2, 0)

        # ---- Hoja Resumen
        sheet_res = "Resumen"
        ws2 = wb.add_worksheet(sheet_res)
        big = wb.add_format({"bold": True, "font_size": 18})
        lbl = wb.add_format({"bold": True})
        val = wb.add_format({"bold": True, "font_color":"#0a8754"})

        ws2.write(0, 0, "Resumen de Resultados", big)
        ws2.write(2, 0, "PnL total (USDT):", lbl); ws2.write(2, 1, resumen.get("pnl_total", 0.0), val)
        ws2.write(3, 0, "Winrate (%):", lbl);      ws2.write(3, 1, resumen.get("winrate", 0.0), val)
        ws2.write(4, 0, "Profit Factor:", lbl);    ws2.write(4, 1, resumen.get("pf", "NA"), val)
        ws2.set_column(0, 1, 22)

    else:
        # openpyxl: formateo más simple para asegurar compatibilidad
        writer.sheets[sheet_trades].freeze_panes = "A3"

        # Resumen como segunda hoja
        pd.DataFrame(
            {
                "Métrica": ["PnL total (USDT)", "Winrate (%)", "Profit Factor"],
                "Valor": [resumen.get("pnl_total", 0.0), resumen.get("winrate", 0.0), resumen.get("pf", "NA")],
            }
        ).to_excel(writer, index=False, sheet_name="Resumen")

    writer.close()
    return output.getvalue()

# ==================== EXPORTAR AL BOT (bridge) ====================
CORE_DIR = ROOT / "core"
NEW_SETTINGS_PATH = ROOT / "settings.json"
LEGACY_SETTINGS_PATH = CORE_DIR / "config.json"

# Ruta real de settings del bot
CORE_SETTINGS_PATH = ROOT / "config" / "settings.json"

def _now_iso():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def map_new_to_legacy(cfg_new: dict) -> dict:
    cfg_legacy = {}
    cfg_legacy.update(cfg_new)
    guard = cfg_new.get("auto_trailing", {}).get("guard", {})
    tr = cfg_legacy.setdefault("trailing", {})
    if "min_mfe_to_trail_pct" in guard:
        tr.setdefault("activar_pct", guard["min_mfe_to_trail_pct"])
    if "min_mfe_to_be_atr" in guard:
        tr.setdefault("be_atr_mult", guard["min_mfe_to_be_atr"])
    if "be_lock_atr" in guard:
        tr.setdefault("lock_atr_mult", guard["be_lock_atr"])
    estr = cfg_new.get("estrategia", {})
    if estr.get("tf"):
        cfg_legacy.setdefault("timeframe", estr["tf"])
    return cfg_legacy

def save_settings_new(cfg_new: dict):
    NEW_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NEW_SETTINGS_PATH.exists():
        shutil.copy2(NEW_SETTINGS_PATH, NEW_SETTINGS_PATH.with_suffix(".bak"))
    with open(NEW_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg_new, fh, ensure_ascii=False, indent=2)

def write_legacy_for_core(cfg_legacy: dict):
    CORE_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_SETTINGS_PATH.exists():
        shutil.copy2(LEGACY_SETTINGS_PATH, LEGACY_SETTINGS_PATH.with_suffix(f".{_now_iso()}.bak"))
    with open(LEGACY_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg_legacy, fh, ensure_ascii=False, indent=2)

def write_core_settings_json(cfg_ui: dict):
    CORE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CORE_SETTINGS_PATH.exists():
        shutil.copy2(CORE_SETTINGS_PATH, CORE_SETTINGS_PATH.with_name(f"settings.{_now_iso()}.bak"))
    with open(CORE_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg_ui, fh, ensure_ascii=False, indent=2)

def apply_to_bot(cfg_ui: dict):
    estr = cfg_ui.get("estrategia", {})
    if estr.get("tf") not in {"1m","5m","15m","30m","1h","2h","4h"}:
        raise ValueError("Timeframe inválido. Elegí 1m,5m,15m,30m,1h,2h,4h.")
    if not cfg_ui.get("tp",{}).get("use_atr_dynamic", False):
        stop_ = float(cfg_ui.get("riesgo",{}).get("stop_pct", 1.0))
        take_ = float(cfg_ui.get("riesgo",{}).get("take_pct", 3.0))
        if take_ <= stop_:
            raise ValueError("take_pct debe ser mayor que stop_pct (si TP dinámico está OFF).")
    save_settings_new(cfg_ui)
    write_legacy_for_core(map_new_to_legacy(cfg_ui))

# ==================== SESSION ====================
for k, v in [("current_run", None), ("last_run", None)]:
    if k not in st.session_state: st.session_state[k] = v

# ==================== CARGA SETTINGS Y HEADER ====================
try:
    cfg_base = load_settings()
except Exception as e:
    st.error(f"No pude leer settings.json: {e}")
    st.stop()

symbol_hdr = cfg_base.get("simbolos", ["ETHUSDT"])[0]
tf_hdr = cfg_base.get("estrategia", {}).get("tf", "15m")
cache_dir = ROOT / "cache"
have_cache = cache_dir.exists()

st.markdown(
    f'''
    <div class="header-wrap">
      <div class="title">Live Backtest</div>
      <div class="header-chip">{symbol_hdr}</div>
      <div class="header-chip">{tf_hdr}</div>
      <div class="header-chip {'green' if have_cache else ''}">cache {'OK' if have_cache else 'faltante'}</div>
      <div class="header-chip green">UI pro</div>
    </div>
    ''',
    unsafe_allow_html=True
)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### Símbolo")
    available_symbols = ["ETHUSDT","BTCUSDT","SOLUSDT"]
    sym_choice = st.selectbox("Símbolo", available_symbols,
                              index=available_symbols.index(symbol_hdr) if symbol_hdr in available_symbols else 0,
                              help="Símbolo a testear y a enviar al bot.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown("### Rango de datos")
    use_last_days = st.checkbox("Usar últimos N días", value=True,
                                help="Filtra el dataset a los últimos N días para acelerar las pruebas.")
    n_days = st.number_input("N días (si está activado)", value=30, min_value=1, step=1)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown("### Parámetros (rápidos)")

    stop_pct = st.slider("stop_pct (%)", 0.2, 3.0,
                         float(cfg_base.get("riesgo",{}).get("stop_pct", 1.0)), 0.1,
                         help="Stop fijo en %. Define R con take_pct.")
    take_pct = st.slider("take_pct (%)", 1.0, 10.0,
                         float(cfg_base.get("riesgo",{}).get("take_pct", 5.0)), 0.5,
                         help="Take fijo en %. Si TP dinámico (ATR) está ON, se ignora.")
    riesgo_usdt = st.number_input("riesgo_usdt (USDT)",
                         value=float(cfg_base.get("riesgo",{}).get("riesgo_usdt",10.0)), step=1.0,
                         help="USDT a arriesgar por operación.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    partials_on = st.checkbox("Activar ventas parciales",
                              value=bool(cfg_base.get("partials",{}).get("enabled", True)),
                              help="Liquida una parte en un múltiplo de R.")
    fraction = st.slider("Proporción parcial", 0.00, 0.99,
                         float(cfg_base.get("partials",{}).get("fraction",0.8)), 0.01,
                         help="Fracción a vender en el parcial (0.80 = 80%).")
    at_R = st.slider("Mín. R para parcial (xR)", 0.50, 10.0,
                     float(cfg_base.get("partials",{}).get("at_R",2.0)), 0.10,
                     help="En qué múltiplo de R ejecutar el parcial.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    trail_on = st.checkbox("Trailing habilitado",
                           value=bool(cfg_base.get("auto_trailing",{}).get("enabled", True)),
                           help="Mueve el stop (TSL/BE) cuando hay ganancia.")
    min_mfe_to_trail_pct = st.slider("Activación trailing (%)", 0.5, 10.0,
                         float(cfg_base.get("auto_trailing",{}).get("guard",{}).get("min_mfe_to_trail_pct",2.4)), 0.1,
                         help="Ganancia mínima desde la entrada para empezar a correr el trailing.")
    min_mfe_to_be_atr = st.slider("BE a (xATR)", 0.0, 5.0,
                         float(cfg_base.get("auto_trailing",{}).get("guard",{}).get("min_mfe_to_be_atr",1.5)), 0.1,
                         help="Avance mínimo (en ATR) para pasar a break-even.")
    be_lock_atr = st.slider("BE lock (xATR)", 0.00, 2.00,
                         float(cfg_base.get("auto_trailing",{}).get("guard",{}).get("be_lock_atr",0.4)), 0.05,
                         help="Colchón sobre BE (en ATR) para asegurar ganancia.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown("### Temporalidad")
    estr = cfg_base.get("estrategia", {})
    tf_choice = st.selectbox("Timeframe", ["1m","5m","15m","30m","1h","2h","4h"],
                             index=["1m","5m","15m","30m","1h","2h","4h"].index(estr.get("tf","15m")),
                             help="Timeframe de la estrategia.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown("### Estrategia e Indicadores")

    # ---- Bollinger / Volatilidad ----
    with st.expander("Bollinger / Volatilidad", expanded=False):
        bb_len = st.number_input("bb_len", value=int(estr.get("bb_len",20)), step=1,
                                 help="Longitud de Bandas de Bollinger (media).")
        bb_mult = st.number_input("bb_mult", value=float(estr.get("bb_mult",2.0)), step=0.1,
                                 help="Multiplicador de desviación (ancho de bandas).")
        vol_relativo = st.checkbox("vol_relativo", value=bool(estr.get("vol_relativo", False)),
                                 help="Evalúa volatilidad contra su propio promedio.")
        vol_ma_n = st.number_input("vol_ma_n", value=int(estr.get("vol_ma_n",20)), step=1,
                                 help="Ventana de promedio para volatilidad relativa.")
        vol_min_mult = st.number_input("vol_min_mult", value=float(estr.get("vol_min_mult",2.5)), step=0.1,
                                 help="Mínimo múltiplo de vol. para permitir operación.")
        ancho_min_pct = st.number_input("ancho_min_pct (%)", value=float(estr.get("ancho_min_pct",0.50)), step=0.05,
                                 help="Ancho mínimo de bandas como % para evitar micro-rangos.")

    # ---- RSI ----
    with st.expander("RSI", expanded=False):
        usar_rsi = st.checkbox("usar_rsi", value=bool(estr.get("usar_rsi",True)),
            help="Activa el filtro de impulso; evita operar sin fuerza.")
        rsi_len = st.number_input("rsi_len", value=int(estr.get("rsi_len",14)), step=1,
            help="Velas para calcular RSI (más bajo = más sensible).")
        rsi_long_min = st.number_input("rsi_long_min", value=float(estr.get("rsi_long_min",60.0)), step=1.0,
            help="Para largos: RSI mínimo permitido (fuerza suficiente).")
        rsi_short_max = st.number_input("rsi_short_max", value=float(estr.get("rsi_short_max",35.0)), step=1.0,
            help="Para cortos: RSI máximo permitido (debilidad).")
        use_rsi_guard = st.checkbox("use_rsi_guard", value=bool(estr.get("use_rsi_guard", False)),
            help="Guarda entradas cuando el impulso se frena de una vela a otra.")
        rsi_delta_min = st.number_input("rsi_delta_min", value=float(estr.get("rsi_delta_min",0.0)), step=0.1,
            help="Cambio mínimo de RSI entre velas para considerar que ‘acelera’.")
        rsi_overbought = st.number_input("rsi_overbought", value=float(estr.get("rsi_overbought",0.0)), step=1.0,
            help="Si RSI supera este valor, evita compras en sobrecompra (0 desactiva).")

    # ---- ADX ----
    with st.expander("ADX", expanded=False):
        usar_adx = st.checkbox("usar_adx", value=bool(estr.get("usar_adx", True)),
            help="Exige fuerza de tendencia; evita operar en rango.")
        adx_len = st.number_input("adx_len", value=int(estr.get("adx_len",14)), step=1,
            help="Longitud para ADX.")
        adx_min = st.number_input("adx_min", value=float(estr.get("adx_min",22.0)), step=0.5,
            help="Mínimo ADX para habilitar entradas.")
        use_adx_rising = st.checkbox("use_adx_rising", value=bool(estr.get("use_adx_rising", False)),
            help="Exige que ADX venga en aumento (fuerza creciente).")
        adx_delta_min = st.number_input("adx_delta_min", value=float(estr.get("adx_delta_min",0.0)), step=0.05,
            help="Mínimo ascenso de ADX entre velas para considerar ‘mejora’.")

    # ---- EMA200 ----
    with st.expander("EMA200", expanded=False):
        usar_ema200 = st.checkbox("usar_ema200", value=bool(estr.get("usar_ema200", True)),
            help="Usa la EMA200 como filtro de tendencia.")
        ema_len = st.number_input("ema_len", value=int(estr.get("ema_len",200)), step=5,
            help="Período de la EMA base.")
        use_ema200_slope = st.checkbox("use_ema200_slope", value=bool(estr.get("use_ema200_slope", False)),
            help="Exige pendiente mínima de EMA200 (tendencia definida).")
        ema200_slope_min_pct_per_bar = st.number_input("ema200_slope_min_pct_per_bar", value=float(estr.get("ema200_slope_min_pct_per_bar",0.0)), step=0.01,
            help="Pendiente mínima por vela (en %) para validar tendencia.")
        use_min_dist_ema200 = st.checkbox("use_min_dist_ema200", value=bool(estr.get("use_min_dist_ema200", True)),
            help="Exige distancia mínima a la EMA para evitar entradas pegadas.")
        min_dist_ema200_pct = st.number_input("min_dist_ema200_pct (%)", value=float(estr.get("min_dist_ema200_pct",0.6)), step=0.05,
            help="Esa distancia mínima en %.")

    # ---- Squeeze / BB Width ----
    with st.expander("Squeeze / Contracción", expanded=False):
        usar_squeeze = st.checkbox("usar_squeeze", value=bool(estr.get("usar_squeeze", False)),
            help="Busca contracción antes de rompimientos.")
        bb_width_ma_len = st.number_input("bb_width_ma_len", value=int(estr.get("bb_width_ma_len",50)), step=1,
            help="MA del ancho de bandas.")
        squeeze_mult = st.number_input("squeeze_mult", value=float(estr.get("squeeze_mult",0.0)), step=0.05,
            help="Umbral de contracción respecto a su promedio.")

    # ---- Breakout + Retest ----
    with st.expander("Breakout + Retest (ATR)", expanded=False):
        use_breakout_retest = st.checkbox("use_breakout_retest", value=bool(estr.get("use_breakout_retest", False)),
            help="Exige rompimiento y retest para entradas más limpias.")
        breakout_retest_min_atr_mult = st.number_input("breakout_retest_min_atr_mult", value=float(estr.get("breakout_retest_min_atr_mult",1.0)), step=0.1,
            help="Fuerza mínima del rompimiento medida en ATR.")
        confirm_wait_bars = st.number_input("confirm_wait_bars", value=int(estr.get("confirm_wait_bars",1)), step=1,
            help="Velas de espera para confirmar el retest.")

    # ---- ATR base ----
    with st.expander("ATR base", expanded=False):
        use_atr = st.checkbox("use_atr", value=bool(estr.get("use_atr", False)),
            help="Expone ATR para otras lógicas (trailing dinámico, filtros).")
        atr_period = st.number_input("atr_period", value=int(estr.get("atr_period",14)), step=1,
            help="Período para ATR.")

    # ---- TP Dinámico / Fijo ----
    with st.expander("Take Profit", expanded=False):
        tp_base = cfg_base.get("tp",{})
        use_atr_dynamic = st.checkbox("tp.use_atr_dynamic", value=bool(tp_base.get("use_atr_dynamic", False)),
            help="Si ON, TP por ATR; si OFF, usa take_pct.")
        r_mult_cons = st.number_input("r_mult.conservador", value=float(tp_base.get("r_mult",{}).get("conservador",2.0)), step=0.1)
        r_mult_mod  = st.number_input("r_mult.moderado",   value=float(tp_base.get("r_mult",{}).get("moderado",3.0)), step=0.1)
        r_mult_agr  = st.number_input("r_mult.agresivo",   value=float(tp_base.get("r_mult",{}).get("agresivo",5.5)), step=0.1)

    # ---- Filtro de sesión ----
    with st.expander("Filtro de sesión", expanded=False):
        sess_base = cfg_base.get("session_filter", {})
        sess_enabled = st.checkbox("session_filter.enabled", value=bool(sess_base.get("enabled", False)),
            help="Evita operar en horas/días específicos.")
        blocked_hours = st.multiselect("blocked_hours (0-23)", options=list(range(24)),
            default=sess_base.get("blocked_hours", []),
            help="Horas bloqueadas UTC (0-23).")
        blocked_weekdays = st.multiselect("blocked_weekdays (0=Lun ... 6=Dom)", options=list(range(7)),
            default=sess_base.get("blocked_weekdays", []),
            help="Días de la semana bloqueados.")

    # ---- Control de Riesgo ----
    with st.expander("Control de Riesgo", expanded=False):
        rc_base = cfg_base.get("risk_controls", {})
        daily_max_trades = st.number_input("daily_max_trades", value=int(rc_base.get("daily_max_trades",5)), step=1,
            help="Máximo de operaciones por día.")
        daily_max_loss_usdt = st.number_input("daily_max_loss_usdt", value=float(rc_base.get("daily_max_loss_usdt",35.0)), step=1.0,
            help="Pérdida diaria máxima (USDT).")
        cool_base = rc_base.get("cooldown_after_sl_streak", {})
        cool_count = st.number_input("cooldown_after_sl_streak.count", value=int(cool_base.get("count",2)), step=1,
            help="Cantidad de SL seguidos para activar pausa.")
        cool_bars = st.number_input("cooldown_after_sl_streak.bars", value=int(cool_base.get("bars",20)), step=1,
            help="Velas a pausar tras racha de SL.")

# ==================== CONSTRUIR CFG (desde perillas) ====================
cfg2 = copy.deepcopy(cfg_base)
cfg2["simbolos"] = st.session_state.get("fab_symbols", [sym_choice])

cfg2.setdefault("capital", {}).setdefault("total_usdt", float(cfg_base.get("capital",{}).get("total_usdt", 500.0)))
cfg2.setdefault("riesgo", {})
cfg2["riesgo"]["stop_pct"] = float(stop_pct)
cfg2["riesgo"]["take_pct"] = float(take_pct)
cfg2["riesgo"]["riesgo_usdt"] = float(riesgo_usdt)
# --- overrides desde el panel rápido (si están seteados) ---
if "fab_rr" in st.session_state:
    cfg2["riesgo"]["relacion"] = st.session_state["fab_rr"]
else:
    cfg2["riesgo"]["relacion"] = cfg2.get("riesgo", {}).get("relacion", "1:3")
if "fab_take_pct" in st.session_state:
    cfg2["riesgo"]["take_pct"] = float(st.session_state["fab_take_pct"])
cfg2.setdefault("partials", {})
cfg2["partials"]["enabled"] = bool(partials_on)
cfg2["partials"]["fraction"] = float(fraction)
cfg2["partials"]["at_R"] = float(at_R)
cfg2.setdefault("auto_trailing", {})
cfg2["auto_trailing"]["enabled"] = bool(trail_on)
cfg2["auto_trailing"].setdefault("guard", {})
cfg2["auto_trailing"]["guard"]["min_mfe_to_trail_pct"] = float(min_mfe_to_trail_pct)
cfg2["auto_trailing"]["guard"]["min_mfe_to_be_atr"] = float(min_mfe_to_be_atr)
cfg2["auto_trailing"]["guard"]["be_lock_atr"] = float(be_lock_atr)
estr2 = cfg2.setdefault("estrategia", {})
estr2["tf"] = tf_choice
# Bollinger/Vol
estr2["bb_len"]=int(bb_len); estr2["bb_mult"]=float(bb_mult)
estr2["vol_relativo"]=bool(vol_relativo); estr2["vol_ma_n"]=int(vol_ma_n)
estr2["vol_min_mult"]=float(vol_min_mult); estr2["ancho_min_pct"]=float(ancho_min_pct)
# RSI
estr2["usar_rsi"]=bool(usar_rsi); estr2["rsi_len"]=int(rsi_len)
estr2["rsi_long_min"]=float(rsi_long_min); estr2["rsi_short_max"]=float(rsi_short_max)
estr2["use_rsi_guard"]=bool(use_rsi_guard); estr2["rsi_delta_min"]=float(rsi_delta_min)
estr2["rsi_overbought"]=float(rsi_overbought)
# ADX
estr2["usar_adx"]=bool(usar_adx); estr2["adx_len"]=int(adx_len)
estr2["adx_min"]=float(adx_min); estr2["use_adx_rising"]=bool(use_adx_rising)
estr2["adx_delta_min"]=float(adx_delta_min)
# EMA200
estr2["usar_ema200"]=bool(usar_ema200); estr2["ema_len"]=int(ema_len)
estr2["use_ema200_slope"]=bool(use_ema200_slope)
estr2["ema200_slope_min_pct_per_bar"]=float(ema200_slope_min_pct_per_bar)
estr2["use_min_dist_ema200"]=bool(use_min_dist_ema200)
estr2["min_dist_ema200_pct"]=float(min_dist_ema200_pct)
# Squeeze
estr2["usar_squeeze"]=bool(usar_squeeze); estr2["bb_width_ma_len"]=int(bb_width_ma_len)
estr2["squeeze_mult"]=float(squeeze_mult)
# Breakout/Retest
estr2["use_breakout_retest"]=bool(use_breakout_retest)
estr2["breakout_retest_min_atr_mult"]=float(breakout_retest_min_atr_mult)
estr2["confirm_wait_bars"]=int(confirm_wait_bars)
# ATR
estr2["use_atr"]=bool(use_atr); estr2["atr_period"]=int(atr_period)
# TP dinámico
tp2 = cfg2.setdefault("tp", {})
tp2["use_atr_dynamic"]=bool(use_atr_dynamic)
tp2.setdefault("r_mult", {})
tp2["r_mult"]["conservador"]=float(r_mult_cons)
tp2["r_mult"]["moderado"]=float(r_mult_mod)
tp2["r_mult"]["agresivo"]=float(r_mult_agr)

# Filtro de sesión / Riesgo
sess2 = cfg2.setdefault("session_filter", {})
sess2["enabled"]=bool(sess_enabled)
sess2["blocked_hours"]=list(blocked_hours)
sess2["blocked_weekdays"]=list(blocked_weekdays)
rc2 = cfg2.setdefault("risk_controls", {})
rc2["daily_max_trades"]=int(daily_max_trades)
rc2["daily_max_loss_usdt"]=float(daily_max_loss_usdt)
rc2.setdefault("cooldown_after_sl_streak", {})
rc2["cooldown_after_sl_streak"]["count"]=int(cool_count)
rc2["cooldown_after_sl_streak"]["bars"]=int(cool_bars)

# ==================== CUERPO (3 columnas) ====================
left, mid, right = st.columns([1.05, 1.7, 1.05])

with left:
    st.markdown('<div class="card"><div class="s-title">RUN Backtest</div>', unsafe_allow_html=True)
    run_bt = st.button("RUN", type="primary", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with mid:
    st.markdown('<div class="card"><div class="s-title">Curva de equity</div>', unsafe_allow_html=True)
    curve_slot = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card"><div class="s-title">Métricas</div>', unsafe_allow_html=True)
    metrics_slot = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

status = st.empty()  # progreso textual

# ==================== RUN ====================
if run_bt:
    if st.session_state.get("current_run") is not None:
        st.session_state["last_run"] = st.session_state["current_run"]

    symbol = cfg2.get("simbolos", ["ETHUSDT"])[0]
    tf     = cfg2.get("estrategia", {}).get("tf", "15m")
    since  = cfg2.get("since", "2025-01-01")

    df_all, err, used_path = ensure_df(symbol, tf, since)
    if err:
        st.error(err); st.stop()

    df_used = apply_last_n_days(df_all, int(n_days)) if use_last_days else df_all
    out, err = run_backtest_live(cfg2, df_override=df_used, status=status)
    if err:
        st.error(err)
    else:
        df_tr, df_eq, audit = out["trades"], out["equity"], out["audit"]

        # Curva
        if df_eq is None or df_eq.empty:
            curve_slot.info("Sin datos de equity.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_eq["time"], y=df_eq["equity"], mode="lines", name="Equity"))
            fig.update_layout(height=420, margin=dict(l=10,r=10,t=10,b=10),
                              paper_bgcolor="#12161C", plot_bgcolor="#12161C",
                              xaxis=dict(gridcolor="#1E2329"), yaxis=dict(gridcolor="#1E2329"))
            curve_slot.plotly_chart(fig, use_container_width=True)

        # Métricas
        pnl_total = round(df_tr["pnl"].sum(),2) if not df_tr.empty else 0.0
        wins = df_tr[df_tr["pnl"]>0]; losses = df_tr[df_tr["pnl"]<0]
        winrate = round(len(wins)/len(df_tr)*100,2) if len(df_tr)>0 else 0.0
        pf = round(wins["pnl"].sum()/abs(losses["pnl"].sum()),2) if (len(wins)>0 and len(losses)>0) else ("NA" if len(wins)>0 else 0.0)

        motivo_col = None
        for c in ["exit_reason","reason","motivo","Motivo salida","Motivo_salida","Motivo"]:
            if c in df_tr.columns: motivo_col=c; break
        counts = {}
        if motivo_col:
            val = df_tr[motivo_col].astype(str).str.upper().str.strip()
            show = ["SL","TP"]
            if cfg2["partials"]["enabled"]: show += ["PARCIAL"]
            if cfg2["auto_trailing"]["enabled"]: show += ["TSL","BE"]
            for k in show: counts[k] = int((val==k).sum())

        m_html = f"""
        <div class="metric">
          <div class="k">PnL total</div><div class="v">{pnl_total} USDT</div>
          <div class="k">Operaciones</div><div class="v">{int(len(df_tr))}</div>
          <div class="k">Winrate</div><div class="v">{winrate}%</div>
          <div class="k">Profit Factor</div><div class="v">{pf}</div>
        """
        for k in ["SL","TP","PARCIAL","TSL","BE"]:
            if k in counts: m_html += f'<div class="k">Salidas {k}</div><div class="v">{counts[k]}</div>'
        m_html += "</div>"
        metrics_slot.markdown(m_html, unsafe_allow_html=True)

# === FAB: Auto-export Excel ===
try:
    import pandas as pd
    # infer trades df name: prefer df_tr if exists else first displayed table var
    df_trades_var = None
    if 'df_tr' in locals(): df_trades_var = df_tr
    elif 'df_trades' in locals(): df_trades_var = df_trades
    # equity variable inference
    eq_df = None
    if 'df_eq' in locals(): 
        eq_df = df_eq.rename(columns={'time':'ts'}) if 'time' in df_eq.columns else df_eq
    # metrics inference
    metrics_dict = {}
    if 'pnl_total' in locals(): metrics_dict['PnL'] = pnl_total
    if 'winrate' in locals(): metrics_dict['WR'] = winrate
    if 'pf' in locals(): metrics_dict['PF'] = pf
    # session persistence
    st.session_state['equity_prev'] = st.session_state.get('equity_curr')
    st.session_state['equity_curr'] = eq_df.copy() if eq_df is not None else None
    st.session_state['last_config_used'] = _sanitize_riesgo(cfg2) if 'cfg2' in locals() else {}
    out_dir = Path('out'); out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"backtest_{_now_iso()}.xlsx"
    export_excel_completo(
        path_xlsx=str(out_path),
        df_trades=df_trades_var,
        equity_df=eq_df if eq_df is not None else pd.DataFrame(columns=['ts','equity']),
        settings_dict=st.session_state.get('last_config_used') or {},
        metrics_dict=metrics_dict,
        equity_prev_df=st.session_state.get('equity_prev')
    )
    st.success(f"Excel auto-guardado: {out_path}")
except Exception as _e_auto:
    st.warning(f"No se pudo auto-exportar Excel: {_e_auto}")

# --- SAFE DEFAULTS FOR FIRST RUN (evita NameError si aún no corriste RUN) ---
pnl_total   = locals().get('pnl_total', 0.0)
winrate     = locals().get('winrate', 0.0)
pf          = locals().get('pf', "NA")
df_tr       = locals().get('df_tr', pd.DataFrame())
counts      = locals().get('counts', {})
symbol      = locals().get('symbol', (cfg2.get('simbolos', ['ETHUSDT'])[0] if 'cfg2' in locals() else 'ETHUSDT'))
tf          = locals().get('tf', (cfg2.get('estrategia', {}).get('tf', '15m') if 'cfg2' in locals() else '15m'))
use_last_days = locals().get('use_last_days', False)
n_days        = locals().get('n_days', None)

st.session_state["current_run"] = {
            "metrics": {
                "PnL": pnl_total,
                "Ops": int(len(df_tr)),
                "WR": winrate,
                "PF": pf,
                **{f"Out_{k}": v for k, v in counts.items()}},
            "trades": df_tr.copy(),
            "symbol": symbol,
            "tf": tf,
            "n_days": int(n_days) if use_last_days else None
        }

# ==================== COMPARADOR Y TRADES ====================
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown("#### Comparador: Anterior vs Actual")
prev = st.session_state.get("last_run"); cur = st.session_state.get("current_run")
if prev is None or cur is None:
    st.info("Corré al menos dos veces para ver comparación.")
else:
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="card card-tight"><div class="s-title">Anterior</div>', unsafe_allow_html=True)
        st.caption(f"{prev.get('symbol','?')} · {prev.get('tf','?')} · "
                   f"{'últimos ' + str(prev.get('n_days')) + ' días' if prev.get('n_days') else 'todo'}")
        st.json(prev["metrics"])
        st.markdown('</div>', unsafe_allow_html=True)
    with b:
        st.markdown('<div class="card card-tight"><div class="s-title">Actual</div>', unsafe_allow_html=True)
        st.caption(f"{cur.get('symbol','?')} · {cur.get('tf','?')} · "
                   f"{'últimos ' + str(cur.get('n_days')) + ' días' if cur.get('n_days') else 'todo'}")
        st.json(cur["metrics"])
        st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown("#### Trades (últimos 200)")
if cur and not cur["trades"].empty:
    df_show = cur["trades"].copy()
    for c in ("ts_entry","ts_exit"):
        if c in df_show.columns:
            df_show[c] = pd.to_datetime(df_show[c], unit="ms", errors="coerce")
    pref = ["symbol","side","qty","price_entry","price_exit","pnl","pnl_pct","ts_entry","ts_exit","exit_reason"]
    order = [c for c in pref if c in df_show.columns] + [c for c in df_show.columns if c not in pref]
    df_show = df_show[order]
    st.dataframe(df_show.tail(200), use_container_width=True, height=420)

    # ===== DESCARGA **XLSX** ORDENADO + RESUMEN =====
    df_csv = prepare_trades_csv(cur["trades"])
    resumen = {
        "pnl_total": round(df_csv["pnl"].sum(), 2) if "pnl" in df_csv.columns else 0.0,
        "winrate": round((df_csv["pnl"] > 0).mean()*100, 2) if "pnl" in df_csv.columns and len(df_csv)>0 else 0.0,
        "pf": round(df_csv.loc[df_csv["pnl"]>0,"pnl"].sum() / abs(df_csv.loc[df_csv["pnl"]<0,"pnl"].sum()), 2)
              if ("pnl" in df_csv.columns and (df_csv["pnl"]>0).any() and (df_csv["pnl"]<0).any()) else "NA",
    }
    xlsx_bytes = df_to_pretty_xlsx(df_csv, resumen)
    st.download_button(
        "Descargar Excel (ordenado + resumen)",
        data=xlsx_bytes,
        file_name="trades_live_ordenado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
else:
    st.info("Sin trades para mostrar.")

# ==================== APLICAR AL BOT + RUN CORE (CMD) ====================
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown("### 📤 Aplicar esta configuración al bot (core)")

cA, cB, cC, cD = st.columns([1,1,1,1])

with cA:
    if st.button("Guardar settings.json (nuevo)", use_container_width=True):
        try:
            save_settings_new(cfg2)
            st.success("✅ settings.json guardado en la raíz.")
        except Exception as e:
            st.error(f"❌ No se pudo guardar settings.json: {e}")

with cB:
    if st.button("Aplicar al bot (genera core/config.json)", use_container_width=True):
        try:
            apply_to_bot(cfg2)
            st.success("✅ Enviado al bot: creado/actualizado core/config.json.")
        except Exception as e:
            st.error(f"❌ No se pudo aplicar al bot: {e}")

with cC:
    if st.button("Aplicar al bot (config/settings.json)", use_container_width=True):
        try:
            cfg_for_core = copy.deepcopy(cfg2)
            cfg_for_core["simbolos"] = [cfg2.get("simbolos",[sym_choice])[0]]
            cfg_for_core.setdefault("estrategia", {})["tf"] = cfg2.get("estrategia",{}).get("tf", "15m")
            write_core_settings_json(cfg_for_core)
            st.success(f"✅ Guardado para el core: {CORE_SETTINGS_PATH}")
            st.caption("Reiniciá el proceso del bot para que tome la nueva config.")
        except Exception as e:
            st.error(f"❌ No se pudo escribir config/settings.json: {e}")

with cD:
    if st.button("▶️ Run Core (abrir CMD)", use_container_width=True):
        _fab_auto_export_after_run()

        try:
            core_script = str((ROOT / "core" / "core_actualizado.py").resolve())
            py_exec = sys.executable
            if os.name == "nt":
                cmd = f'start "" cmd /k "{py_exec}" "{core_script}"'
                subprocess.Popen(cmd, shell=True)
            else:
                subprocess.Popen([sys.executable, core_script])
            st.success("✅ Core lanzado en una nueva ventana de CMD.")
        except Exception as e:
            st.error(f"❌ No se pudo abrir la ventana CMD: {e}")



# =============================
# === SECCIÓN EXTRA: FABIAN ===
# Panel aditivo: múltiples símbolos + agregar manual,
# RR con sincronización, Guardar/Aplicar unificado y Run Core absoluto.
# No elimina nada de la UI original.
# =============================
try:
    import streamlit as _st_fab
    import json as _json_fab
    import subprocess as _subproc_fab
    import sys 
    from pathlib import Path as _Path_fab
    

    with _st_fab.expander("🛠️ Configuración rápida (símbolos, riesgo y RR) – Fabián", expanded=False):
        # Rutas (ajustar si es necesario)
        _ROOT_FAB = _Path_fab(r"C:\backtest_bibit_1to1")
        _SETTINGS_FAB = _ROOT_FAB / "settings.json"  # único JSON real (hard link con \config\settings.json)
        import sys  # <-- agregar este import cerca de los otros
        _PYTHON_EXE_FAB = _Path_fab(sys.executable)          # usa el mismo Python de la UI
        _CORE_PATH_FAB  = _ROOT_FAB / "core" / "core_actualizado.py" # deja esto igual


        def _load_settings_fab():
            cfg = {}
            if _SETTINGS_FAB.exists():
                try:
                    with open(_SETTINGS_FAB, "r", encoding="utf-8") as fh:
                        cfg = _json_fab.load(fh)
                except Exception as e:
                    _st_fab.error(f"Error leyendo {_SETTINGS_FAB}: {e}")
                    cfg = {}
            cfg.setdefault("simbolos", ["BTCUSDT","ETHUSDT","SOLUSDT"])
            cfg.setdefault("riesgo", {})
            cfg["riesgo"].setdefault("stop_pct", 1.0)
            cfg["riesgo"].setdefault("take_pct", 3.0)
            cfg["riesgo"].setdefault("relacion", "1:3")
            cfg["riesgo"].setdefault("riesgo_usdt", 10.0)
            cfg.setdefault("estrategia", {})
            cfg["estrategia"].setdefault("tf", cfg.get("timeframe", "30m"))
            cfg.setdefault("timeframe", cfg["estrategia"]["tf"])
            return cfg

        def _save_settings_fab(cfg):
            try:
                _SETTINGS_FAB.parent.mkdir(parents=True, exist_ok=True)
                with open(_SETTINGS_FAB, "w", encoding="utf-8") as fh:
                    _json_fab.dump(cfg, fh, ensure_ascii=False, indent=2)
            except Exception as e:
                _st_fab.error(f"Error guardando {_SETTINGS_FAB}: {e}")

        _cfg_fab = _load_settings_fab()

        # Símbolos múltiples + agregar manual
        _st_fab.subheader("Símbolos")
        _catalogo = [
            "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT",
            "ADAUSDT","DOGEUSDT","MATICUSDT"
        ]
        _sim_actuales = sorted(set([s.upper() for s in _cfg_fab.get("simbolos", [])]))
        _seleccion = _st_fab.multiselect(
            "Seleccioná uno o varios símbolos",
            options=sorted(set(_catalogo + _sim_actuales)),
            default=_sim_actuales
        )
        _c1,_c2 = _st_fab.columns([3,1])
        with _c1:
            _nuevo = _st_fab.text_input("Agregar símbolo manual (ej: ARBUSDT)").strip().upper()
        with _c2:
            if _st_fab.button("Agregar"):
                if _nuevo and _nuevo not in _seleccion:
                    _seleccion.append(_nuevo)
                    _st_fab.success(f"Agregado: {_nuevo}")
                elif _nuevo:
                    _st_fab.info(f"{_nuevo} ya está seleccionado.")

        # Persistir selección en session_state para que la use cfg2
        _st_fab.session_state["fab_symbols"] = sorted(set(_seleccion)) or ["ETHUSDT"]

        # Riesgo + RR con sincronización
        _st_fab.subheader("Riesgo / Relación")
        _col1,_col2,_col3 = _st_fab.columns(3)
        with _col1:
            _stop = _st_fab.slider("Stop (%)", min_value=0.2, max_value=5.0, step=0.1,
                                   value=float(_cfg_fab["riesgo"].get("stop_pct", 1.0)))
        with _col2:
            _rr_opts = ["1:2","1:3","1:4","1:5"]
            _rr_sel = _st_fab.radio("Relación (RR)", options=_rr_opts,
                                    index=_rr_opts.index(_cfg_fab["riesgo"].get("relacion","1:3")))
        with _col3:
            _r_usdt = _st_fab.number_input("Riesgo fijo (USDT)", min_value=1.0, max_value=1000.0, step=1.0,
                                           value=float(_cfg_fab["riesgo"].get("riesgo_usdt", 10.0)))

        _sync = _st_fab.checkbox("Sincronizar Take (%) con RR (TP = Stop × RR)", value=True)
        _take = float(_cfg_fab["riesgo"].get("take_pct", 3.0))
        if _sync:
            _take = round(_stop * int(_rr_sel.split(':')[1]), 2)
        else:
            _take = _st_fab.slider("Take (%)", min_value=0.5, max_value=20.0, step=0.1, value=_take)

        _st_fab.write(f"**Take (%) actual**: {_take}  |  **RR**: {_rr_sel}")

        # Guardar en session_state para que cfg2 lo tome
        _st_fab.session_state["fab_rr"] = _rr_sel
        _st_fab.session_state["fab_take_pct"] = float(_take)

        _sA,_sB = _st_fab.columns([1,1])
        with _sA:
            if _st_fab.button("💾 Guardar y aplicar (unificado)"):
                _cfg_fab["simbolos"] = _st_fab.session_state["fab_symbols"]
                _cfg_fab.setdefault("riesgo", {})
                _cfg_fab["riesgo"]["stop_pct"] = float(_stop)
                _cfg_fab["riesgo"]["take_pct"] = float(_take)
                _cfg_fab["riesgo"]["relacion"] = _rr_sel
                _cfg_fab["riesgo"]["riesgo_usdt"] = float(_r_usdt)
                # espejo timeframe por compatibilidad
                _cfg_fab.setdefault("estrategia", {})
                _cfg_fab["timeframe"] = _cfg_fab["estrategia"].get("tf", _cfg_fab.get("timeframe","30m"))
                _save_settings_fab(_cfg_fab)
                _st_fab.success(f"Config guardada en: {_SETTINGS_FAB}")
                _st_fab.info("Si el core estaba corriendo, reinicialo para tomar la nueva config.")

        with _sB:
            if _st_fab.button("▶️ Run Core (ruta absoluta)"):
                try:
                    if not _PYTHON_EXE_FAB.exists():
                        _st_fab.error(f"No encuentro Python en: {_PYTHON_EXE_FAB} (ajustá la ruta).")
                    elif not _CORE_PATH_FAB.exists():
                        _st_fab.error(f"No encuentro el core en: {_CORE_PATH_FAB} (ajustá la ruta).")
                    else:
                        _cmd = f'start "" cmd /k "{_PYTHON_EXE_FAB}" "{_CORE_PATH_FAB}"'
                        _subproc_fab.Popen(_cmd, shell=True)
                        _st_fab.success("Core lanzado en nueva consola.")
                except Exception as _e:
                    _st_fab.error(f"No pude lanzar el core: {_e}")
except Exception as _e_fab:
    # No romper la app si esta sección falla
    pass



# === FAB: Excel exporter with curve, config and comparator ===
import json as _json
import pandas as _pd
from pathlib import Path as _Path

def export_excel_completo(
    path_xlsx: str,
    df_trades: _pd.DataFrame,
    equity_df: _pd.DataFrame,
    settings_dict: dict,
    metrics_dict: dict | None = None,
    equity_prev_df: _pd.DataFrame | None = None,
) -> str:
    path = _Path(path_xlsx)
    path.parent.mkdir(parents=True, exist_ok=True)
    eq = equity_df.copy() if equity_df is not None else _pd.DataFrame(columns=["ts","equity"])
    if "ts" in eq.columns:
        eq["ts"] = _pd.to_datetime(eq["ts"])
    eq_prev = None
    if equity_prev_df is not None and not equity_prev_df.empty:
        eq_prev = equity_prev_df.copy()
        if "ts" in eq_prev.columns:
            eq_prev["ts"] = _pd.to_datetime(eq_prev["ts"])
    with _pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm") as writer:
        # Trades (+ PnL+/PnL- and totals)
        if df_trades is not None and not df_trades.empty:
            df_t = df_trades.copy()
            pnl_col = None
            for c in df_t.columns:
                if c.lower() in ("pnl", "pnl_usdt", "pnl_net", "pnl_neto", "pnl (usdt)"):
                    pnl_col = c
                    break
            if pnl_col is None and len([c for c in df_t.columns if "pnl" in c.lower()])>0:
                pnl_col = [c for c in df_t.columns if "pnl" in c.lower()][0]
            if pnl_col:
                df_t["PnL_pos"] = df_t[pnl_col].clip(lower=0)
                df_t["PnL_neg"] = df_t[pnl_col].clip(upper=0)
                total_row = {col: "" for col in df_t.columns}
                total_row[pnl_col] = df_t[pnl_col].sum()
                total_row["PnL_pos"] = df_t["PnL_pos"].sum()
                total_row["PnL_neg"] = df_t["PnL_neg"].sum()
                wins = (df_t[pnl_col] > 0).sum()
                losses = (df_t[pnl_col] <= 0).sum()
                total = len(df_t)
                total_row["TOTAL"] = "resumen"
                total_row["wins"] = wins
                total_row["losses"] = losses
                total_row["total_ops"] = total
                total_row["win_rate"] = round(100.0 * wins / total, 2) if total else 0.0
                total_row["loss_rate"] = round(100.0 * losses / total, 2) if total else 0.0
                df_t = _pd.concat([df_t, _pd.DataFrame([total_row])], ignore_index=True)
            df_t.to_excel(writer, sheet_name="Trades", index=False)
        # Curva
        if not eq.empty:
            eq.sort_values("ts", inplace=True)
            eq.to_excel(writer, sheet_name="Curva", index=False)
            wb  = writer.book
            ws  = writer.sheets["Curva"]
            chart = wb.add_chart({"type": "line"})
            last_row = len(eq) + 1
            chart.add_series({
                "name":       "Equity",
                "categories": ["Curva", 1, 0, last_row-1, 0],
                "values":     ["Curva", 1, 1, last_row-1, 1],
            })
            chart.set_title({"name": "Curva de equity"})
            chart.set_x_axis({"name": "Fecha"})
            chart.set_y_axis({"name": "Equity"})
            ws.insert_chart("D2", chart, {"x_offset": 10, "y_offset": 10})
        # Config usada
        if settings_dict:
            cfg_items = []
            def _flat(prefix, obj):
                if isinstance(obj, dict):
                    for k,v in obj.items():
                        _flat(f"{prefix}.{k}" if prefix else str(k), v)
                else:
                    cfg_items.append((prefix, _json.dumps(obj) if isinstance(obj, (list,dict)) else obj))
            _flat("", settings_dict)
            _pd.DataFrame(cfg_items, columns=["clave","valor"]).to_excel(writer, sheet_name="Config usada", index=False)
        # Metrics
        if metrics_dict:
            _pd.DataFrame(list(metrics_dict.items()), columns=["metric","value"]).to_excel(writer, sheet_name="Métricas", index=False)
        # Comparador
        if eq_prev is not None and not eq_prev.empty and not eq.empty:
            comp = eq_prev.merge(eq, on="ts", how="outer", suffixes=("_prev","_curr")).sort_values("ts")
            comp.to_excel(writer, sheet_name="Comparador", index=False)
            wb  = writer.book
            ws  = writer.sheets["Comparador"]
            chart2 = wb.add_chart({"type": "line"})
            last_row = len(comp) + 1
            chart2.add_series({
                "name":       "Equity (Anterior)",
                "categories": ["Comparador", 1, 0, last_row-1, 0],
                "values":     ["Comparador", 1, 1, last_row-1, 1],
            })
            chart2.add_series({
                "name":       "Equity (Actual)",
                "categories": ["Comparador", 1, 0, last_row-1, 0],
                "values":     ["Comparador", 1, 2, last_row-1, 2],
            })
            chart2.set_title({"name": "Comparador de curvas"})
            chart2.set_x_axis({"name": "Fecha"})
            chart2.set_y_axis({"name": "Equity"})
            ws.insert_chart("E2", chart2, {"x_offset": 10, "y_offset": 10})
    return str(path)



# === FAB: sanitizer to avoid duplicate riesgo blocks ===
def _sanitize_riesgo(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        return cfg
    r = cfg.get("riesgo")
    if isinstance(r, dict):
        cfg["riesgo"] = {
            "stop_pct": float(r.get("stop_pct", 1.0)),
            "take_pct": float(r.get("take_pct", 3.0)),
            "relacion": str(r.get("relacion", "1:3")),
            "riesgo_usdt": float(r.get("riesgo_usdt", 10.0)),
        }
    # remove shadow copies under other keys
    try:
        if isinstance(cfg.get("estrategia"), dict) and "riesgo" in cfg["estrategia"]:
            cfg["estrategia"].pop("riesgo", None)
    except Exception:
        pass
    return cfg



# === FAB: wrapper to call auto-export from your run block ===
def _fab_auto_export_after_run():
    import datetime
    from pathlib import Path
    try:
        # Update session curves
        try:
            st.session_state["equity_prev"]  = st.session_state.get("equity_curr")
            st.session_state["metrics_prev"] = st.session_state.get("metrics_curr")
        except Exception:
            pass
        # Expect equity_df, metrics, config_usada, df_trades in locals()
        eq = locals().get("equity_df", st.session_state.get("equity_curr"))
        if eq is not None:
            st.session_state["equity_curr"] = eq.copy()
        if isinstance(locals().get("metrics"), dict):
            st.session_state["metrics_curr"] = locals().get("metrics")
        if isinstance(locals().get("config_usada"), dict):
            st.session_state["last_config_used"] = locals().get("config_usada")
        out_dir = Path("out"); out_dir.mkdir(exist_ok=True, parents=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"backtest_{ts}.xlsx"
        export_excel_completo(
            path_xlsx=str(out_path),
            df_trades=locals().get("df_trades"),
            equity_df=st.session_state.get("equity_curr"),
            settings_dict=st.session_state.get("last_config_used") or {},
            metrics_dict=st.session_state.get("metrics_curr") or {},
            equity_prev_df=st.session_state.get("equity_prev"),
        )
        st.success(f"Excel auto-guardado: {out_path}")
    except Exception as _e_auto:
        st.warning(f"No se pudo auto-exportar Excel: {_e_auto}")
