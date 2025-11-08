import os
import json
import urllib.request
import urllib.parse 

def esta_habilitado(cfg: dict) -> bool:
    return bool(cfg.get("telegram", {}).get("enabled", False))

def enviar_mensaje(cfg: dict, texto: str) -> None:
    if not esta_habilitado(cfg): 
        return
    token = cfg["telegram"]["bot_token"]
    chat_id = cfg["telegram"]["chat_id"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": texto}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as _:
        pass

# Compat: core puede pedir enviar_mensaje_raw; delegamos al normal.
def enviar_mensaje_raw(cfg: dict, texto: str) -> bool:
    try:
        enviar_mensaje(cfg, texto)
        return True
    except Exception:
        return False
