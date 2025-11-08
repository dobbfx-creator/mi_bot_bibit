# -*- coding: utf-8 -*-
import sys, json, glob, argparse, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuso funciones del runner para ejecutar un escenario desde un archivo
from tests.run_scenarios import load_core, run_scenario
# Adaptador para tu settings real
from tests.compat_cfg import load_settings, snapshot_for_runner

TMP_DIR = ROOT / "tests" / "scenarios_tmp"

def _list_jsons(folder: Path):
    return sorted(glob.glob(str(folder / "*.json")))

def _prepare_for_runner(src_path: Path) -> Path:
    """
    Lee el escenario y, si tiene 'precios' (nuestro formato normalizado),
    genera un archivo temporal con la clave que el runner espera: 'precio_sequence'.
    Devuelve la ruta del archivo que se debe pasar a run_scenario.
    """
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Si ya trae la clave vieja que espera el runner, devolvemos tal cual
    if "precio_sequence" in data:
        return src_path

    seq = None
    # aceptar varios nombres, priorizamos 'precios'
    for k in ("precios", "prices", "close", "closes", "serie", "series", "seq"):
        if k in data:
            seq = data[k]
            break

    if seq is None:
        # no hay serie; devolvemos el original (luego fallará con KeyError “esperado”)
        return src_path

    # Creamos copia temporal con la clave esperada por el runner
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TMP_DIR / src_path.name
    patched = dict(data)
    patched["precio_sequence"] = seq
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(patched, f, ensure_ascii=False, indent=2)
    return out_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=str(ROOT / "tests" / "scenarios"),
                        help="Carpeta con escenarios .json")
    parser.add_argument("--salida", default=str(ROOT / "tests" / "salida"),
                        help="Carpeta de salida")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--use-fixed", action="store_true", help="Usar escenarios normalizados (tests/scenarios_fixed)")
    args = parser.parse_args()

    scenarios_dir = Path(args.scenarios)
    if args.use_fixed:
        scenarios_dir = ROOT / "tests" / "scenarios_fixed"

    # Limpieza de temporales
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR, ignore_errors=True)

    # 1) Core + settings reales
    C = load_core()
    cfg = load_settings(ROOT)
    snap = snapshot_for_runner(cfg)

    files = _list_jsons(scenarios_dir)
    if not files:
        print("No se encontraron escenarios en:", scenarios_dir)
        print("Tip: normalizá con  python tests\\fix_scenarios.py  y corré con  --use-fixed")
        return

    results = []
    for path in files:
        p = Path(path)
        # Adaptamos clave 'precios' -> 'precio_sequence' si hace falta
        patched_path = _prepare_for_runner(p)
        r = run_scenario(C, cfg, str(patched_path))
        results.append(r)

    ok = sum(1 for r in results if r.get("passed"))
    total = len(results)
    print(f"Resultados: {ok}/{total} PASSED")
    for r in results:
        name = r.get("name")
        passed = r.get("passed")
        seq_len = len(r.get("seq") or [])
        print(f"- {name}: {'OK' if passed else 'FAIL'} (expected={r.get('expected_index')}, actual={r.get('actual_index')})")
        print(f"  cfg → take_pct={snap.get('take_pct')}  relacion={snap.get('relacion')}  at_R={snap.get('at_R')}  paso_pct={snap.get('paso_pct')}  target={snap.get('target')}")
        print(f"  first_trigger_price={r.get('first_trigger_price')}  seq_len={seq_len}")

    if args.report:
        out_dir = Path(args.salida); out_dir.mkdir(parents=True, exist_ok=True)
        outj = out_dir / "report.json"; outt = out_dir / "report.txt"
        with open(outj, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        with open(outt, "w", encoding="utf-8") as f:
            f.write(f"Resultados: {ok}/{total} PASSED\n")
            for r in results:
                f.write(f"- {r['name']}: {'OK' if r.get('passed') else 'FAIL'} (expected={r.get('expected_index')}, actual={r.get('actual_index')})\n")
                f.write(f"  cfg → take_pct={snap.get('take_pct')}  relacion={snap.get('relacion')}  at_R={snap.get('at_R')}  paso_pct={snap.get('paso_pct')}  target={snap.get('target')}\n")
                f.write(f"  first_trigger_price={r.get('first_trigger_price')}  seq_len={len(r.get('seq') or [])}\n")
        print("Reportes escritos:", outj, "y", outt)

if __name__ == "__main__":
    main()
