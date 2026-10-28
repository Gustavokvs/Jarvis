import time
import urllib.parse
import os
import platform
import subprocess
import threading
import re
from core import outcome
from core.lazyimport import LazyModule, installed
from core import appidentity

# Usa a mesma biblioteca de teclado do seu computer_control e adiciona o pyperclip para colar textos perfeitos
_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
pyautogui = LazyModule("pyautogui")
pyperclip = LazyModule("pyperclip")


_last_sent_cache = {}

# Windows-specific: save/restore foreground window
if platform.system() == "Windows":
    try:
        import ctypes
        from ctypes import wintypes
        _USER32 = ctypes.WinDLL("user32", use_last_error=True)
        _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception:
        _USER32 = None
        _KERNEL32 = None
else:
    _USER32 = None
    _KERNEL32 = None


def _get_foreground_window():
    """Get the currently foreground window handle (Windows only)."""
    if _USER32:
        try:
            return _USER32.GetForegroundWindow()
        except Exception:
            pass
    return None


def _set_foreground_window(hwnd):
    """Restore focus to a specific window (Windows only)."""
    if not _USER32 or not hwnd:
        return False
    try:
        # Same focus-stealing prevention technique as appidentity.focus()
        fore = _USER32.GetForegroundWindow()
        if not fore:
            return False
        their = _USER32.GetWindowThreadProcessId(fore, None)
        ours = _KERNEL32.GetCurrentThreadId()
        if their == ours:
            return _USER32.SetForegroundWindow(hwnd)
        if not _USER32.AttachThreadInput(ours, their, True):
            return False
        try:
            _USER32.BringWindowToTop(hwnd)
            return bool(_USER32.SetForegroundWindow(hwnd))
        finally:
            _USER32.AttachThreadInput(ours, their, False)
    except Exception:
        pass
    return False


def _minimize_window(hwnd):
    """Minimize a window (Windows only)."""
    if _USER32 and hwnd:
        try:
            SW_MINIMIZE = 6
            _USER32.ShowWindow(hwnd, SW_MINIMIZE)
            return True
        except Exception:
            pass
    return False


def _find_whatsapp_window():
    """Find WhatsApp window handle after launch (Windows only)."""
    if not _USER32:
        return None
    try:
        # Wait a bit for WhatsApp to create its window
        time.sleep(1.5)
        matches = appidentity.running("WhatsApp")
        if not matches:
            return None
        # Get window handles for the best match
        best = matches[0]
        hwnds = appidentity._hwnds_for(best.pid)
        return hwnds[0] if hwnds else None
    except Exception:
        return None


def controlar_whatsapp_desktop(
    parameters, response=None, player=None, session_memory=None
) -> str:
    params = parameters or {}
    # Mudamos "numero" para "destinatario" para aceitar tanto Nomes quanto Números
    destinatario = params.get("destinatario", "").strip()
    mensagem = params.get("mensagem", "").strip()
    auto_enviar = params.get("auto_enviar", False)
    # Novo parâmetro: manter foco na tela atual (padrão True para nova UX)
    manter_foco = params.get("manter_foco", True)

    if not destinatario or not mensagem:
        return outcome.failed("whatsapp_desktop", "Destinatário e mensagem são obrigatórios.")

    # Idempotency check: prevent duplicate sending within 10 seconds
    now = time.time()
    cache_key = (destinatario.lower(), mensagem)
    if cache_key in _last_sent_cache and (now - _last_sent_cache[cache_key]) < 10.0:
        return outcome.done("whatsapp_desktop", info=f"Mensagem para {destinatario} já foi enviada recentemente (evitado envio duplicado).")
    _last_sent_cache[cache_key] = now

    try:
        # Voz proativa
        acao_voz = "enviando" if auto_enviar else "preparando"
        if player and hasattr(player, "speak"):
            threading.Thread(
                target=player.speak,
                args=(f"Deixa comigo, {acao_voz} a mensagem no WhatsApp.",),
                daemon=True,
            ).start()

        # Salva a janela ativa atual ANTES de abrir o WhatsApp
        original_hwnd = _get_foreground_window() if manter_foco else None
        whatsapp_hwnd = None

        # Verifica se o destinatário é um número de telefone (só digitos, espaços, + ou -)
        is_numero = bool(re.match(r'^[\+\d\s\-]+$', destinatario))

        if is_numero:
            # Remove espaços e traços
            numero_limpo = re.sub(r'[\s\-]', '', destinatario)
            # Usa a URI direta para o número, mas SEM o text= para evitar o bug do Windows
            uri = f"whatsapp://send?phone={numero_limpo}"
            if platform.system() == "Windows":
                os.startfile(uri)
            elif platform.system() == "Darwin":
                subprocess.run(["open", uri])
            else:
                subprocess.run(["xdg-open", uri])

            time.sleep(4) # Aguarda o app abrir e carregar a conversa

        else:
            # É UM NOME DE CONTATO! Abre o app puro e pesquisa na marra.
            uri = "whatsapp://"
            if platform.system() == "Windows":
                os.startfile(uri)
            elif platform.system() == "Darwin":
                subprocess.run(["open", uri])
            else:
                subprocess.run(["xdg-open", uri])

            time.sleep(4) # Aguarda o app abrir

            if _PYAUTOGUI and _PYPERCLIP:
                # Atalho universal de pesquisa no WhatsApp
                hotkey_cmd = "command" if platform.system() == "Darwin" else "ctrl"
                pyautogui.hotkey(hotkey_cmd, "f")
                time.sleep(1)
                # Usa colar para o nome do contato para evitar erros com acentos/caracteres
                pyperclip.copy(destinatario)
                time.sleep(0.3)
                pyautogui.hotkey(hotkey_cmd, "v")
                time.sleep(2) # Espera a busca carregar
                pyautogui.press("enter")
                time.sleep(1) # Espera entrar no chat do contato

        # Agora vamos escrever a mensagem usando a Área de Transferência (Ctrl+V)
        # Isso garante que 100% das palavras, acentos e emojis funcionem perfeitamente.
        if _PYPERCLIP and _PYAUTOGUI:
            pyperclip.copy(mensagem)
            time.sleep(0.5)

            hotkey_cmd = "command" if platform.system() == "Darwin" else "ctrl"
            pyautogui.hotkey(hotkey_cmd, "v")
            time.sleep(1) # Pequena pausa para o texto colar na caixa

            if auto_enviar:
                pyautogui.press("enter")
                result_msg = f"Aplicativo aberto e mensagem ENVIADA para {destinatario}."
                status = "done"
            else:
                result_msg = f"Aplicativo aberto e mensagem REDIGIDA para {destinatario}. Aguardando revisão."
                status = "done"
        else:
            return outcome.failed("whatsapp_desktop", "PyAutoGUI ou Pyperclip não estão instalados.")

        # Se o usuário pediu para manter foco, restaura a janela original
        if manter_foco and original_hwnd:
            # Tenta encontrar a janela do WhatsApp para minimizar
            whatsapp_hwnd = _find_whatsapp_window()
            if whatsapp_hwnd:
                _minimize_window(whatsapp_hwnd)
            # Restaura foco para a janela original
            _set_foreground_window(original_hwnd)
            if status == "done" and not auto_enviar:
                result_msg += " (WhatsApp minimizado - sua tela não perdeu o foco)"

        return outcome.done("whatsapp_desktop", info=result_msg)

    except Exception as e:
        # Tenta restaurar foco mesmo em caso de erro
        if manter_foco and original_hwnd:
            _set_foreground_window(original_hwnd)
        return outcome.failed(
            "whatsapp_desktop", f"Erro ao manipular o WhatsApp Desktop: {str(e)}"
        )


TOOL = {
    "name": "whatsapp_desktop_legacy",
    "description": (
        "[LEGADO/DEPRECADO] Controla o aplicativo nativo do WhatsApp Desktop (ROUBA FOCO). "
        "⚠️ USE 'whatsapp' EM VEZ DESTA - a ferramenta 'whatsapp' usa WhatsApp Web headless e NÃO rouba foco. "
        "Esta ferramenta abre o app nativo do Windows, o que tira você do jogo/tela. "
        "Mantida apenas para compatibilidade. "
        "Parâmetros: "
        "- 'destinatario': Nome do contato ou número "
        "- 'mensagem': Texto da mensagem "
        "- 'auto_enviar': true=envia, false=prepara "
        "- 'manter_foco': true=tenta restaurar foco depois (padrão: true)"
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "destinatario": {
                "type": "STRING",
                "description": "Nome do contato (ex: 'Sonic', 'Pri') OU Número de telefone (ex: 5551999999999)",
            },
            "mensagem": {
                "type": "STRING",
                "description": "Texto exato da mensagem que será enviada/redigida",
            },
            "auto_enviar": {
                "type": "BOOLEAN",
                "description": "True para apertar o botão de enviar. False apenas para colar o texto e aguardar o usuário revisar.",
            },
            "manter_foco": {
                "type": "BOOLEAN",
                "description": "Se true (padrão), após a operação o foco volta para a janela original e o WhatsApp é minimizado. Se false, o WhatsApp fica em foco (comportamento antigo).",
            },
        },
        "required": ["destinatario", "mensagem", "auto_enviar"],
    },
    "handler": controlar_whatsapp_desktop,
}