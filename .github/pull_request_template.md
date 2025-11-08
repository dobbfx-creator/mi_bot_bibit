## Objetivo
<!-- Qué problema resuelve: partial y/o trailing -->

## Cambios claves
- [ ] Refactor de `trailing_base.py` (estado, activación, lock, buffer)
- [ ] Fix en `core/core.py` (llamadas a parcial y trailing en orden correcto)
- [ ] Test mínimo en `scripts/smoke_test.py` pasa en CI

## Reproducción
1. `python scripts/smoke_test.py`
2. `python backtest.py --use-fixed`
3. Verificar logs en `logs/*.log`

## Checklist
- [ ] Sin claves en el repo (.env local)
- [ ] `requirements.txt` actualizado
- [ ] `jules.yaml` actualizado
- [ ] Logs claros de partial / trailing
