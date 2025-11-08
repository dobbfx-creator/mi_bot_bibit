# core_actualizado.py (versión completa)
# - Carga credenciales desde .env (raíz)
# - Mantiene filtro de sesión (session_filter)
# - Mantiene map_new_to_legacy() para compatibilidad
# - Sincroniza settings.json (raíz) -> config/settings.json
# - Lanza el core legacy (core.py)
#
# Ubicaciones esperadas en tu PC:
#   C:\backtest_bibit_1to1\.env
#   C:\backtest_bibit_1to1\settings.json           (UI escribe aquí)
#   C:\backtest_bibit_1to1\config\settings.json     (core lee aquí)
#   C:\backtest_bibit_1to1\core\core.py             (motor estable)

from pathlib import Path
from datetime import datetime, timezone
import os, json, shutil, importlib
# --- Fallback robusto para cargar .env ---
from pathlib import Path
try:
    from dotenv import load_dotenv  # ya lo usás en el launcher
    # Si todavía no se cargaron las claves, probá en las rutas del proyecto:
    if not (os.getenv("BYBIT_API_KEY") and os.getenv("BYBIT_API_SECRET")):
        here = Path(__file__).resolve().parent          # si el file está en core/
        root = here if (here / "config" / "settings.json").exists() else here.parent  # raíz del proyecto
        candidates = [root / ".env", here / ".env"]
        for envp in candidates:
            if envp.exists():
                load_dotenv(envp)
                print(f"[INFO] .env cargado -> {envp}")
                break
except Exception as _e:
    print(f"[ADVERTENCIA] Carga fallback .env falló: {_e}")
# --- Fin fallback ---

# --- FIX: asegurar que se pueda importar core, mensajeria, trailing, etc ---
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
# --- FIN FIX ---

# --- Rutas ---
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
NEW_SETTINGS = ROOT / "settings.json"              # lo escribe la UI
LEGACY_SETTINGS = CONFIG_DIR / "settings.json"     # lo lee el core viejo

# --- Cargar .env ANTES de importar core ---
def _load_env():
    try:
        from dotenv import load_dotenv
    except Exception as e:
        print(f"[ADVERTENCIA] python-dotenv no disponible: {e}")
        return
    env_file = ROOT / ".env"
    if not env_file.exists():
        print(f"[ADVERTENCIA] No existe .env en {env_file}")
    load_dotenv(env_file)

def _require_env(keys):
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Faltan variables en .env: {missing}. Verificá {ROOT / '.env'}")

# --- Tiempo ---
def _utcnow():
    return datetime.now(timezone.utc)

def _ts():
    return _utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

# --- I/O JSON ---
def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def _write_json(path: Path, data: dict):
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(".json.bak"))
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

# --- Filtro de sesión ---
def is_blocked_by_session(cfg: dict) -> bool:
    sess = cfg.get("session_filter", {})
    if not isinstance(sess, dict) or not sess.get("enabled", False):
        return False
    blocked_hours = set(sess.get("blocked_hours", []))
    blocked_weekdays = set(sess.get("blocked_weekdays", []))
    now = _utcnow()
    if now.weekday() in blocked_weekdays:
        return True
    if now.hour in blocked_hours:
        return True
    return False

# --- Bridge nuevo -> legacy ---
def map_new_to_legacy(cfg_new: dict) -> dict:
    """
    Compatibilidad suave: copiamos todo y aplicamos alias en lo que sabemos que el core consume.
    Agregá aquí mapeos adicionales si tu core espera nombres distintos.
    """
    cfg_legacy = dict(cfg_new)  # copia 1:1

    # Alias de timeframe (si el core espera "timeframe" plano)
    estr = cfg_new.get("estrategia", {})
    if isinstance(estr, dict) and estr.get("tf"):
        cfg_legacy.setdefault("timeframe", estr["tf"])

    # Trailing guard (ej. desde "auto_trailing.guard" a "trailing.*")
    auto_tr = cfg_new.get("auto_trailing", {}) or {}
    guard = auto_tr.get("guard", {}) or {}
    tr = cfg_legacy.setdefault("trailing", {})
    if "min_mfe_to_trail_pct" in guard:
        tr.setdefault("activar_pct", guard.get("min_mfe_to_trail_pct"))
    if "min_mfe_to_be_atr" in guard:
        tr.setdefault("be_atr_mult", guard.get("min_mfe_to_be_atr"))
    if "be_lock_atr" in guard:
        tr.setdefault("lock_atr_mult", guard.get("be_lock_atr"))

    # Ejemplos de banderas que tu core ya entiende (si vienen anidadas en cfg_new, podés aplanarlas aquí):
    # for k in ["usar_rsi", "usar_adx", "usar_ema200", "usar_bb_width", "usar_volumen"]:
    #     if k in cfg_new:
    #         cfg_legacy.setdefault(k, cfg_new[k])

    return cfg

# --- Sincronizar settings y lanzar core ---
def _sync_settings_new_to_legacy():
    from pathlib import Path
    ROOT = (lambda p: (p.parent if (p.parent / "config" / "settings.json").exists() else p.parent.parent))(Path(__file__).resolve())
    settings_root = root / "settings.json"
    settings_cfg  = root / "config" / "settings.json"

    # Preferí el de \config si existe; si no, usá el de raíz por compatibilidad
    if settings_cfg.exists():
        src = settings_cfg
    elif settings_root.exists():
        src = settings_root
    else:
        raise FileNotFoundError(f"No existe {settings_root} ni {settings_cfg}. Guardá primero desde la UI o crea config/settings.json.")

    # Si estás copiando a legacy, mantené compatibilidad (opcional)
    dst = src  # ya no copiamos, tomamos directo el json "bueno"

    # Cargá y devolvé el dict
    import json
    cfg = json.loads(src.read_text(encoding="utf-8"))
    print(f"[{__import__('time').strftime('%Y-%m-%d %H:%M:%S UTC', __import__('time').gmtime())}] Config leída -> {src}")
    return cfg

def main():
    # 1) Entorno listo (.env + claves mínimas)
    _load_env()
    _require_env(["BYBIT_API_KEY", "BYBIT_API_SECRET"])  # agregá más si querés forzar TELEGRAM_*

    # 2) Sincronizar config
    cfg = _sync_settings_new_to_legacy()
    if cfg is None:
        return  # bloqueado por sesión

    # 3) Importar y lanzar core legacy (core.py en carpeta "core")
    legacy_core = importlib.import_module("core")
    if hasattr(legacy_core, "main"):
        print(f"[{_ts()}] Iniciando core legacy...")
        return legacy_core.main()
    else:
        print("[ADVERTENCIA] core.py no expone main(); importado igualmente.")
        return None

if __name__ == "__main__":
    main()



