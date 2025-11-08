TESTS TRAILING (1:1 con tu settings.json actual):
- Usa activar_pct y min_mfe_to_trail_pct del JSON (umbral = el MAYOR de ambos).
- Con be_atr_mult=0.0, bloquea a Break-Even al activarse (stop = entry).
- Marca cierre cuando el precio retrocede al BE (este harness valida umbral y cierre básico).

Cómo correr:
    cd C:\backtest_bibit_1to1\tests_trailing
    python run_trailing_tests.py --report
