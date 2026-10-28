"""
WhatsApp Web via CDP (Chrome DevTools Protocol) - Conecta no SEU Brave real
- Usa seu perfil Brave real (WhatsApp já logado, extensões, senhas)
- Zero QR Code após 1º login manual
- 100% headless/background após conectar
- NON-BLOCKING: retorna started, roda em background
- Preview popup no segundo monitor (ou monitor principal)
"""

import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from core import outcome
from core.lazyimport import LazyModule, installed

_PLAYWRIGHT = installed("playwright")
_PILLOW = installed("PIL")

playwright = LazyModule("playwright.async_api")
PILImage = LazyModule("PIL.Image")

BASE_DIR = Path(__file__).resolve().parent.parent
PREVIEW_DIR = BASE_DIR / "temp" / "whatsapp_previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

_last_prepared: Dict[str, Any] = {}

# Seletores baseados no debug real do WhatsApp Web (2025)
# O WhatsApp Web usa data-testid extensivamente
SELECTORS = {
    # Tela de QR Code / Link Device
    "qr_code": "div[data-testid='qr-code']",
    "qr_canvas_fallback": "canvas[aria-label*='Scan']",
    "link_device_screen": "div[data-testid='link-device-qr-code']",

    # Tela logada - busca de contatos
    "search_box": "div[data-testid='chat-list-search-container']",
    "search_box_fallback": "div[data-testid='chat-list-search']",
    "search_box_fallback2": "input[data-testid='chat-list-search-input']",
    "search_box_fallback3": "div[contenteditable='true'][placeholder*='Search']",

    # Lista de contatos
    "contact_list_item": "div[data-testid^='list-item-']",
    "contact_list_item_fallback": "div[data-testid='cell-frame-container']",
    "contact_name": "div[data-testid='cell-frame-title']",
    "contact_name_fallback": "span[dir='auto']",

    # Chat aberto - input de mensagem
    "message_input": "div[data-testid='conversation-compose-box-input']",
    "message_input_fallback": "div[contenteditable='true'][data-tab='10']",
    "message_input_fallback2": "div[contenteditable='true'][aria-label*='Type']",

    # Painel de conversa
    "chat_main": "div[data-testid='conversation-panel-messages']",
    "chat_header": "header[data-testid='conversation-header']",

    # Botão enviar (seletores atualizados 2024/2025) - ADICIONADO data-tab="11" que é o real
    "send_button": "button[data-testid='compose-btn-send']",
    "send_button_fallback": "button[data-testid='send-button']",
    "send_button_fallback2": "button[aria-label*='Send']",
    "send_button_fallback3": "button[aria-label*='Enviar']",
    "send_button_fallback4": "button[data-tab='11']",  # O VERDADEIRO seletor do botão enviar
    "send_button_fallback5": "span[data-icon='send']",
    "send_button_fallback6": "div[data-testid='send-button']",
    "send_button_fallback7": "button:has(span[data-icon='send'])",

    # Loading
    "loading": "div[data-testid='loading-screen']",
    "loading_fallback": "div[data-testid='spinner']",
}

# Ordem de tentativa para cada elemento (principal primeiro, fallbacks depois)
# IMPORTANTE: search_box_fallback2 (input real) ANTES do container
# send_button_fallback4 (data-tab="11") É O REAL - coloca ANTES dos outros
SELECTOR_GROUPS = {
    "search_box": ["search_box_fallback2", "search_box", "search_box_fallback", "search_box_fallback3"],
    "qr_code": ["qr_code", "qr_canvas_fallback", "link_device_screen"],
    "contact_list_item": ["contact_list_item", "contact_list_item_fallback"],
    "contact_name": ["contact_name", "contact_name_fallback"],
    "message_input": ["message_input", "message_input_fallback", "message_input_fallback2"],
    "send_button": ["send_button_fallback4", "send_button", "send_button_fallback", "send_button_fallback2", "send_button_fallback3", "send_button_fallback5", "send_button_fallback6", "send_button_fallback7"],
    "loading": ["loading", "loading_fallback"],
}

CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Caminho padrão do perfil do Brave no Windows
BRAVE_USER_DATA_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"))

# Detecta todos os navegadores Chromium instalados
def _find_chromium_browsers() -> Dict[str, Dict[str, str]]:
    """Retorna dict com browsers Chromium encontrados: {nome: {exe, user_data_dir}}"""
    browsers = {}

    # Configurações conhecidas de navegadores Chromium no Windows
    browser_configs = [
        {
            "name": "Brave",
            "exe_candidates": [
                r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
            "user_data_dir": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
        },
        {
            "name": "Chrome",
            "exe_candidates": [
                r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
                r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            ],
            "user_data_dir": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        },
        {
            "name": "Edge",
            "exe_candidates": [
                r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
                r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
                r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
            ],
            "user_data_dir": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
        },
        {
            "name": "Vivaldi",
            "exe_candidates": [
                r"%PROGRAMFILES%\Vivaldi\Application\vivaldi.exe",
                r"%PROGRAMFILES(X86)%\Vivaldi\Application\vivaldi.exe",
                r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe",
            ],
            "user_data_dir": r"%LOCALAPPDATA%\Vivaldi\User Data",
        },
        {
            "name": "Opera",
            "exe_candidates": [
                r"%PROGRAMFILES%\Opera\Opera.exe",
                r"%PROGRAMFILES(X86)%\Opera\Opera.exe",
                r"%LOCALAPPDATA%\Programs\Opera\Opera.exe",
                r"%LOCALAPPDATA%\Programs\Opera GX\Opera.exe",
            ],
            "user_data_dir": r"%APPDATA%\Opera Software\Opera Stable",
        },
        {
            "name": "Opera GX",
            "exe_candidates": [
                r"%PROGRAMFILES%\Opera GX\Opera.exe",
                r"%PROGRAMFILES(X86)%\Opera GX\Opera.exe",
                r"%LOCALAPPDATA%\Programs\Opera GX\Opera.exe",
            ],
            "user_data_dir": r"%APPDATA%\Opera Software\Opera GX Stable",
        },
    ]

    for config in browser_configs:
        for exe_candidate in config["exe_candidates"]:
            expanded = os.path.expandvars(exe_candidate)
            if os.path.exists(expanded):
                user_data = os.path.expandvars(config["user_data_dir"])
                browsers[config["name"]] = {
                    "exe": expanded,
                    "user_data_dir": user_data,
                }
                print(f"[WhatsAppCDP] 🔍 Navegador detectado: {config['name']} -> {expanded}")
                break

    return browsers


def _find_any_chromium_executable() -> Optional[Dict[str, str]]:
    """Encontra o primeiro navegador Chromium disponível."""
    browsers = _find_chromium_browsers()
    if not browsers:
        return None

    # Prioridade: Brave > Chrome > Edge > Vivaldi > Opera
    priority = ["Brave", "Chrome", "Edge", "Vivaldi", "Opera", "Opera GX"]
    for name in priority:
        if name in browsers:
            return {"name": name, **browsers[name]}

    # Retorna o primeiro encontrado
    first_name = next(iter(browsers))
    return {"name": first_name, **browsers[first_name]}


# Para compatibilidade com código antigo
def _find_brave_executable() -> Optional[str]:
    result = _find_any_chromium_executable()
    if result:
        return result["exe"]
    return None


class WhatsAppCDPSession:
    """
    Conecta no navegador Chromium real (Brave, Chrome, Edge, Vivaldi, Opera) via CDP (porta 9222).
    Requer que o navegador esteja rodando com --remote-debugging-port=9222
    """

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._connected = False

    def _names_match(self, search_name: str, found_name: str) -> bool:
        """Match flexível: nomes (ignora case, acentos, emojis, espaços) + telefones (só dígitos)."""
        import unicodedata
        import re

        def normalize_text(s: str) -> str:
            # Remove acentos, emojis, normaliza espaços, lowercase
            s = unicodedata.normalize('NFKD', s)
            s = ''.join(c for c in s if not unicodedata.combining(c))
            s = ''.join(c for c in s if c.isprintable() and ord(c) < 0x10000)  # remove emojis
            return ' '.join(s.lower().split())

        def normalize_phone(s: str) -> str:
            # Extrai SÓ dígitos (remove +, espaços, traços, parênteses)
            return re.sub(r'\D', '', s)

        search_norm = normalize_text(search_name)
        found_norm = normalize_text(found_name)

        # Match textual normal
        if search_norm in found_norm or found_norm in search_norm:
            return True

        # Match de TELEFONE: compara só dígitos (ignora +55, espaços, traços, etc)
        search_digits = normalize_phone(search_name)
        found_digits = normalize_phone(found_name)
        if search_digits and found_digits:
            # Match se um contém o outro (ex: 51994395124 contido em 5551994395124)
            if search_digits in found_digits or found_digits in search_digits:
                return True

        return False

    async def start(self) -> bool:
        """Conecta no Brave via CDP."""
        try:
            self._playwright = await playwright.async_playwright().start()

            # Tenta conectar no Brave já rodando na porta 9222
            print(f"[WhatsAppCDP] 🔌 Conectando no Brave via CDP ({CDP_URL})...")
            self.browser = await self._playwright.chromium.connect_over_cdp(CDP_URL, timeout=8000)

            # Pega o contexto padrão (seu perfil real)
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = await self.browser.new_context()

            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = await self.context.new_page()

            # Anti-detecção
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
            """)

            self._connected = True
            print("[WhatsAppCDP] ✅ Conectado no Brave real via CDP")
            return True

        except Exception as e:
            print(f"[WhatsAppCDP] ❌ Falha ao conectar via CDP: {e}")
            return False

    async def ensure_brave_running(self) -> bool:
        """Garante que algum navegador Chromium tá rodando com CDP. Se não, inicia.
        RECONEXÃO FORÇADA: para playwright antigo, cria tudo novo - evita conexão corrompida pós-popup.
        NÃO MATA navegador existente - só inicia novo se NÃO tiver nenhum rodando."""
        # SEMPRE limpa conexão antiga antes de reconectar (popup corrompe CDP)
        if self._playwright:
            try:
                await self._playwright.stop()
                print("[WhatsAppCDP] 🧹 Playwright antigo parado")
            except:
                pass
            self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._connected = False

        # 1. Tenta conectar no CDP existente
        print(f"[WhatsAppCDP] 🔌 Conectando no CDP ({CDP_URL})...")
        try:
            self._playwright = await playwright.async_playwright().start()
            self.browser = await self._playwright.chromium.connect_over_cdp(CDP_URL, timeout=8000)

            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = await self.browser.new_context()

            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = await self.context.new_page()

            # Anti-detecção
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = { runtime: {} };
            """)

            # Valida que a página RESPONDE
            test_url = await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda: self.page.url), timeout=3.0)
            test_title = await asyncio.wait_for(self.page.title(), timeout=3.0)
            print(f"[WhatsAppCDP] ✅ CDP reconectado e validado: {test_url} | {test_title}")

            self._connected = True
            return True

        except Exception as e:
            print(f"[WhatsAppCDP] ⚠️ CDP não disponível: {e}")

        # 2. Verifica se tem navegador Chromium rodando (sem CDP)
        browser_info = _find_any_chromium_executable()
        if not browser_info:
            print("[WhatsAppCDP] ❌ Nenhum navegador Chromium encontrado no sistema")
            return False

        # Check if browser process is already running
        import subprocess
        browser_name = browser_info["name"]
        browser_exe_name = os.path.basename(browser_info["exe"])

        try:
            result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {browser_exe_name}"],
                                  capture_output=True, text=True, timeout=5)
            browser_running = browser_exe_name.lower() in result.stdout.lower()
        except:
            browser_running = False

        if browser_running:
            # NÃO MATA SEU BRAVE - usa perfil dedicado do JARVIS
            print(f"[WhatsAppCDP] 🔄 {browser_name} seu tá aberto sem CDP → usando PERFIL DEDICADO do JARVIS...")
            print(f"[WhatsAppCDP]    (Seu Brave principal fica intocado)")
            # Usa perfil dedicado em vez do perfil do usuário
            jarvis_profile_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\JARVIS\BraveProfile"))
            jarvis_profile_dir.mkdir(parents=True, exist_ok=True)
            browser_info = dict(browser_info)
            browser_info["user_data_dir"] = str(jarvis_profile_dir)
            browser_running = False  # Força fluxo de iniciação com perfil dedicado

        # 3. NENHUM navegador rodando → INICIA AUTOMÁTICO (minimizado, sem roubar foco)
        print(f"[WhatsAppCDP] 🚀 Nenhum {browser_name} rodando. Iniciando com CDP automático...")
        print(f"[WhatsAppCDP]    Executável: {browser_info['exe']}")
        print(f"[WhatsAppCDP]    Perfil: {browser_info['user_data_dir']}")

        try:
            creation_flags = 0
            startupinfo = None
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE = minimizado, não ativa

            proc = subprocess.Popen([
                browser_info["exe"],
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={browser_info['user_data_dir']}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--start-minimized",
            ], creationflags=creation_flags, startupinfo=startupinfo)

            print(f"[WhatsAppCDP] ✅ {browser_name} iniciado automático (PID: {proc.pid}) - MINIMIZADO, não rouba foco")

            # Aguarda porta abrir
            for i in range(25):  # 25s max
                await asyncio.sleep(1)
                try:
                    if self._playwright:
                        try:
                            await self._playwright.stop()
                        except:
                            pass

                    self._playwright = await playwright.async_playwright().start()
                    self.browser = await self._playwright.chromium.connect_over_cdp(CDP_URL, timeout=4000)
                    contexts = self.browser.contexts
                    self.context = contexts[0] if contexts else await self.browser.new_context()
                    pages = self.context.pages
                    self.page = pages[0] if pages else await self.context.new_page()

                    # Valida
                    test_url = await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda: self.page.url), timeout=3.0)
                    test_title = await asyncio.wait_for(self.page.title(), timeout=3.0)
                    print(f"[WhatsAppCDP] ✅ CDP conectado e validado ({i+1}s): {test_url} | {test_title}")

                    self._connected = True
                    return True
                except:
                    continue

            print(f"[WhatsAppCDP] ❌ Timeout: {browser_name} não abriu porta CDP após 25s")
            return False

        except Exception as e:
            print(f"[WhatsAppCDP] ❌ Erro ao iniciar {browser_name}: {e}")
            return False

    async def _wait_for_any_selector(self, selector_keys: list[str], timeout: int = 10000) -> Tuple[str | None, any]:
        """Tenta múltiplos seletores em ordem, retorna (nome_do_seletor, elemento) do primeiro que achar."""
        for key in selector_keys:
            selector = SELECTORS.get(key)
            if not selector:
                continue
            try:
                element = await self.page.wait_for_selector(selector, timeout=timeout)
                if element:
                    print(f"[WhatsAppCDP] ✅ Seletor encontrado: {key} ({selector})")
                    return key, element
            except:
                continue
        return None, None

    async def goto_whatsapp(self) -> bool:
        """Navega para WhatsApp Web."""
        # Garante que a página está válida antes de navegar
        if not await self.ensure_page_valid():
            return False

        try:
            # Verifica se já estamos no WhatsApp Web
            current_url = self.page.url
            if "web.whatsapp.com" not in current_url:
                print("[WhatsAppCDP] 🌐 Navegando para WhatsApp Web...")
                await self.page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=20000)
            else:
                print("[WhatsAppCDP] 🔄 Já no WhatsApp Web, recarregando...")
                await self.page.reload(wait_until="domcontentloaded", timeout=10000)

            # Aguarda estabilizar
            await asyncio.sleep(0.8)

            # Tenta achar a caixa de busca (logado)
            print("[WhatsAppCDP] 🔍 Procurando indicador de login (caixa de busca)...")
            found_key, _ = await self._wait_for_any_selector(
                SELECTOR_GROUPS["search_box"],
                timeout=8000
            )
            if found_key:
                print("[WhatsAppCDP] ✅ WhatsApp Web já logado (perfil real)")
                return True

            # Se não achou busca, procura QR code / Link Device
            print("[WhatsAppCDP] 🔍 Procurando QR code / tela de link device...")
            found_key, _ = await self._wait_for_any_selector(
                SELECTOR_GROUPS["qr_code"],
                timeout=8000
            )
            if found_key:
                print(f"[WhatsAppCDP] ⚠️ QR Code / Link Device detectado ({found_key}) - precisa escanear")
                return False

            # Debug: lista o que tem na página se nada achou
            print("[WhatsAppCDP] ⚠️ Nem busca nem QR encontrados - debug da página:")
            await self._debug_page_state()

            return False

        except Exception as e:
            print(f"[WhatsAppCDP] Erro ao carregar WhatsApp: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _debug_page_state(self):
        """Debug: mostra o estado atual da página."""
        try:
            print(f"  URL: {self.page.url}")
            print(f"  Title: {await self.page.title()}")

            # Procura todos os data-testid visíveis
            testids = await self.page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('[data-testid]');
                    const result = [];
                    for (const el of elements) {
                        const testid = el.getAttribute('data-testid');
                        const tag = el.tagName.toLowerCase();
                        const visible = el.offsetWidth > 0 && el.offsetHeight > 0;
                        if (visible) result.push({testid, tag});
                    }
                    return result.slice(0, 30);
                }
            """)
            print(f"  data-testid visíveis: {testids}")

            # Procura contenteditable
            editables = await self.page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('[contenteditable="true"]');
                    const result = [];
                    for (const el of elements) {
                        const tag = el.tagName.toLowerCase();
                        const tab = el.getAttribute('data-tab');
                        const placeholder = el.getAttribute('placeholder');
                        const aria = el.getAttribute('aria-label');
                        const visible = el.offsetWidth > 0 && el.offsetHeight > 0;
                        if (visible) result.push({tag, 'data-tab': tab, placeholder, 'aria-label': aria});
                    }
                    return result;
                }
            """)
            print(f"  contenteditable visíveis: {editables}")

        except Exception as e:
            print(f"  Erro no debug: {e}")

    async def wait_for_qr_login(self, timeout: int = 120) -> bool:
        """Aguarda escanear QR (fallback se perfil não tiver sessão)."""
        print(f"[WhatsAppCDP] 📱 Escaneie QR no Brave... (tem {timeout}s)")
        try:
            # Aguarda QR sumir (qualquer um dos seletores de QR)
            found_key, _ = await self._wait_for_any_selector(
                SELECTOR_GROUPS["qr_code"],
                timeout=5000
            )
            if found_key:
                # QR encontrado, espera ele desaparecer
                print("[WhatsAppCDP] ⏳ QR detectado, aguardando escaneamento...")
                # Tenta esperar o QR sumir - usa o primeiro seletor que achou
                selector = SELECTORS[found_key]
                await self.page.wait_for_selector(selector, state="hidden", timeout=timeout * 1000)

            # Depois espera a busca aparecer (logado)
            found_key, _ = await self._wait_for_any_selector(
                SELECTOR_GROUPS["search_box"],
                timeout=15000
            )
            if found_key:
                print("[WhatsAppCDP] ✅ Login realizado!")
                return True

            print("[WhatsAppCDP] ❌ QR sumiu mas busca não apareceu")
            return False

        except Exception as e:
            print(f"[WhatsAppCDP] ❌ Timeout/erro no QR: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def search_contact(self, contact_name: str) -> bool:
        """Busca e seleciona contato usando clipboard para velocidade (não rouba foco)."""
        # Garante que a página está válida antes de buscar
        if not await self.ensure_page_valid():
            return False

        try:
            # Acha a caixa de busca
            print(f"[WhatsAppCDP] 🔍 Buscando contato: {contact_name}")
            found_key, search_box = await self._wait_for_any_selector(
                SELECTOR_GROUPS["search_box"],
                timeout=5000
            )
            if not search_box:
                print("[WhatsAppCDP] ❌ Caixa de busca não encontrada")
                return False

            # Se achou o container (div), procura o input DENTRO dele
            tag_name = await search_box.evaluate("el => el.tagName.toLowerCase()")
            if tag_name != "input" and tag_name != "textarea":
                print(f"[WhatsAppCDP] 🔍 Container encontrado ({tag_name}), procurando input interno...")
                inner_input = await search_box.query_selector("input, textarea, [contenteditable='true']")
                if inner_input:
                    search_box = inner_input
                    print(f"[WhatsAppCDP] ✅ Input interno encontrado")
                else:
                    print(f"[WhatsAppCDP] ⚠️ Input interno não encontrado, usando keyboard no container")

            await search_box.click()
            await asyncio.sleep(0.3)

            # USA CLIPBOARD PARA COLAR NOME DO CONTATO (muito mais rápido que digitar)
            # Evita roubo de foco porque não usa keyboard.type caractere por caractere
            try:
                import pyperclip
                pyperclip.copy(contact_name)
                await asyncio.sleep(0.1)
                # Ctrl+V para colar
                await self.page.keyboard.press("Control+v")
                print(f"[WhatsAppCDP] ✅ Contato colado via clipboard: {contact_name}")
            except ImportError:
                # Fallback: digita se pyperclip não disponível
                print(f"[WhatsAppCDP] ⚠️ pyperclip não disponível, digitando caractere por caractere")
                if tag_name in ("input", "textarea") or await search_box.get_attribute("contenteditable") == "true":
                    await search_box.fill("")
                await self.page.keyboard.type(contact_name, delay=30)

            # Aguarda resultados da busca aparecerem
            await asyncio.sleep(1.0)

            # Acha o item do contato - ESTRATÉGIA UNIVERSAL (qualquer nome)
            contact_item = None

            # Prepara versão só-dígitos para busca de telefone (WhatsApp formata diferente)
            import re
            search_digits = re.sub(r'\D', '', contact_name)
            has_text = search_digits if search_digits and len(search_digits) >= 8 else contact_name

            # Estratégia 1: Busca por texto no item (case-insensitive, parcial, telefones só dígitos)
            for attempt in range(3):
                # Seletores amplos que cobrem TODAS as versões do WhatsApp Web
                contact_selectors = [
                    # Seletores por data-testid (modernos)
                    f"div[data-testid^='list-item-']:has-text('{has_text}')",
                    f"div[data-testid='cell-frame-container']:has-text('{has_text}')",
                    f"div[data-testid='chat-list-item']:has-text('{has_text}')",
                    # Seletores genéricos por role/estrutura
                    f"div[role='listitem']:has-text('{has_text}')",
                    f"div[role='row']:has-text('{has_text}')",
                    # Seletores por classe comum (fallback)
                    f"div[class*='list-item']:has-text('{has_text}')",
                    f"div[class*='chat-list']:has-text('{has_text}')",
                    f"div[class*='contact']:has-text('{has_text}')",
                    # Último recurso: qualquer elemento clicável com o texto
                    f"*:has-text('{has_text}'):visible",
                ]

                for selector in contact_selectors:
                    try:
                        contact_item = await self.page.query_selector(selector)
                        if contact_item:
                            # Validação FLEXÍVEL: pega nome visível no item
                            name_el = await contact_item.query_selector(SELECTORS["contact_name"]) or \
                                     await contact_item.query_selector(SELECTORS["contact_name_fallback"]) or \
                                     await contact_item.query_selector("span[dir='auto']") or \
                                     await contact_item.query_selector("span[title]") or \
                                     await contact_item.query_selector("div[title]")
                            if name_el:
                                found_name = await name_el.inner_text()
                                # Match flexível: contém OU似似似似似 (pinyin, emojis, etc)
                                if self._names_match(contact_name, found_name):
                                    print(f"[WhatsAppCDP] ✅ Contato encontrado: '{found_name.strip()}' (seletor: {selector})")
                                    break
                            else:
                                # Sem elemento de nome - aceita se o item tem o texto
                                item_text = await contact_item.inner_text()
                                if self._names_match(contact_name, item_text):
                                    print(f"[WhatsAppCDP] ✅ Contato encontrado via texto do item: '{item_text[:50]}...' (seletor: {selector})")
                                    break
                        contact_item = None
                    except:
                        continue

                if contact_item:
                    break

                # Fallback: ITERA TODOS os itens da lista (não só o 1º)
                if attempt < 2:
                    print(f"[WhatsAppCDP] 🔄 Tentativa {attempt+1}/3 - aguardando resultados...")
                    await asyncio.sleep(1.5)
                    # Pega TODOS os itens da lista
                    all_items = await self.page.query_selector_all("div[data-testid^='list-item-'], div[role='listitem'], div[data-testid='cell-frame-container']")
                    print(f"[WhatsAppCDP] 🔍 Fallback: {len(all_items)} itens encontrados na lista")
                    for idx, item in enumerate(all_items):
                        try:
                            name_el = await item.query_selector(SELECTORS["contact_name"]) or \
                                     await item.query_selector(SELECTORS["contact_name_fallback"]) or \
                                     await item.query_selector("span[dir='auto']") or \
                                     await item.query_selector("span[title]") or \
                                     await item.query_selector("div[title]")
                            if name_el:
                                found_name = await name_el.inner_text()
                                match = self._names_match(contact_name, found_name)
                                print(f"[WhatsAppCDP]   Item #{idx+1}: '{found_name.strip()[:80]}' → match={match}")
                                if match:
                                    contact_item = item
                                    print(f"[WhatsAppCDP] ✅ Contato encontrado no item #{idx+1}: '{found_name.strip()}'")
                                    break
                            else:
                                # Tenta texto direto do item
                                item_text = await item.inner_text()
                                match = self._names_match(contact_name, item_text)
                                print(f"[WhatsAppCDP]   Item #{idx+1} (texto direto): '{item_text.strip()[:80]}' → match={match}")
                                if match:
                                    contact_item = item
                                    print(f"[WhatsAppCDP] ✅ Contato encontrado no item #{idx+1} (texto direto)")
                                    break
                        except Exception as e:
                            print(f"[WhatsAppCDP]   Item #{idx+1} erro: {e}")
                            continue
                    if contact_item:
                        break

            if not contact_item:
                print("[WhatsAppCDP] ❌ Contato não encontrado na lista após tentativas")
                # Debug completo
                try:
                    testids = await self.page.evaluate("""() => {
                        const els = document.querySelectorAll('[data-testid]');
                        return Array.from(els).slice(0, 40).map(el => el.getAttribute('data-testid'));
                    }""")
                    print(f"[WhatsAppCDP] 🔍 data-testid visíveis: {testids}")
                    # Lista textos dos itens da lista
                    items_text = await self.page.evaluate("""() => {
                        const items = document.querySelectorAll('[data-testid^=\"list-item-\"], [role=\"listitem\"]');
                        return Array.from(items).slice(0, 10).map(el => el.innerText.slice(0, 100));
                    }""")
                    print(f"[WhatsAppCDP] 📋 Itens da lista: {items_text}")
                except:
                    pass
                return False

            # CLICA NO CONTATO - estratégia robusta
            click_success = False

            # Rola para visão
            try:
                await contact_item.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
            except:
                pass

            for click_attempt in range(5):
                try:
                    if click_attempt == 0:
                        # Click via JavaScript no elemento nome (mais confiável)
                        name_el = await contact_item.query_selector(SELECTORS["contact_name"]) or \
                                  await contact_item.query_selector(SELECTORS["contact_name_fallback"])
                        if name_el:
                            await name_el.evaluate("el => el.click()")
                        else:
                            await contact_item.evaluate("el => el.click()")
                        print(f"[WhatsAppCDP] 🖱️ Click via JavaScript")

                    elif click_attempt == 1:
                        # Click normal Playwright
                        await contact_item.click(delay=100)
                        print(f"[WhatsAppCDP] 🖱️ Click normal Playwright")

                    elif click_attempt == 2:
                        # Click via coordenadas do mouse
                        box = await contact_item.bounding_box()
                        if box:
                            await self.page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        print(f"[WhatsAppCDP] 🖱️ Click via coordenadas mouse")

                    elif click_attempt == 3:
                        # Duplo click
                        await contact_item.click(delay=50)
                        await asyncio.sleep(0.1)
                        await contact_item.click(delay=50)
                        print(f"[WhatsAppCDP] 🖱️ Duplo click")

                    else:
                        # Enter no elemento focado
                        await contact_item.focus()
                        await self.page.keyboard.press("Enter")
                        await asyncio.sleep(0.2)
                        await self.page.keyboard.press("Enter")
                        print(f"[WhatsAppCDP] 🖱️ Enter duplo")

                    # Aguarda chat carregar
                    await asyncio.sleep(1.5)

                    # Verifica se chat abriu - múltiplos indicadores
                    conversation_loaded = False

                    # 1. Painel de conversa
                    panel = await self.page.query_selector("div[data-testid='conversation-panel'], div[data-testid='conversation-panel-messages'], div[role='main']")

                    # 2. Input de mensagem (footer)
                    msg_input = await self.page.query_selector(
                        "div[contenteditable='true'][data-tab='10'], "
                        "div[contenteditable='true'][aria-label*='mensagem'], "
                        "div[contenteditable='true'][placeholder*='mensagem'], "
                        "footer div[contenteditable='true'], "
                        "div[data-testid='conversation-compose-box-input']"
                    )

                    # 3. Header do contato (confirma que abriu o chat certo)
                    header = await self.page.query_selector("header[data-testid='conversation-header'], div[data-testid='conversation-header']")

                    if panel and msg_input and header:
                        conversation_loaded = True
                        print("[WhatsAppCDP] ✅ Chat carregado confirmado (painel + input + header)")
                    elif panel and msg_input:
                        conversation_loaded = True
                        print("[WhatsAppCDP] ✅ Chat carregado (painel + input)")

                    if conversation_loaded:
                        click_success = True
                        break

                    print(f"[WhatsAppCDP] 🔄 Tentativa {click_attempt+1}/5 - chat não carregou totalmente, tentando novamente...")
                    # Re-rolar para visão
                    try:
                        await contact_item.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                    except:
                        pass

                except Exception as e:
                    print(f"[WhatsAppCDP] ⚠️ Erro no clique tentativa {click_attempt+1}: {e}")

            if not click_success:
                print("[WhatsAppCDP] ❌ Falha ao abrir chat após 5 tentativas")
                return False

            print(f"[WhatsAppCDP] ✅ Contato '{contact_name}' selecionado e chat aberto")
            return True
        except Exception as e:
            print(f"[WhatsAppCDP] Erro ao buscar '{contact_name}': {e}")
            import traceback
            traceback.print_exc()
            return False

    async def type_message(self, message: str) -> bool:
        """Digita mensagem usando clipboard (Ctrl+V) - muito mais rápido e confiável."""
        # Garante que a página está válida antes de digitar
        if not await self.ensure_page_valid():
            return False

        try:
            print(f"[WhatsAppCDP] ✏️ Colando mensagem via clipboard...")
            found_key, msg_input = await self._wait_for_any_selector(
                SELECTOR_GROUPS["message_input"],
                timeout=5000
            )
            if not msg_input:
                print("[WhatsAppCDP] ❌ Campo de mensagem não encontrado")
                return False

            await msg_input.click()
            await asyncio.sleep(0.2)

            # USA CLIPBOARD PARA COLAR MENSAGEM (evita digitação caractere por caractere)
            try:
                import pyperclip
                pyperclip.copy(message)
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+v")
                print(f"[WhatsAppCDP] ✅ Mensagem colada via clipboard ({len(message)} chars)")
            except ImportError:
                # Fallback: digita se pyperclip não disponível
                print(f"[WhatsAppCDP] ⚠️ pyperclip não disponível, digitando...")
                await msg_input.fill("")
                await self.page.keyboard.type(message, delay=20)

            await asyncio.sleep(0.5)
            print("[WhatsAppCDP] ✅ Mensagem pronta no campo")
            return True
        except Exception as e:
            print(f"[WhatsAppCDP] Erro ao digitar: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def take_chat_screenshot(self, preview_path: Path) -> bool:
        """Captura screenshot do chat em ALTA RESOLUÇÃO: header (nome+foto) + histórico + input com mensagem."""
        # Garante que a página está válida antes de capturar
        if not await self.ensure_page_valid():
            return False

        try:
            # Aguarda o chat carregar completamente e a mensagem aparecer no input
            await asyncio.sleep(0.5)

            # Verifica se o input tem a mensagem (confirma que type_message funcionou)
            input_element = await self.page.query_selector(
                "div[contenteditable='true'][data-tab='10'], "
                "div[contenteditable='true'][aria-label*='mensagem'], "
                "div[contenteditable='true'][placeholder*='mensagem'], "
                "footer div[contenteditable='true'], "
                "div[data-testid='conversation-compose-box-input']"
            )

            if input_element:
                input_text = await input_element.inner_text()
                print(f"[WhatsAppCDP] 📝 Input atual: '{input_text[:50]}...' ({len(input_text)} chars)")

            # PRIORIDADE 1: Captura o painel inteiro da conversa (header + mensagens + input)
            # Este é o container principal que engloba tudo
            conversation_panel = await self.page.query_selector("div[data-testid='conversation-panel']")

            if conversation_panel:
                print("[WhatsAppCDP] 📸 Capturando painel completo da conversa (header + mensagens + input)")
                # Força scroll para topo para capturar histórico
                await conversation_panel.evaluate("el => el.scrollTop = 0")
                await asyncio.sleep(0.3)
                await conversation_panel.screenshot(
                    path=str(preview_path),
                    animations="disabled",
                )
                print(f"[WhatsAppCDP] 📸 Preview HD completo salvo: {preview_path}")
                return True

            # PRIORIDADE 2: Captura viewport da área principal (main) que inclui header + mensagens + footer/input
            main_element = await self.page.query_selector("main")
            if main_element:
                print("[WhatsAppCDP] 📸 Capturando <main> completo (header + histórico + input)")
                # Scroll topo para pegar histórico
                await main_element.evaluate("el => el.scrollTop = 0")
                await asyncio.sleep(0.3)
                await main_element.screenshot(
                    path=str(preview_path),
                    animations="disabled",
                )
                print(f"[WhatsAppCDP] 📸 Preview HD salvo (<main>): {preview_path}")
                return True

            # PRIORIDADE 3: Captura viewport da página (fallback)
            print("[WhatsAppCDP] 📸 Capturando viewport completo da página")
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.3)
            await self.page.screenshot(
                path=str(preview_path),
                full_page=False,
                animations="disabled",
            )
            print(f"[WhatsAppCDP] 📸 Preview HD salvo (viewport): {preview_path}")
            return True

        except Exception as e:
            print(f"[WhatsAppCDP] Erro no screenshot: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def send_message(self) -> bool:
        """Envia a mensagem clicando no botão ou pressionando Enter. Rápido e robusto."""
        # SEMPRE reconecta antes de enviar (popup pode ter quebrado a conexão CDP)
        print("[WhatsAppCDP] 🔄 === INICIANDO ENVIO ===")
        print("[WhatsAppCDP] 🔄 Reconectando sessão antes de enviar...")
        if not await self.ensure_brave_running():
            print("[WhatsAppCDP] ❌ Falha ao reconectar")
            return False

        # Garante que a página está válida
        if not await self.ensure_page_valid():
            print("[WhatsAppCDP] ❌ Página inválida após reconexão")
            return False

        try:
            print("[WhatsAppCDP] 📤 Enviando mensagem...")
            print(f"[WhatsAppCDP] 📍 URL atual: {self.page.url}")

            # Debug SIMPLES sem evaluate (não trava) - apenas loga URL e título
            try:
                title = await asyncio.wait_for(self.page.title(), timeout=2.0)
                print(f"[WhatsAppCDP] 📄 Título da página: {title}")
            except:
                print("[WhatsAppCDP] ⚠️ Não conseguiu ler título (ignorado)")

            # Timeout razoável para achar botão de enviar
            found_key, send_btn = await self._wait_for_any_selector(
                SELECTOR_GROUPS["send_button"],
                timeout=8000
            )
            if send_btn:
                print(f"[WhatsAppCDP] ✅ Botão encontrado via seletor: {found_key}")
                await send_btn.click()
                await asyncio.sleep(0.3)
                print("[WhatsAppCDP] ✅ Mensagem enviada via botão")
                return True
            else:
                print("[WhatsAppCDP] ⚠️ Botão não achado via seletores, tentando click direto no footer...")
                # Tenta achar botão dentro do footer/conversation-compose
                footer_selectors = [
                    "footer button[data-testid='compose-btn-send']",
                    "footer button[aria-label*='Send']",
                    "footer button[aria-label*='Enviar']",
                    "div[data-testid='conversation-compose-box'] button",
                    "footer div[role='button']:has(span[data-icon='send'])",
                    "footer button:has(span[data-icon='send'])",
                ]
                for selector in footer_selectors:
                    try:
                        btn = await self.page.query_selector(selector)
                        if btn:
                            await btn.click()
                            await asyncio.sleep(0.3)
                            print(f"[WhatsAppCDP] ✅ Mensagem enviada via botão no footer ({selector})")
                            return True
                    except Exception as e:
                        print(f"[WhatsAppCDP] Footer selector {selector} falhou: {e}")
                        continue

                print("[WhatsAppCDP] ⚠️ Botão não achado no footer, tentando Enter via JS no input...")
                # Fallback robusto: dispara evento de teclado via JavaScript no input
                try:
                    result = await self.page.evaluate("""
                        () => {
                            const selectors = [
                                "div[contenteditable='true'][data-tab='10']",
                                "div[contenteditable='true'][aria-label*='mensagem']",
                                "div[contenteditable='true'][placeholder*='mensagem']",
                                "footer div[contenteditable='true']",
                                "div[data-testid='conversation-compose-box-input']"
                            ];
                            for (const sel of selectors) {
                                const input = document.querySelector(sel);
                                if (input && input.offsetWidth > 0 && input.offsetHeight > 0) {
                                    input.focus();
                                    input.textContent = input.textContent; // garante foco
                                    const event = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                                    input.dispatchEvent(event);
                                    const event2 = new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                                    input.dispatchEvent(event2);
                                    return {success: true, selector: sel};
                                }
                            }
                            return {success: false, error: 'Input não encontrado ou invisível'};
                        }
                    """)
                    print(f"[WhatsAppCDP] JS fallback resultado: {result}")
                    if result.get('success'):
                        await asyncio.sleep(0.3)
                        print("[WhatsAppCDP] ✅ Mensagem enviada via Enter (JS)")
                        return True
                    else:
                        print(f"[WhatsAppCDP] JS fallback falhou: {result.get('error')}")
                except Exception as e:
                    print(f"[WhatsAppCDP] Erro no fallback JS: {e}")
                    import traceback
                    traceback.print_exc()

                # Último recurso: Enter via keyboard do Playwright
                try:
                    if self.page and self.page.keyboard:
                        await self.page.keyboard.press("Enter")
                        await asyncio.sleep(0.3)
                        print("[WhatsAppCDP] ✅ Mensagem enviada via keyboard.press")
                        return True
                except Exception as e:
                    print(f"[WhatsAppCDP] Keyboard.press falhou: {e}")

                return False
        except Exception as e:
            print(f"[WhatsAppCDP] Erro ao enviar: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def ensure_page_valid(self) -> bool:
        """Garante que a página ainda está válida, conectada e no WhatsApp Web. Reconecta se necessário."""
        try:
            if not self._connected or not self.browser or not self.context or not self.page:
                print("[WhatsAppCDP] 🔄 Sessão inválida (objetos None), reconectando...")
                return await self.ensure_brave_running()

            # Testa se a página REALMENTE responde (acessa URL + título com timeout)
            try:
                # self.page.url é property, self.page.title() é método
                current_url = await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, lambda: self.page.url), timeout=3.0)
                title = await asyncio.wait_for(self.page.title(), timeout=3.0)
                print(f"[WhatsAppCDP] ✅ Página válida: {current_url} | {title}")
            except Exception as e:
                print(f"[WhatsAppCDP] 🔄 Página não responde ({e}), reconectando...")
                return await self.ensure_brave_running()

            # Se não estamos no WhatsApp Web, navega de volta
            if "web.whatsapp.com" not in current_url:
                print(f"[WhatsAppCDP] 🔄 Página não está no WhatsApp Web ({current_url}), navegando...")
                await self.page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(0.8)

                # Verifica se logou
                found_key, _ = await self._wait_for_any_selector(
                    SELECTOR_GROUPS["search_box"],
                    timeout=5000
                )
                if not found_key:
                    print("[WhatsAppCDP] ⚠️ Não logou no WhatsApp Web após navegar")
                    return False
                print("[WhatsAppCDP] ✅ Voltou ao WhatsApp Web logado")

            return True
        except Exception as e:
            print(f"[WhatsAppCDP] Página inválida, reconectando: {e}")
            return await self.ensure_brave_running()

    async def close(self):
        """Fecha conexão CDP (NÃO fecha o Brave - mantém seu perfil rodando)."""
        try:
            if self._playwright:
                await self._playwright.stop()
            # NÃO fecha browser/context - é seu Brave real, mantém aberto
        except Exception as e:
            print(f"[WhatsAppCDP] Erro ao desconectar: {e}")


def _show_preview_popup_and_handle(preview_path: Path, destinatario: str, mensagem: str, auto_enviar: bool, session, player):
    """
    Abre o preview em uma janela popup RESPONSIVA com scroll - cabe em qualquer tela.
    Imagem escala mantendo proporção, com scrollbars se necessário.
    Quando o usuário clica em Enviar ou Cancelar, executa a ação correspondente diretamente.
    """
    try:
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image, ImageTk

        # Carrega a imagem
        img = Image.open(preview_path)
        original_width, original_height = img.size

        # Calcula tamanho máximo baseado na tela (85% da tela, deixando margem)
        root_temp = tk.Tk()
        root_temp.withdraw()  # Esconde janela temporária
        screen_width = root_temp.winfo_screenwidth()
        screen_height = root_temp.winfo_screenheight()
        root_temp.destroy()

        max_width = int(screen_width * 0.85)
        max_height = int(screen_height * 0.85)

        # Redimensiona mantendo aspect ratio se necessário
        if original_width > max_width or original_height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            print(f"[WhatsAppCDP] 📸 Imagem redimensionada: {original_width}x{original_height} -> {img.width}x{img.height}")
        else:
            print(f"[WhatsAppCDP] 📸 Imagem tamanho original: {img.width}x{img.height}")

        # Cria janela root
        root = tk.Tk()
        root.title(f"📱 WhatsApp Preview - {destinatario}")
        root.attributes('-topmost', True)
        root.attributes('-alpha', 1.0)
        root.minsize(600, 400)  # Tamanho mínimo

        # Configura ícone se possível
        try:
            root.iconbitmap(default='')
        except:
            pass

        # Tenta posicionar no segundo monitor
        root.update_idletasks()

        # Obtém informações dos monitores
        try:
            import win32api
            monitors = win32api.EnumDisplayMonitors()
            if len(monitors) > 1:
                monitor_info = win32api.GetMonitorInfo(monitors[1][0])
                work_area = monitor_info['Work']
                monitor_width = work_area[2] - work_area[0]
                monitor_height = work_area[3] - work_area[1]
                # Usa 90% da área do monitor
                win_width = min(img.width, int(monitor_width * 0.9))
                win_height = min(img.height, int(monitor_height * 0.9))
                x = work_area[0] + (monitor_width - win_width) // 2
                y = work_area[1] + (monitor_height - win_height) // 2
                print(f"[WhatsAppCDP] 📺 Popup no 2º monitor: ({x}, {y}) janela {win_width}x{win_height}")
            else:
                win_width = min(img.width, int(screen_width * 0.9))
                win_height = min(img.height, int(screen_height * 0.9))
                x = (screen_width - win_width) // 2
                y = (screen_height - win_height) // 2
                print(f"[WhatsAppCDP] 📺 Popup centralizado: ({x}, {y}) janela {win_width}x{win_height}")
        except ImportError:
            win_width = min(img.width, int(screen_width * 0.9))
            win_height = min(img.height, int(screen_height * 0.9))
            x = (screen_width - win_width) // 2
            y = (screen_height - win_height) // 2
            print(f"[WhatsAppCDP] 📺 Popup centralizado (sem win32api): ({x}, {y}) janela {win_width}x{win_height}")

        # Define geometria
        root.geometry(f"{win_width}x{win_height}+{x}+{y}")

        # Força atualização e traz para frente
        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.attributes('-topmost', True)
        root.focus_force()

        # Converte para PhotoImage
        photo = ImageTk.PhotoImage(img)

        # ===== LAYOUT RESPONSIVO COM SCROLL =====
        # Canvas com scrollbars para a imagem
        canvas_frame = ttk.Frame(root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        # Grid layout para canvas + scrollbars
        canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        # Frame interno que vai no canvas (para a imagem + info)
        inner_frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # Imagem no frame interno
        img_label = ttk.Label(inner_frame, image=photo)
        img_label.image = photo
        img_label.pack(pady=(0, 10))

        # Info label
        info_text = f"📞 Para: {destinatario}\n💬 Mensagem: {mensagem[:300]}{'...' if len(mensagem) > 300 else ''}"
        info_label = ttk.Label(inner_frame, text=info_text, wraplength=win_width - 60,
                               justify=tk.CENTER, font=('Segoe UI', 11))
        info_label.pack(pady=(0, 20))

        # Botões GRANDES E FIXOS NA BASE (fora do scroll)
        btn_frame = ttk.Frame(root)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=15)

        def on_send():
            root.result = "send"
            root.quit()
            root.destroy()

        def on_cancel():
            root.result = "cancel"
            root.quit()
            root.destroy()

        style = ttk.Style()
        style.configure('Big.TButton', font=('Segoe UI', 12, 'bold'), padding=(20, 10))

        send_btn = ttk.Button(btn_frame, text="✅  ENVIAR AGORA", command=on_send, style='Big.TButton')
        send_btn.pack(side=tk.LEFT, padx=15, ipadx=20, ipady=5)

        cancel_btn = ttk.Button(btn_frame, text="❌  CANCELAR", command=on_cancel, style='Big.TButton')
        cancel_btn.pack(side=tk.RIGHT, padx=15, ipadx=20, ipady=5)

        # Bind teclas
        root.bind('<Return>', lambda e: on_send())
        root.bind('<Escape>', lambda e: on_cancel())
        root.bind('<KP_Enter>', lambda e: on_send())

        # Scroll com mouse wheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        def _on_shift_mousewheel(event):
            canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Shift-MouseWheel>", _on_shift_mousewheel)

        # Atualiza scrollregion quando inner_frame muda de tamanho
        def _configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner_frame.bind("<Configure>", _configure_scroll_region)

        # Ajusta largura do inner_frame ao canvas
        def _configure_canvas_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _configure_canvas_width)

        send_btn.focus_set()

        # Garante visibilidade
        root.after(100, lambda: (root.lift(), root.attributes('-topmost', True), root.focus_force()))

        print(f"[WhatsAppCDP] 📺 Popup ABERTO - responsivo com scroll, aguardando ação...")

        # Roda o loop
        root.mainloop()

        # Cleanup binds globais (protege contra app já destruído)
        try:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Shift-MouseWheel>")
        except tk.TclError:
            pass  # App já destruído, ignora

        # Processa o resultado
        result = getattr(root, 'result', 'cancel')

        print(f"[WhatsAppCDP] 📺 Popup FECHADO - resultado: {result}")

        # Lock anti-race: se envio por voz já tá rodando, cancela este
        if result == "send" and not _send_lock.acquire(blocking=False):
            print("[WhatsAppCDP] ⚠️ Envio por voz já em andamento - cancelando envio do popup")
            _notify_done(player, "Envio cancelado (já estava enviando por comando de voz).")
        else:
            # Executa a ação em thread separada com seu próprio event loop
            # CRIA NOVA SESSION (a antiga foi corrompida pelo popup bloquear o event loop)
            def _handle_result():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if result == "send":
                        print("[WhatsAppCDP] 🔄 Popup: criando NOVA session para envio (conexão fresca)...")
                        fresh_session = WhatsAppCDPSession()
                        if loop.run_until_complete(fresh_session.ensure_brave_running()):
                            if loop.run_until_complete(fresh_session.send_message()):
                                with _last_prepared_lock:
                                    _last_prepared = {}
                                _notify_done(player, f"✅ Mensagem ENVIADA para {destinatario}", sent=True)
                            else:
                                _notify_failed(player, "Falha ao enviar mensagem")
                        else:
                            _notify_failed(player, "Não conseguiu reconectar no navegador para enviar")
                    elif result == "cancel":
                        with _last_prepared_lock:
                            _last_prepared = {}
                        _notify_done(player, "Mensagem cancelada.")
                    else:
                        _notify_failed(player, "Erro ao exibir preview")
                except Exception as e:
                    print(f"[WhatsAppCDP] Erro ao processar resultado do popup: {e}")
                    import traceback
                    traceback.print_exc()
                    _notify_failed(player, f"Erro: {e}")
                finally:
                    if result == "send":
                        _send_lock.release()
                    loop.close()

            threading.Thread(target=_handle_result, daemon=True, name="whatsapp-popup-result").start()

    except Exception as e:
        print(f"[WhatsAppCDP] Erro ao abrir popup de preview: {e}")
        import traceback
        traceback.print_exc()
        _notify_failed(player, f"Erro ao abrir preview: {e}")


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND WORKER
# ═══════════════════════════════════════════════════════════════════════

_last_prepared_lock = threading.Lock()
_send_lock = threading.Lock()  # Evita envios paralelos (popup + voz)
_background_thread: Optional[threading.Thread] = None


def _run_prepare_in_background(
    player,
    destinatario: str,
    mensagem: str,
    auto_enviar: bool
):
    """Worker: prepara mensagem via CDP no seu navegador Chromium real (Brave, Chrome, Edge, etc)."""
    global _last_prepared

    async def _prepare():
        global _last_prepared
        session = WhatsAppCDPSession()

        try:
            if not await session.ensure_brave_running():
                _notify_failed(player, "Não conseguiu conectar/iniciar navegador Chromium com CDP (porta 9222)")
                return

            logged_in = await session.goto_whatsapp()

            if not logged_in:
                # Perfil não tem sessão WhatsApp - precisa QR (raro, só 1ª vez)
                if not await session.wait_for_qr_login():
                    _notify_failed(player, "Timeout no QR Code (2 min)")
                    return

            if not await session.search_contact(destinatario):
                _notify_failed(player, f"Contato '{destinatario}' não encontrado")
                return

            if not await session.type_message(mensagem):
                _notify_failed(player, "Falha ao digitar mensagem")
                return

            timestamp = int(time.time() * 1000)
            preview_filename = f"preview_{timestamp}.png"
            preview_path = PREVIEW_DIR / preview_filename

            if not await session.take_chat_screenshot(preview_path):
                _notify_failed(player, "Falha ao gerar preview")
                return

            # Sucesso - salva estado para envio posterior
            with _last_prepared_lock:
                _last_prepared = {
                    "session": session,
                    "destinatario": destinatario,
                    "mensagem": mensagem,
                    "auto_enviar": auto_enviar,
                    "preview_path": str(preview_path),
                    "timestamp": timestamp,
                }

            if auto_enviar:
                # Garante que a página ainda está válida antes de enviar
                if not await session.ensure_page_valid():
                    _notify_failed(player, "Conexão com navegador perdida ao tentar enviar")
                    return
                if await session.send_message():
                    with _last_prepared_lock:
                        _last_prepared = {}
                    _notify_done(player, f"✅ Mensagem ENVIADA para {destinatario}", sent=True)
                else:
                    _notify_failed(player, "Falha ao enviar mensagem")
            else:
                # AVISA QUE TÁ PRONTO (voz + UI)
                _notify_ready(player, destinatario, preview_path)
                # Mostra preview em POPUP responsivo no segundo monitor
                _show_preview_popup_and_handle(preview_path, destinatario, mensagem, auto_enviar, session, player)

        except Exception as e:
            print(f"[WhatsAppCDP] Erro geral: {e}")
            _notify_failed(player, str(e))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_prepare())
    finally:
        loop.close()


def _notify_ready(player, destinatario: str, preview_path: Path):
    msg = f"📱 WhatsApp pronto para {destinatario}! Preview aberto em popup."
    print(f"[WhatsAppCDP] {msg}")
    try:
        if player and hasattr(player, "speak"):
            player.speak(f"Mensagem preparada pro {destinatario}. Abri o preview no segundo monitor, confere aí.")
        if player and hasattr(player, "show_content"):
            player.show_content(f"WhatsApp Preview - {destinatario}",
                f"Preview aberto em popup na tela secundária.\n\nArquivo salvo em:\n{preview_path}\n\nClique em 'Enviar' no popup ou diga 'envia whatsapp'.")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[WhatsApp] Preview pronto para {destinatario}: {preview_path}")
    except Exception as e:
        print(f"[WhatsAppCDP] Erro ao notificar: {e}")


def _notify_done(player, info: str, sent: bool = False):
    print(f"[WhatsAppCDP] {info}")
    try:
        if player and hasattr(player, "speak"):
            player.speak(info.replace("✅ ", "").replace("❌ ", ""))
        if player and hasattr(player, "write_log"):
            player.write_log(f"[WhatsApp] {info}")
    except Exception as e:
        print(f"[WhatsAppCDP] Erro ao notificar done: {e}")


def _notify_failed(player, error: str):
    print(f"[WhatsAppCDP] ❌ {error}")
    try:
        if player and hasattr(player, "speak"):
            player.speak(f"Deu ruim no WhatsApp: {error}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[WhatsApp] ERRO: {error}")
    except Exception as e:
        print(f"[WhatsAppCDP] Erro ao notificar falha: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TOOL HANDLERS
# ═══════════════════════════════════════════════════════════════════════

def _handle_preparar(parameters, player) -> str:
    params = parameters or {}
    destinatario = params.get("destinatario", "").strip()
    mensagem = params.get("mensagem", "").strip()
    auto_enviar = params.get("auto_enviar", False)

    if not destinatario or not mensagem:
        return outcome.failed("whatsapp", "Destinatário e mensagem são obrigatórios.")

    global _background_thread
    if _background_thread and _background_thread.is_alive():
        return outcome.failed("whatsapp", "Já tem preparação em andamento. Diga 'cancela whatsapp' ou aguarde.")

    _background_thread = threading.Thread(
        target=_run_prepare_in_background,
        args=(player, destinatario, mensagem, auto_enviar),
        daemon=True,
        name="whatsapp-prepare"
    )
    _background_thread.start()

    return outcome.started("whatsapp", info=f"Preparando WhatsApp para {destinatario}... (conectando no seu Brave via CDP)")


def _handle_enviar(player) -> str:
    global _last_prepared

    with _last_prepared_lock:
        if not _last_prepared or "destinatario" not in _last_prepared:
            return outcome.failed("whatsapp", "Nenhuma mensagem preparada pendente. Use 'preparar' primeiro.")
        destinatario = _last_prepared["destinatario"]
        # NÃO reusa session - cria nova no event loop do worker (evita bug cross-loop)

    # Lock anti-race: evita envio paralelo (popup + voz)
    if not _send_lock.acquire(blocking=False):
        return outcome.failed("whatsapp", "Envio já em andamento (popup aberto). Aguarde ou cancele.")

    def _send_worker():
        async def _send():
            global _last_prepared
            fresh_session = WhatsAppCDPSession()
            try:
                print("[WhatsAppCDP] 🔄 Voz: criando NOVA session para envio...")
                if not await fresh_session.ensure_brave_running():
                    _notify_failed(player, "Não conseguiu conectar no navegador para enviar")
                    return
                if await fresh_session.send_message():
                    with _last_prepared_lock:
                        _last_prepared = {}
                    _notify_done(player, f"✅ Mensagem ENVIADA para {destinatario}", sent=True)
                else:
                    _notify_failed(player, "Falha ao enviar")
            except Exception as e:
                _notify_failed(player, f"Erro ao enviar: {e}")
                import traceback
                traceback.print_exc()
            finally:
                _send_lock.release()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_send())
        finally:
            loop.close()

    threading.Thread(target=_send_worker, daemon=True, name="whatsapp-send").start()
    return outcome.started("whatsapp", info=f"Enviando mensagem para {destinatario}...")


def _handle_cancelar(player) -> str:
    global _last_prepared, _background_thread
    with _last_prepared_lock:
        _last_prepared = {}
    return outcome.done("whatsapp", info="Mensagem cancelada.")


def controlar_whatsapp(
    parameters, response=None, player=None, session_memory=None
) -> str:
    params = parameters or {}
    acao = params.get("acao", "preparar").strip().lower()

    if acao == "enviar":
        return _handle_enviar(player)
    elif acao == "cancelar":
        return _handle_cancelar(player)
    else:
        return _handle_preparar(params, player)


TOOL = {
    "name": "whatsapp",
    "description": (
        "Controla WhatsApp Web via CDP no SEU navegador Chromium real (Brave, Chrome, Edge, Vivaldi, Opera) na porta 9222. "
        "⭐ USA SEU PERFIL REAL - WhatsApp já logado, extensões, senhas. "
        "ZERO QR CODE após 1º login manual no navegador. "
        "NON-BLOCKING: responde na hora, prepara em background. "
        "NÃO ROUBA FOCO do jogo/tela - conecta no navegador que já tá rodando. "
        "Pré-requisito: Navegador aberto com --remote-debugging-port=9222 "
        "(o script inicia automaticamente se não estiver rodando - tenta Brave, Chrome, Edge, Vivaldi, Opera). "
        "Fluxo: 'prepara whatsapp pro Sonic' → conecta no seu navegador → "
        "busca contato → cola msg → screenshot preview → POPUP no 2º monitor → 'envia whatsapp'. "
        "Comandos: 'prepara whatsapp pro Sonic dizendo bora jogar', "
        "'envia whatsapp', 'cancela whatsapp'."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "destinatario": {"type": "STRING", "description": "Nome do contato (ex: 'Mãe', 'Sonic')"},
            "mensagem": {"type": "STRING", "description": "Texto exato da mensagem"},
            "auto_enviar": {"type": "BOOLEAN", "description": "True=envia direto, False=prepara e abre popup (padrão: false)", "default": False},
            "acao": {"type": "STRING", "description": "Ação: 'preparar' (padrão), 'enviar', 'cancelar'", "enum": ["preparar", "enviar", "cancelar"], "default": "preparar"}
        },
        "required": ["destinatario", "mensagem"]
    },
    "handler": controlar_whatsapp,
}