import time
import urllib.parse
import os
import platform
import subprocess
import threading
import re
from core import outcome
from core.lazyimport import LazyModule, installed

# Usa a mesma biblioteca de teclado do seu computer_control e adiciona o pyperclip para colar textos perfeitos
_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
pyautogui = LazyModule("pyautogui")
pyperclip = LazyModule("pyperclip")


def controlar_whatsapp_desktop(
    parameters, response=None, player=None, session_memory=None
) -> str:
    params = parameters or {}
    # Mudamos "numero" para "destinatario" para aceitar tanto Nomes quanto Números
    destinatario = params.get("destinatario", "").strip()
    mensagem = params.get("mensagem", "").strip()
    auto_enviar = params.get("auto_enviar", False)

    if not destinatario or not mensagem:
        return outcome.failed("whatsapp_desktop", "Destinatário e mensagem são obrigatórios.")

    try:
        # Voz proativa
        acao_voz = "enviando" if auto_enviar else "preparando"
        if player and hasattr(player, "speak"):
            threading.Thread(
                target=player.speak,
                args=(f"Deixa comigo, {acao_voz} a mensagem no WhatsApp.",),
                daemon=True,
            ).start()

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
                return outcome.done("whatsapp_desktop", info=f"Aplicativo aberto e mensagem ENVIADA para {destinatario}.")
            else:
                return outcome.done("whatsapp_desktop", info=f"Aplicativo aberto e mensagem REDIGIDA para {destinatario}. Aguardando revisão física do usuário.")
        else:
            return outcome.failed("whatsapp_desktop", "PyAutoGUI ou Pyperclip não estão instalados.")

    except Exception as e:
        return outcome.failed(
            "whatsapp_desktop", f"Erro ao manipular o WhatsApp Desktop: {str(e)}"
        )


TOOL = {
    "name": "whatsapp_desktop",
    "description": (
        "Controla o aplicativo nativo do WhatsApp Desktop do usuário. "
        "SUPER PODER: Agora você pode passar o NOME do contato (ex: 'Sonic', 'Mãe') no campo 'destinatario', "
        "ou um número de telefone direto. "
        "Se o usuário pedir para 'procurar o contato' e mandar mensagem, USE ESTA FERRAMENTA, passando o nome no destinatário. NUNCA diga que não consegue procurar contatos. "
        "Atenção à variável 'auto_enviar': "
        "Se o usuário disser 'escreva, prepare, deixe pronto, não envie', defina auto_enviar como FALSE. "
        "Se o usuário disser 'mande, envie, dispara', defina auto_enviar como TRUE."
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
        },
        "required": ["destinatario", "mensagem", "auto_enviar"],
    },
    "handler": controlar_whatsapp_desktop,
}