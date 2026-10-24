import time
import os
import platform
import subprocess
import threading
from core import outcome
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
pyautogui = LazyModule("pyautogui")
pyperclip = LazyModule("pyperclip")


def controlar_discord_desktop(
    parameters, response=None, player=None, session_memory=None
) -> str:
    params = parameters or {}
    destino = params.get("destino", "").strip()
    mensagem = params.get("mensagem", "").strip()
    auto_enviar = params.get("auto_enviar", False)

    if not destino or not mensagem:
        return outcome.failed("discord_desktop", "Destino (canal, servidor ou contato) e mensagem são obrigatórios.")

    try:
        acao_voz = "enviando" if auto_enviar else "preparando"
        if player and hasattr(player, "speak"):
            threading.Thread(
                target=player.speak,
                args=(f"Deixa comigo, {acao_voz} a mensagem no Discord.",),
                daemon=True,
            ).start()

        # Abre o Discord via URI ou executável
        uri = "discord://"
        if platform.system() == "Windows":
            os.startfile(uri)
        elif platform.system() == "Darwin":
            subprocess.run(["open", uri])
        else:
            subprocess.run(["xdg-open", uri])

        time.sleep(4)  # Aguarda o app abrir e carregar

        if not (_PYAUTOGUI and _PYPERCLIP):
            return outcome.failed("discord_desktop", "PyAutoGUI ou Pyperclip não estão instalados.")

        hotkey_cmd = "command" if platform.system() == "Darwin" else "ctrl"

        # 1. Navegação rápida no Discord usando Ctrl+K (Quick Switcher)
        # Usamos a área de transferência para colar o destino com total precisão, evitando erros de digitação.
        pyperclip.copy(destino)
        time.sleep(0.3)
        
        pyautogui.hotkey(hotkey_cmd, "k")
        time.sleep(0.8)

        pyautogui.hotkey(hotkey_cmd, "v")
        time.sleep(1.0)  # Espera a busca popular os resultados

        pyautogui.press("enter")
        time.sleep(1.5)  # Espera entrar no canal ou chat privado

        # 2. Escrever a mensagem usando a Área de Transferência (Ctrl+V)
        pyperclip.copy(mensagem)
        time.sleep(0.5)

        pyautogui.hotkey(hotkey_cmd, "v")
        time.sleep(1.0)

        if auto_enviar:
            pyautogui.press("enter")
            return outcome.done("discord_desktop", info=f"Discord aberto e mensagem ENVIADA para {destino}.")
        else:
            return outcome.done("discord_desktop", info=f"Discord aberto e mensagem REDIGIDA para {destino}. Aguardando revisão física do usuário.")

    except Exception as e:
        return outcome.failed(
            "discord_desktop", f"Erro ao manipular o Discord Desktop: {str(e)}"
        )


TOOL = {
    "name": "discord_desktop",
    "description": (
        "Controla o aplicativo nativo do Discord Desktop. "
        "Permite entrar em servidores, canais específicos (#geral), DMs de usuários, "
        "colando o destino via Quick Switcher (Ctrl+K) e enviando mensagens com total precisão. "
        "Parâmetros: "
        "- 'destino': Nome do canal, servidor ou contato (ex: '#geral', 'Servidor de Jogos', 'NomeDoAmigo'). "
        "- 'mensagem': Texto exato da mensagem. "
        "- 'auto_enviar': True para enviar imediatamente, False apenas para redigir."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "destino": {
                "type": "STRING",
                "description": "Canal, servidor ou contato de destino (ex: '#geral', 'Amigo')",
            },
            "mensagem": {
                "type": "STRING",
                "description": "Texto da mensagem",
            },
            "auto_enviar": {
                "type": "BOOLEAN",
                "description": "True para apertar enter e enviar. False apenas para colar na caixa de texto.",
            },
        },
        "required": ["destino", "mensagem", "auto_enviar"],
    },
    "handler": controlar_discord_desktop,
}
