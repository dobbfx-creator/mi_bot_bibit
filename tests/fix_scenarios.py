# -*- coding: utf-8 -*-
import json, glob
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "tests" / "scenarios"
DST = PROJECT / "tests" / "scenarios_fixed"
DST.mkdir(parents=True, exist_ok=True)

# Nombres aceptados para la serie de precios → normalizamos a 'precios'
PRICE_KEYS = ["precios", "precio_sequence", "prices", "close", "closes", "serie", "series", "seq"]
ENTRY_KEYS = ["entry", "entrada", "precio_entrada"]

def _to_float_list(seq):
    out = []
    for x in seq:
        if isinstance(x, (int, float)):
            out.append(float(x))
        else:
            s = str(x).strip().replace(",", ".")
            out.append(float(s))
    return out

def normalize_one(path: Path) -> Path:
    with open(path, "r", encoding="utf-8") as f:
        scn = json.load(f)

    # entry
    entry = None
    for k in ENTRY_KEYS:
        if k in scn:
            entry = scn[k]; break
    if entry is None:
        raise ValueError(f"{path.name}: falta 'entry'/'entrada'")

    try:
        entry = float(str(entry).replace(",", "."))
    except Exception:
        raise ValueError(f"{path.name}: 'entry' inválido: {entry}")

    # precios
    seq = None
    for k in PRICE_KEYS:
        if k in scn:
            seq = scn[k]; break
    if seq is None:
        raise ValueError(f"{path.name}: falta array de precios (precios/precio_sequence/prices/close/...)")

    seq = _to_float_list(seq)
    if not seq:
        raise ValueError(f"{path.name}: array de precios vacío")

    # Ensamblar escenario NORMALIZADO
    norm = {
        "name": scn.get("name", path.stem),
        "side": scn.get("side"),
        "entry": entry,
        "precios": seq
    }
    # Conservamos expectativas si existen
    for key in ("expect_partial_at_index", "expect_activation_at_index", "expect_close_at_index"):
        if key in scn: norm[key] = scn[key]

    out = DST / path.name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(norm, f, ensure_ascii=False, indent=2)
    return out

def main():
    files = sorted(glob.glob(str(SRC / "*.json")))
    if not files:
        print("No hay escenarios en:", SRC); return
    ok, fail = 0, 0
    for fp in files:
        p = Path(fp)
        try:
            out = normalize_one(p)
            print(f"OK  -> {p.name}  =>  {out.relative_to(PROJECT)}")
            ok += 1
        except Exception as e:
            print(f"FAIL -> {p.name}  ({e})")
            fail += 1
    print(f"Listo. Normalizados: {ok}, con error: {fail}")

if __name__ == "__main__":
    main()
