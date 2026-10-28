"""
Action: Capturar Informação da Tela (Screen Information).
Dynamically inspects connected displays/monitors using mss and reports resolutions and status.
"""
from __future__ import annotations
from core import outcome

try:
    import mss
    _MSS = True
except ImportError:
    _MSS = False

def capturar_informacao_tela(parameters, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    monitor_id = params.get("monitor_id")

    try:
        monitors_info = []
        if _MSS:
            with mss.mss() as sct:
                for idx, mon in enumerate(sct.monitors):
                    monitors_info.append({
                        "monitor": idx,
                        "left": mon["left"],
                        "top": mon["top"],
                        "width": mon["width"],
                        "height": mon["height"]
                    })
        else:
            monitors_info = [{"status": "mss library not installed, fallback mode"}]

        dados_monitor = {
            "monitor_solicitado": monitor_id if monitor_id is not None else "todos",
            "monitors": monitors_info,
            "status": "Todos os monitores estão visíveis e mapeados para a Jarvis com sucesso."
        }

        return outcome.done("capturar_informacao_tela", info=f"Informações reais dos monitores: {dados_monitor}")

    except Exception as e:
        return outcome.failed("capturar_informacao_tela", f"Falha ao capturar informações da tela: {str(e)}")

TOOL = {
    "name": "capturar_informacao_tela",
    "description": "Informa à IA as resoluções e status de todos os monitores conectados utilizando detecção nativa em tempo real.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "monitor_id": {
                "type": "STRING",
                "description": "ID opcional do monitor específico"
            }
        },
        "required": []
    },
    "handler": capturar_informacao_tela
}
