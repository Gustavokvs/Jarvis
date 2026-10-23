import sys
import time
import threading
from core import outcome
from core.lazyimport import LazyModule, installed

# Carrega as bibliotecas apenas quando a ação for chamada
_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")

def _configure_pyautogui(module) -> None:
    module.FAILSAFE = True
    module.PAUSE = 0.05

pyautogui = LazyModule("pyautogui", _configure_pyautogui)
pyperclip = LazyModule("pyperclip")

def _executar_digitacao(text, delay, press_enter, use_paste, player):
    """Sempre usa a área de transferência para evitar erros com acentos (ç, ã, é)."""
    if delay > 0:
        time.sleep(delay)

    try:
        if use_paste and _PYPERCLIP:
            # Forçamos o uso do pyperclip (copiar e colar) na maioria das vezes
            pyperclip.copy(text)
            time.sleep(0.1)
            hotkey = ("command", "v") if sys.platform == "darwin" else ("ctrl", "v")
            pyautogui.hotkey(*hotkey)
        else:
            # Só usa a digitação robótica se a biblioteca de colar não existir ou for falso
            pyautogui.write(text, interval=0.03)

        if press_enter:
            time.sleep(0.1)
            pyautogui.press("enter")
            
        print(f"[DigitarTeclado] ✅ Texto inserido com sucesso.")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[ação] digitou texto no sistema.")

    except Exception as e:
        print(f"[DigitarTeclado] ❌ Erro: {e}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[erro] falha ao digitar: {e}")

def digitar_teclado(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    text = params.get("text", "")
    delay = params.get("delay", 3)
    press_enter = params.get("press_enter", False)
    use_paste = params.get("use_paste", True) # Por segurança, sempre tentará colar

    if not text:
        return outcome.failed("digitar_teclado", "Nenhum texto foi fornecido.")
        
    if not _PYAUTOGUI:
        return outcome.failed(
            "digitar_teclado", 
            "PyAutoGUI não está instalado. Rode no terminal: pip install pyautogui"
        )

    # Inicia a digitação em segundo plano
    threading.Thread(
        target=_executar_digitacao,
        args=(text, delay, press_enter, use_paste, player),
        daemon=True,
        name="digitar-teclado",
    ).start()

    return outcome.started("digitar_teclado", delay_esperado=delay)

# ── Declaração da Ferramenta para a IA ──────────────
TOOL = {
    "name": "digitar_teclado",
    "description": (
        "Usa o teclado do computador para digitar um texto onde o cursor estiver focado. "
        "Sempre avise o usuário que você vai começar a digitar e peça para ele clicar "
        "no campo correto durante o tempo de espera (delay). "
        "A ferramenta usará a área de transferência (colar) automaticamente para evitar erros de acentos."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {
                "type": "STRING",
                "description": "Texto exato a ser digitado."
            },
            "delay": {
                "type": "INTEGER",
                "description": "Segundos de espera antes de digitar (padrão: 3)."
            },
            "press_enter": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro, pressiona a tecla Enter após digitar."
            },
            "use_paste": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro, usa Ctrl+V em vez de simular cada tecla."
            }
        },
        "required": ["text"]
    },
    "handler": digitar_teclado,
}