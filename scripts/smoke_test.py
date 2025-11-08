import sys, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def ok(name):
    print(f"[OK] {name}")

def main():
    try:
        import core
        ok("import core (paquete)")
    except Exception:
        try:
            import core.core as C
            ok("import core.core (módulo)")
        except Exception as e:
            print("[FAIL] import core/core.py")
            traceback.print_exc()
            raise

    try:
        import trailing_base as T
        ok("import trailing_base.py")
        # chequeo rápido de API esperada
        assert hasattr(T, "preparar_posicion")
        assert hasattr(T, "actualizar_trailing")
        ok("API trailing disponible")
    except Exception:
        print("[FAIL] trailing_base")
        traceback.print_exc()
        raise

    try:
        import run_scenarios as R
        ok("import run_scenarios.py")
        assert hasattr(R, "load_core")
        ok("API escenarios disponible")
    except Exception:
        print("[FAIL] run_scenarios")
        traceback.print_exc()
        raise

    print("SMOKE_TEST=OK")

if __name__ == "__main__":
    main()
