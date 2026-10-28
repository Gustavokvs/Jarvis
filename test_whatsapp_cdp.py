#!/usr/bin/env python3
"""
Test script to verify WhatsApp Web CDP connection works.
This tests the core functionality without needing the full JARVIS app.
"""
import asyncio
import os
from pathlib import Path
import sys

# Add the project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.lazyimport import installed
from playwright.async_api import async_playwright

# Check dependencies
print("Checking dependencies...")
print(f"  playwright: {installed('playwright')}")
print(f"  PIL: {installed('PIL')}")

# Configuration
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"
BRAVE_USER_DATA_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"))
BRAVE_EXE = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

print(f"\nBrave executable: {BRAVE_EXE}")
print(f"Brave user data dir: {BRAVE_USER_DATA_DIR}")
print(f"CDP URL: {CDP_URL}")

async def test_cdp_connection():
    """Test connecting to Brave via CDP."""
    print("\n--- Testing CDP Connection ---")

    # First, check if Brave is already running with CDP
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        print("✅ Connected to existing Brave instance via CDP!")

        contexts = browser.contexts
        print(f"  Found {len(contexts)} context(s)")

        if contexts:
            context = contexts[0]
            pages = context.pages
            print(f"  Found {len(pages)} page(s)")
            for i, page in enumerate(pages):
                print(f"    Page {i}: {page.url}")

        await playwright.stop()
        return True
    except Exception as e:
        print(f"❌ No existing Brave with CDP on port {CDP_PORT}: {e}")
        return False

async def test_start_brave_with_cdp():
    """Test starting Brave with CDP enabled."""
    print("\n--- Testing Brave Start with CDP ---")

    import subprocess

    # Kill any existing Brave processes on the port
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe"],
                      capture_output=True, timeout=5)
    except:
        pass

    await asyncio.sleep(1)

    # Start Brave with CDP
    print(f"Starting Brave with --remote-debugging-port={CDP_PORT}...")
    try:
        creation_flags = 0
        startupinfo = None
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE

        proc = subprocess.Popen([
            BRAVE_EXE,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={BRAVE_USER_DATA_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--start-minimized",
        ], creationflags=creation_flags, startupinfo=startupinfo)

        print(f"  Started Brave process (PID: {proc.pid})")

        print(f"  Started Brave process (PID: {proc.pid})")

        # Wait for port to be ready
        for i in range(30):
            await asyncio.sleep(1)
            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.connect_over_cdp(CDP_URL, timeout=3000)
                print(f"✅ Connected to Brave after {i+1} seconds!")

                contexts = browser.contexts
                context = contexts[0] if contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()

                # Test navigating to WhatsApp Web
                print("  Navigating to WhatsApp Web...")
                await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=60000)
                print(f"  Page URL: {page.url}")

                # Check for search box (logged in) or QR code (not logged in)
                try:
                    await page.wait_for_selector("div[contenteditable='true'][data-tab='3']", timeout=10000)
                    print("✅ WhatsApp Web is LOGGED IN (search box found)")
                except:
                    try:
                        await page.wait_for_selector("canvas[aria-label='Scan me!']", timeout=5000)
                        print("⚠️ WhatsApp Web shows QR CODE - needs manual login")
                    except:
                        print("? WhatsApp Web state unknown")

                await playwright.stop()
                return True
            except Exception as e:
                if i == 29:
                    print(f"❌ Timeout: Brave didn't open CDP port after 30 seconds: {e}")
                    proc.terminate()
                    return False
                continue

    except Exception as e:
        print(f"❌ Failed to start Brave: {e}")
        return False

async def main():
    print("=" * 60)
    print("WhatsApp Web CDP Test")
    print("=" * 60)

    # Test 1: Try connecting to existing Brave
    connected = await test_cdp_connection()

    if not connected:
        # Test 2: Start Brave with CDP and test
        connected = await test_start_brave_with_cdp()

    print("\n" + "=" * 60)
    if connected:
        print("✅ TEST PASSED: CDP connection works!")
        print("The whatsapp_web.py should work correctly.")
    else:
        print("❌ TEST FAILED: Could not establish CDP connection")
        print("Check:")
        print("  1. Brave is installed at:", BRAVE_EXE)
        print("  2. No other Brave instances are blocking the port")
        print("  3. Firewall/antivirus isn't blocking port 9222")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())