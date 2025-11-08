import os, sys, json, glob, argparse
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CFG_PATH = PROJECT / "config" / "settings.json"

def load_cfg():
    with open(CFG_PATH, "r", encoding="utf-8") as f: 
        return json.load(f)

def trailing_params(cfg):
    t_cfg = cfg.get("trailing", {}) or {}
    auto   = cfg.get("auto_trailing", {}) or {}
    guard  = auto.get("guard", {}) if isinstance(auto, dict) else {}
    activar_pct = float(t_cfg.get("activar_pct", 0.0))
    min_mfe_pct = float(guard.get("min_mfe_to_trail_pct", activar_pct))
    be_atr_mult = float(t_cfg.get("be_atr_mult", 0.0))
    lock_atr_mult = float(t_cfg.get("lock_atr_mult", 0.0))
    return {
        "activar_pct": activar_pct,
        "min_mfe_to_trail_pct": min_mfe_pct,
        "be_atr_mult": be_atr_mult,
        "lock_atr_mult": lock_atr_mult
    }

def _pct_change(from_px, to_px):
    return (to_px - from_px) / from_px * 100.0

def simulate_trailing(entry, prices, side, params):
    s = str(side).upper()
    is_long = "LONG" in s
    trigger_pct = max(params["activar_pct"], params["min_mfe_to_trail_pct"])

    activated_index = None
    stop = None

    for i, px in enumerate(prices):
        mfe_pct = _pct_change(entry, px) if is_long else _pct_change(px, entry)
        if activated_index is None and mfe_pct >= trigger_pct:
            activated_index = i
            if params["be_atr_mult"] == 0.0:
                stop = entry
            else:
                stop = entry
        if activated_index is not None:
            if is_long and px <= stop:
                return {"activated_index": activated_index, "closed_index": i, "closed_price": px}
            if (not is_long) and px >= stop:
                return {"activated_index": activated_index, "closed_index": i, "closed_price": px}
    return {"activated_index": activated_index, "closed_index": None, "closed_price": None}

def side_txt(side):
    return "COMPRA (LONG)" if "LONG" in str(side).upper() else "VENTA (SHORT)"

def run_scenario(cfg, scenario_path):
    with open(scenario_path, "r", encoding="utf-8") as f:
        scn = json.load(f)
    name = scn.get("name", Path(scenario_path).name)
    entry = float(scn["entry"])
    seq = list(map(float, scn["precio_sequence"]))
    side = side_txt(scn["side"])
    params = trailing_params(cfg)

    res = simulate_trailing(entry, seq, side, params)
    exp_act = scn.get("expect_activation_at_index", None)
    exp_cls = scn.get("expect_close_at_index", None)

    passed = True
    if exp_act is not None: passed &= (res["activated_index"] == exp_act)
    if exp_cls is not None: passed &= (res["closed_index"] == exp_cls)

    return {
        "name": name,
        "entry": entry,
        "side": side,
        "params": params,
        "sequence": seq,
        "result": res,
        "expected_activation_at_index": exp_act,
        "expected_close_at_index": exp_cls,
        "passed": bool(passed)
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    cfg = load_cfg()
    scen_dir = Path(__file__).resolve().parent / "scenarios"
    files = sorted(glob.glob(str(scen_dir / "*.json")))

    results = [run_scenario(cfg, p) for p in files]
    ok = sum(1 for r in results if r["passed"]); total = len(results)

    print(f"TRAILING: {ok}/{total} PASSED")
    for r in results:
        print(f"- {r['name']}: {'OK' if r['passed'] else 'FAIL'}  "
              f"(act={r['result']['activated_index']} exp={r.get('expected_activation_at_index')}, "
              f"close={r['result']['closed_index']} exp={r.get('expected_close_at_index')})")
        pr = r["params"]
        print(f"  params → activar_pct={pr['activar_pct']}  min_mfe_to_trail_pct={pr['min_mfe_to_trail_pct']}  be_atr_mult={pr['be_atr_mult']}  lock_atr_mult={pr['lock_atr_mult']}")

    if args.report:
        outj = Path(__file__).resolve().parent / "report_trailing.json"
        outt = Path(__file__).resolve().parent / "report_trailing.txt"
        with open(outj, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        with open(outt, "w", encoding="utf-8") as f:
            f.write(f"TRAILING: {ok}/{total} PASSED\n")
            for r in results:
                f.write(f"- {r['name']}: {'OK' if r['passed'] else 'FAIL'}  (act={r['result']['activated_index']} exp={r.get('expected_activation_at_index')}, close={r['result']['closed_index']} exp={r.get('expected_close_at_index')})\n")
                pr = r["params"]
                f.write(f"  params → activar_pct={pr['activar_pct']}  min_mfe_to_trail_pct={pr['min_mfe_to_trail_pct']}  be_atr_mult={pr['be_atr_mult']}  lock_atr_mult={pr['lock_atr_mult']}\n")
        print("Reportes escritos:", outj, "y", outt)

if __name__ == "__main__": main()
