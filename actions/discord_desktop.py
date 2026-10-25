import time
import os
import platform
import subprocess
import threading
from core import outcome
from core import appidentity
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
pyautogui = LazyModule("pyautogui")
pyperclip = LazyModule("pyperclip")


_last_sent_cache = {}


def controlar_discord_desktop(
    parameters, response=None, player=None, session_memory=None
) -> str:
    params = parameters or {}
    destino = params.get("destino", "").strip()
    mensagem = params.get("mensagem", "").strip()
    auto_enviar = params.get("auto_enviar", False)

    if not destino or not mensagem:
        return outcome.failed("discord_desktop", "Destino (canal, servidor ou contato) e mensagem são obrigatórios.")

    # Idempotency check: prevent duplicate sending within 10 seconds
    now = time.time()
    cache_key = (destino.lower(), mensagem)
    if cache_key in _last_sent_cache and (now - _last_sent_cache[cache_key]) < 10.0:
        return outcome.done("discord_desktop", info=f"Mensagem para {destino} já foi enviada recentemente (evitado envio duplicado).")
    _last_sent_cache[cache_key] = now

    try:
        acao_voz = "enviando" if auto_enviar else "preparando"
        if player and hasattr(player, "speak"):
            threading.Thread(
                target=player.speak,
                args=(f"Deixa comigo, {acao_voz} a mensagem no Discord.",),
                daemon=True,
            ).start()

        before = appidentity.snapshot()

        # 0. Check if Discord is already running and focus it!
        existing = appidentity.running("Discord")
        focused = False
        if existing:
            for candidate in existing[:8]:
                if appidentity.focus(candidate):
                    focused = True
                    break

        if not focused:
            # 1. Official Windows Discord Update.exe --processStart Discord.exe
            try:
                update_exe = os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")
                if os.path.exists(update_exe):
                    subprocess.Popen([update_exe, "--processStart", "Discord.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

            # 2. URI scheme
            try:
                if platform.system() == "Windows":
                    os.startfile("discord://")
                elif platform.system() == "Darwin":
                    subprocess.run(["open", "discord://"])
                else:
                    subprocess.run(["xdg-open", "discord://"])
            except Exception:
                pass

            # Wait to see if Discord appeared
            appeared = appidentity.wait_for_launch("Discord", before, timeout=4.0)

            # 3. Fallback: Start Menu search typing + Enter
            if appeared is None and _PYAUTOGUI:
                try:
                    if platform.system() == "Darwin":
                        pyautogui.hotkey("command", "space")
                    else:
                        pyautogui.press("win")
                    time.sleep(0.6)
                    pyautogui.write("Discord", interval=0.05)
                    time.sleep(0.6)
                    pyautogui.press("enter")
                except Exception:
                    pass
                appeared = appidentity.wait_for_launch("Discord", before, timeout=6.0)

            # Focus after launch
            existing = appidentity.running("Discord")
            if existing:
                for candidate in existing[:8]:
                    if appidentity.focus(candidate):
                        break

        time.sleep(2.0)  # Extra buffer for Discord UI to load fully

        if not (_PYAUTOGUI and _PYPERCLIP):
            return outcome.failed("discord_desktop", "PyAutoGUI ou Pyperclip não estão instalados.")

        hotkey_cmd = "command" if platform.system() == "Darwin" else "ctrl"

        # 1. Navegação rápida no Discord usando Ctrl+K (Quick Switcher) para encontrar servidores, canais (#geral) ou contatos
        pyperclip.copy(destino)
        time.sleep(0.3)

        pyautogui.hotkey(hotkey_cmd, "k")
        time.sleep(0.8)

        pyautogui.hotkey(hotkey_cmd, "v")
        time.sleep(1.2)  # Espera a busca popular os resultados

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
        "Permite encontrar e enviar mensagens em QUALQUER servidor do Discord, canais específicos (ex: '#geral', '#anúncios', 'geral'), "
        "ou DMs de amigos/contatos. "
        "Usa o Quick Switcher (Ctrl+K) do Discord para buscar o servidor, canal ou contato exato que o usuário pedir. "
        "Parâmetros: "
        "- 'destino': Nome exato do servidor, canal (ex: '#geral', 'geral') ou contato/amigo. "
        "- 'mensagem': Texto exato da mensagem. "
        "- 'auto_enviar': True para enviar imediatamente, False apenas para redigir. "
        "Call this tool exactly once per request. Never repeat or call in a loop."
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
