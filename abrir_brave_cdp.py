#!/usr/bin/env python3
"""
Abre o Brave com CDP (porta 9222) e seu perfil real.
NAVEGA AUTOMATICAMENTE pro WhatsApp Web e espera você confirmar.
DEIXE ESSE BRAVE ABERTO e rode o JARVIS em outro terminal.
"""
import subprocess
import os
import sys
import asyncio
from pathlib import Path

# Mata todos os Brave existentes
print("🔴 Fechando todos os Brave...")
try:
    subprocess.run(["taskkill", "/F", "/IM", "brave.exe"], capture_output=True, timeout=10)
except:
    pass

import time
time.sleep(2)

# Caminhos
brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")

print(f"📁 Perfil: {user_data_dir}")
print(f"🚀 Iniciando Brave com --remote-debugging-port=9222...")

# Inicia Brave com CDP + JÁ ABRE WhatsApp Web
# SCRIPT MANUAL: roda UMA VEZ antes de jogar pra configurar
# Abre VISÍVEL (maximizado) pra você confirmar login no WhatsApp Web
# Depois você minimiza/joga pro 2º monitor e JARVIS conecta via CDP sem roubar foco
proc = subprocess.Popen([
    brave_exe,
    "--remote-debugging-port=9222",
    f"--user-data-dir={user_data_dir}",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--start-maximized",
    "https://web.whatsapp.com/",  # ← ABRE DIRETO NO WHATSAPP WEB
], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)

print(f"✅ Brave iniciado (PID: {proc.pid})")
print("⏳ Aguardando WhatsApp Web carregar...")
time.sleep(5)

print()
print("=" * 60)
print("📋 PRÓXIMOS PASSOS:")
print("=" * 60)
print("1. No Brave que abriu: WhatsApp Web JÁ ABRIU automaticamente")
print("2. CONFIRME que NÃO pede QR code (já mostra suas conversas)")
print("3. Se pedir QR: escaneie com o celular")
print("4. DEIXE ESSE BRAVE ABERTO")
print("5. Abra OUTRO terminal (VS Code Terminal recomendado) e rode:")
print("   cd D:\\Projetos\\Mark-LVI-main")
print("   python modo_dev_sem_backup.py")
print("=" * 60)
print()
print("Pressione ENTER aqui quando confirmar que o WhatsApp Web tá logado...")
input()

# Testa a conexão CDP com seletores atualizados
print("\n🔍 Testando conexão CDP...")
try:
    from playwright.async_api import async_playwright

    async def test():
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        # Se não tá no WhatsApp, navega
        if "web.whatsapp.com" not in page.url:
            await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # Seletores modernos (data-testid) + fallbacks
        search_selectors = [
            "div[data-testid='chat-list-search']",
            "div[contenteditable='true'][data-tab='3']",
            "div[contenteditable='true'][placeholder*='Search']",
            "div[contenteditable='true'][aria-label*='Search']",
        ]

        qr_selectors = [
            "div[data-testid='qr-code']",
            "canvas[aria-label*='Scan']",
            "div[data-testid='link-device-qr-code']",
        ]

        # Tenta achar busca (logado)
        for selector in search_selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                print("✅ WHATSAPP WEB LOGADO! Caixa de busca encontrada.")
                await playwright.stop()
                return True
            except:
                continue

        # Tenta achar QR (não logado)
        for selector in qr_selectors:
            try:
                await page.wait_for_selector(selector, timeout=3000)
                print("⚠️  QR CODE DETECTADO - escaneie com o celular")
                await playwright.stop()
                return False
            except:
                continue

        print("? Estado desconhecido - nem busca nem QR achados")
        await playwright.stop()
        return False

    result = asyncio.run(test())
    if result:
        print("\n🎉 TUDO PRONTO! Pode rodar o JARVIS no outro terminal.")
    else:
        print("\n⚠️  Escaneie o QR code no Brave, depois rode o JARVIS.")

except Exception as e:
    print(f"⚠️  Erro no teste automático: {e}")
    print("   Se você vê as conversas no Brave, ignore e rode o JARVIS.")

print("\nPressione ENTER para fechar este script (o Brave continua aberto)...")
input()