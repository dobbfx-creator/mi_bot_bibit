import os, sys, json, glob, argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path: sys.path.insert(0, str(PROJECT))

import importlib

def load_core():
    try:
        import core.core as C
        importlib.reload(C)
        return C
    except Exception as e:
        print("ERROR: No pude importar core.core ->", e); raise

def load_cfg():
    cfg_path = PROJECT / "config" / "settings.json"
    with open(cfg_path, "r", encoding="utf-8") as f: return json.load(f)

def _parse_relacion(rel):
    try:
        if isinstance(rel, (int, float)): return float(rel) if rel else 3.0
        s = str(rel).strip()
        if not s: return 3.0
        if ":" in s or "-" in s:
            sep = ":" if ":" in s else "-"
            a, b = [p.strip() for p in s.split(sep, 1)]
            num, den = float(b), float(a)
            return (num/den) if den!=0 else 3.0
        return float(s)
    except Exception:
        return 3.0

def get_keys(cfg):
    take = float(cfg["riesgo"]["take_pct"])
    rel  = _parse_relacion(cfg["riesgo"].get("relacion", 3.0)) or 3.0
    atR  = None
    p = cfg.get("partials", {})
    if isinstance(p, dict) and "at_R" in p: atR = float(p["at_R"])
    if atR is None:
        p2 = cfg.get("parcial", {})
        if isinstance(p2, dict) and "at_r" in p2: atR = float(p2["at_r"])
    if atR is None: atR = 0.5
    paso = (take/rel) * atR
    return take, rel, atR, paso

def side_txt(side):
    s = str(side).upper()
    return "COMPRA (LONG)" if "LONG" in s else "VENTA (SHORT)"

def run_scenario(C, cfg, scenario_path):
    with open(scenario_path, "r", encoding="utf-8") as f: scn = json.load(f)
        name = scn.get("name", Path(scenario_path).name)

    # Entrada
    entry = float(str(scn.get("entry", scn.get("entrada"))).replace(",", "."))

    # Serie de precios: aceptar 'precios' y 'precio_sequence', más alias
    seq_raw = None
    for k in ("precios", "precio_sequence", "prices", "close", "closes", "serie", "series", "seq"):
        if k in scn:
            seq_raw = scn[k]
            break
    if not seq_raw:
        raise KeyError("No se encontró serie de precios en el escenario (precios/precio_sequence/...)")

    # Normalizar a floats (soporta strings y comas decimales)
    def _to_floats(xs):
        out = []
        for x in xs:
            if isinstance(x, (int, float)):
                out.append(float(x))
            else:
                s = str(x).strip().replace(",", ".")
                out.append(float(s))
        return out

    seq = _to_floats(seq_raw)


    take, rel, atR, paso = get_keys(cfg)
    if not hasattr(C, "_alcanzo_objetivo_parcial"):
        return {"name": name, "error": "core._alcanzo_objetivo_parcial no existe"}

    # Calculamos target teórico:
    if "LONG" in stxt:
        target = entry * (1 + paso/100.0)
    else:
        target = entry * (1 - paso/100.0)

    triggered_index = None
    first_px = None
    for i, px in enumerate(seq):
        ok = C._alcanzo_objetivo_parcial(entry, px, stxt, cfg)
        if ok and triggered_index is None:
            triggered_index = i
            first_px = px

    expected = scn.get("expect_partial_at_index")
    passed = (triggered_index == expected)
    return {
        "name": name,
        "entry": entry,
        "side": stxt,
        "expected_index": expected,
        "actual_index": triggered_index,
        "first_trigger_price": first_px,
        "cfg_snapshot": {"take_pct": take, "relacion": rel, "at_R": atR, "paso_pct": paso, "target_teorico": target},
        "seq": seq,
        "passed": bool(passed)
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    C = load_core()
    cfg = load_cfg()
    base = Path(__file__).resolve().parent / "scenarios"
    files = sorted(glob.glob(str(base / "*.json")))
    results = [run_scenario(C, cfg, p) for p in files]

    ok = sum(1 for r in results if r.get("passed")); total = len(results)
    print(f"Resultados: {ok}/{total} PASSED")
    for r in results:
        print(f"- {r['name']}: {'OK' if r.get('passed') else 'FAIL'} (expected={r.get('expected_index')}, actual={r.get('actual_index')})")
        snap = r.get("cfg_snapshot", {})
        print(f"  cfg → take_pct={snap.get('take_pct')}  relacion={snap.get('relacion')}  at_R={snap.get('at_R')}  paso_pct={snap.get('paso_pct')}  target={snap.get('target_teorico')}")
        print(f"  first_trigger_price={r.get('first_trigger_price')}  seq={r.get('seq')}")

    if args.report:
        outj = Path(__file__).resolve().parent / "report.json"
        outt = Path(__file__).resolve().parent / "report.txt"
        with open(outj, "w", encoding="utf-8") as f: json.dump(results, f, indent=2, ensure_ascii=False)
        with open(outt, "w", encoding="utf-8") as f:
            f.write(f"Resultados: {ok}/{total} PASSED\n")
            for r in results:
                f.write(f"- {r['name']}: {'OK' if r.get('passed') else 'FAIL'} (expected={r.get('expected_index')}, actual={r.get('actual_index')})\n")
                snap = r.get("cfg_snapshot", {})
                f.write(f"  cfg → take_pct={snap.get('take_pct')}  relacion={snap.get('relacion')}  at_R={snap.get('at_R')}  paso_pct={snap.get('paso_pct')}  target={snap.get('target_teorico')}\n")
                f.write(f"  first_trigger_price={r.get('first_trigger_price')}  seq={r.get('seq')}\n")
        print("Reportes escritos:", outj, "y", outt)

if __name__ == "__main__": main()
