# -*- coding: utf-8 -*-
import os, sys, json, time, types, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent  # asumimos que el repo está por encima
sys.path.insert(0, str(ROOT))

captured = []

def _install_patch():
    """
    Parchea mensajeria.telegram.enviar_mensaje para capturar el texto
    sin pegarle a Telegram real.
    """
    import mensajeria.telegram as tg

    def fake_send(cfg, texto: str):
        captured.append({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tipo": "sendMessage",
            "texto": str(texto),
        })
        # NO llama a la red

    tg.enviar_mensaje = fake_send

def _dump_outputs(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    # messages.json
    with open(outdir/"messages.json", "w", encoding="utf-8") as fh:
        json.dump(captured, fh, ensure_ascii=False, indent=2)
    # messages.txt
    with open(outdir/"messages.txt", "w", encoding="utf-8") as fh:
        for i, m in enumerate(captured, 1):
            fh.write(f"[{i}] {m['ts']} · {m['tipo']}\n{m['texto']}\n")
            fh.write("-"*60 + "\n")
    # resumen.json
    resumen = {}
    for m in captured:
        k = m.get("tipo", "sendMessage")
        resumen[k] = resumen.get(k, 0) + 1
    with open(outdir/"resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)

def main():
    # 1) preparar entorno y parche
    _install_patch()

    # 2) cfg mínimo con telegram.enabled=True (no pega a red igual, está parcheado)
    cfg = {
        "telegram": {"enabled": True, "bot_token": "X", "chat_id": "Y"},
        "notify": {"partials": True, "trailing": True}
    }

    # 3) importar utilidades de formato y notificador
    from mensajeria import formatos
    from mensajeria import notifier

    # 4) escenarios (agregamos más cuando quieras)
    escenarios = []

    # Heartbeat dummy (core manda un texto; acá lo simulamos)
    heartbeat_txt = (
        "Fabi bot BiBIT:\n"
        "🔄 HEARTBEAT\n"
        "Capital total: 49,113.55 USDT\n"
        "Hora: 18:32\n\n"
        "Estado de los pares:\n\n"
        "Total de órdenes ejecutadas en 24h: 29"
    )
    escenarios.append(("HEARTBEAT", lambda: notifier.safe_send(cfg, heartbeat_txt)))

    # Parcial ejecutado
    escenarios.append((
        "PARCIAL",
        lambda: notifier.parcial(
            cfg=cfg, simbolo="BTCUSDT", is_long=True, fraction=0.5,
            pnl_usdt=12.34, qty_restante=0.0025, precio_ejecucion=108000.0, at_r=0.5
        )
    ))

    # Cierre por trailing
    escenarios.append((
        "TRAILING_CLOSE",
        lambda: notifier.trailing_close(
            cfg=cfg, simbolo="ETHUSDT", is_long=True,
            pnl_usdt=25.67, precio_cierre=4013.1, distancia_pct=0.42
        )
    ))

    # 5) ejecutar
    for nombre, fn in escenarios:
        try:
            fn()
        except Exception as e:
            captured.append({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tipo": "ERROR",
                "texto": f"{nombre} lanzó excepción: {e}"
            })

    # 6) volcar archivos
    _dump_outputs(pathlib.Path(__file__).resolve().parent / "salida")
    print("OK · Mensajes capturados:", len(captured))

if __name__ == "__main__":
    main()
