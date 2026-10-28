import os
import platform
import re
import sys
import json
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from config import get_os, is_windows, is_mac, is_linux

_CNW: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if platform.system() == "Windows" else {}
)

_KNOWN_APPIDS: dict[str, tuple[str, str]] = {
    "pubg":                ("578080",  "PUBG: Battlegrounds"),
    "pubg battlegrounds":  ("578080",  "PUBG: Battlegrounds"),
    "pubg: battlegrounds": ("578080",  "PUBG: Battlegrounds"),
    "battlegrounds":       ("578080",  "PUBG: Battlegrounds"),
    "gta5":                ("271590",  "Grand Theft Auto V"),
    "gta v":               ("271590",  "Grand Theft Auto V"),
    "grand theft auto v":  ("271590",  "Grand Theft Auto V"),
    "cs2":                 ("730",     "Counter-Strike 2"),
    "csgo":                ("730",     "Counter-Strike 2"),
    "counter-strike 2":    ("730",     "Counter-Strike 2"),
    "counter strike 2":    ("730",     "Counter-Strike 2"),
    "dota2":               ("570",     "Dota 2"),
    "dota 2":              ("570",     "Dota 2"),
    "rust":                ("252490",  "Rust"),
    "valheim":             ("892970",  "Valheim"),
    "cyberpunk":           ("1091500", "Cyberpunk 2077"),
    "cyberpunk 2077":      ("1091500", "Cyberpunk 2077"),
    "elden ring":          ("1245620", "ELDEN RING"),
    "minecraft":           ("1672970", "Minecraft Launcher"),
    "apex legends":        ("1172470", "Apex Legends"),
    "apex":                ("1172470", "Apex Legends"),
    "fortnite":            ("1517990", "Fortnite"),
    "goose goose duck":    ("1568590", "Goose Goose Duck"),
    "among us":            ("945360",  "Among Us"),
    "fall guys":           ("1097150", "Fall Guys"),
    "rocket league":       ("252950",  "Rocket League"),
    "warframe":            ("230410",  "Warframe"),
    "destiny 2":           ("1085660", "Destiny 2"),
    "team fortress 2":     ("440",     "Team Fortress 2"),
    "tf2":                 ("440",     "Team Fortress 2"),
    "left 4 dead 2":       ("550",     "Left 4 Dead 2"),
    "l4d2":                ("550",     "Left 4 Dead 2"),
    "paladins":            ("444090",  "Paladins"),
    "smite":               ("386360",  "SMITE"),
    "war thunder":         ("236390",  "War Thunder"),
    "world of warships":   ("552990",  "World of Warships"),
    "path of exile":       ("238960",  "Path of Exile"),
    "poe":                 ("238960",  "Path of Exile"),
    "lost ark":            ("1599340", "Lost Ark"),
    "new world":           ("1063730", "New World: Aeternum"),
}

def _find_steam_path() -> Path | None:
    if is_windows(): return _find_steam_windows()
    if is_mac():     return _find_steam_mac()
    return _find_steam_linux()


def _find_steam_windows() -> Path | None:
    try:
        import winreg
        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if p.exists() and (p / "steam.exe").exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", ""))       / "Steam",
        Path("C:/Steam"), Path("D:/Steam"), Path("E:/Steam"), Path("F:/Steam"),
    ]:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_steam_mac() -> Path | None:
    for p in [
        Path.home() / "Library" / "Application Support" / "Steam",
        Path("/Applications/Steam.app/Contents/MacOS"),
    ]:
        if p.exists():
            return p
    return None


def _find_steam_linux() -> Path | None:
    for p in [
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "root",
        Path.home() / ".local"  / "share" / "Steam",
        Path("/usr/share/steam"),
        Path("/opt/steam"),
    ]:
        if p.exists():
            return p
    return None


def _steam_exe(steam_path: Path) -> Path:
    if is_windows(): return steam_path / "steam.exe"
    if is_mac():     return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    return steam_path / "steam.sh"


def _launch_steam_url(exe: Path, url: str) -> None:
    if is_mac():
        subprocess.Popen(["open", url])
    elif is_linux():
        subprocess.Popen(["xdg-open", url])
    else:
        subprocess.Popen([str(exe), url])

def _get_steam_libraries(steam_path: Path) -> list[Path]:
    libraries = [steam_path / "steamapps"]
    vdf_path  = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries
    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
            lib = Path(raw_path.replace("\\\\", "/")) / "steamapps"
            if lib.exists() and lib not in libraries:
                libraries.append(lib)
    except Exception:
        pass
    return libraries


def _get_steam_games(steam_path: Path) -> list[dict]:
    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content  = acf.read_text(encoding="utf-8", errors="ignore")
                app_id   = re.search(r'"appid"\s+"(\d+)"',     content)
                name     = re.search(r'"name"\s+"([^"]+)"',     content)
                state    = re.search(r'"StateFlags"\s+"(\d+)"', content)
                size     = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
                if app_id and name:
                    games.append({
                        "id":    app_id.group(1),
                        "name":  name.group(1),
                        "state": int(state.group(1)) if state else 0,
                        "size":  int(size.group(1))  if size  else 0,
                        "lib":   str(lib),
                        "acf":   str(acf),
                    })
            except Exception:
                continue
    return games

def _is_steam_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                                 capture_output=True, text=True, **_CNW).stdout
            return "steam.exe" in out.lower()
        proc = "steam_osx" if is_mac() else "steam"
        return bool(subprocess.run(["pgrep", "-x", proc],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        return False

def _get_steam_window_rect() -> tuple[int, int, int, int] | None:
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            if "steam" in w.title.lower() and w.width > 200 and w.visible:
                return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


def _click_first_profile_by_screenshot() -> bool:

    try:
        import pyautogui
        import numpy as np

        time.sleep(1.5)
        win = _get_steam_window_rect()
        if not win:
            print("[GameUpdater] ⚠️ Steam window not found")
            return False

        wx, wy, ww, wh = win
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img        = np.array(screenshot)
        h, w       = img.shape[:2]

        search_y1, search_y2 = h // 3,  h * 3 // 4
        search_x1, search_x2 = w // 5,  w * 4 // 5
        region = img[search_y1:search_y2, search_x1:search_x2]

        r, g, b = region[:,:,0].astype(int), region[:,:,1].astype(int), region[:,:,2].astype(int)
        max_c   = np.maximum(np.maximum(r, g), b)
        min_c   = np.minimum(np.minimum(r, g), b)
        colorful = (max_c > 60) & ((max_c - min_c) > 40)

        if not colorful.any():
            print("[GameUpdater] ⚠️ Avatar colour not found — clicking by guess")
            pyautogui.click(wx + ww // 2 - ww // 6, wy + wh // 2)
            return True

        cols = np.where(colorful.any(axis=0))[0]
        rows = np.where(colorful.any(axis=1))[0]
        if not len(cols) or not len(rows):
            return False

        avatar_w   = min(90, region.shape[1] // 4)
        first_col  = int(cols[0])
        block_cols = cols[cols < first_col + avatar_w]

        abs_x = wx + search_x1 + int(block_cols.mean())
        abs_y = wy + search_y1 + int(rows.mean())
        print(f"[GameUpdater] 🎯 Profile avatar ({abs_x}, {abs_y}) — clicking")
        pyautogui.click(abs_x, abs_y)
        return True

    except ImportError as e:
        print(f"[GameUpdater] ⚠️ Missing library: {e}")
        return False
    except Exception as e:
        print(f"[GameUpdater] ⚠️ Profile detection failed: {e}")
        return False


def _handle_steam_profile_selection() -> bool:
    print("[GameUpdater] 🔍 Checking profile-selection dialog...")
    win = _get_steam_window_rect()
    if not win:
        return False

    wx, wy, ww, wh = win
    try:
        import pyautogui, numpy as np
        screenshot   = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img          = np.array(screenshot)
        is_small     = ww < 900 and wh < 700
        top_region   = img[:wh // 3, :, :]
        white_pixels = int(np.sum(
            (top_region[:,:,0] > 200) &
            (top_region[:,:,1] > 200) &
            (top_region[:,:,2] > 200)
        ))
        if not is_small and white_pixels <= 100:
            print("[GameUpdater] ℹ️ No profile dialog — Steam is already logged in")
            return False
    except ImportError:
        pass
    except Exception:
        pass

    print("[GameUpdater] 👤 Profile selection detected — clicking the first profile")
    return _click_first_profile_by_screenshot()

def _find_best_drive() -> dict | None:
    import shutil, string
    drives = []
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        if os.path.exists(drive_path):
            try:
                free_gb = shutil.disk_usage(drive_path).free / (1024 ** 3)
                if free_gb > 0:
                    drives.append({"letter": letter, "path": drive_path, "free_gb": free_gb})
            except Exception:
                continue
    return max(drives, key=lambda d: d["free_gb"]) if drives else None


def _select_drive_in_dialog(dialog, drive_letter: str) -> bool:
    target = drive_letter.upper()
    for control_type in ("ListItem", "RadioButton"):
        try:
            for ctrl in dialog.descendants(control_type=control_type):
                if target in ctrl.window_text().upper():
                    ctrl.click_input()
                    print(f"[GameUpdater] ✅ Drive selected ({control_type}): {ctrl.window_text()}")
                    return True
        except Exception:
            continue
    try:
        for combo in dialog.descendants(control_type="ComboBox"):
            try:
                combo.expand()
                time.sleep(0.15)
                for idx, txt in enumerate(combo.texts()):
                    if target in txt.upper():
                        combo.select(idx)
                        return True
                combo.collapse()
            except Exception:
                continue
    except Exception:
        pass
    try:
        for ctrl in dialog.descendants():
            txt = ctrl.window_text().upper()
            if f"{target}:" in txt and len(txt) < 80:
                ctrl.click_input()
                return True
    except Exception:
        pass
    return False


def _click_button(window, keywords: list[str]) -> bool:
    try:
        for btn in window.descendants(control_type="Button"):
            try:
                txt = btn.window_text().lower().strip()
                if txt in keywords or any(kw in txt for kw in keywords):
                    btn.click_input()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _handle_install_dialog_pyautogui(game_name: str, best_drive: dict) -> str:
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return (f"Install dialog opened for '{game_name}'. "
                f"Please select '{best_drive['letter']}:' and click Install manually.")

    pyautogui.FAILSAFE = False
    drive_label = f"{best_drive['letter']}:"
    install_win = None

    for _ in range(30):
        time.sleep(0.5)
        for w in gw.getAllWindows():
            if ("install" in w.title.lower() or "steam" in w.title.lower()) \
                    and w.width > 300 and w.visible:
                install_win = w
                break
        if install_win:
            break

    if not install_win:
        return f"Please select '{drive_label}' and click Install in Steam for '{game_name}'."

    try:
        install_win.activate()
        time.sleep(0.4)
    except Exception:
        pass

    wx, wy = install_win.left, install_win.top
    ww, wh = install_win.width, install_win.height
    pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))
    time.sleep(0.2)
    pyautogui.typewrite(best_drive["letter"], interval=0.05)
    time.sleep(0.2)
    pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))
    return f"Attempted drive {drive_label} selection and Install click for '{game_name}'."


def _handle_install_dialog(game_name: str) -> str:
    best_drive = _find_best_drive()
    if not best_drive:
        return f"Install dialog opened for '{game_name}'. Could not detect drives."

    drive_letter = best_drive["letter"]
    drive_label  = f"{drive_letter}:"
    print(f"[GameUpdater] 🏆 Target drive: {drive_label} ({best_drive['free_gb']:.1f} GB free)")

    try:
        from pywinauto import Application, findwindows
        dialog = None

        # NOTE: this drives Steam's native installer dialog by matching its
        # on-screen button/title text, which is localized. We match English and
        # Turkish labels (install/yükle, next/ileri, ok/tamam). On a Steam client
        # set to another language the match simply fails and the automation
        # reports it — it never crashes, and manual install still works.
        for _ in range(40):
            time.sleep(0.5)
            try:
                for hwnd in findwindows.find_windows(
                    title_re=r"(?i)(install|yükle|steam)", visible_only=True
                ):
                    try:
                        app  = Application(backend="uia").connect(handle=hwnd)
                        win  = app.window(handle=hwnd)
                        rect = win.rectangle()
                        if win.is_visible() and rect.width() > 300 and rect.height() > 200:
                            all_text = " ".join(
                                c.window_text() for c in win.descendants()
                                if c.window_text()
                            ).upper()
                            if any(x in all_text for x in
                                   ("C:", "D:", "E:", "F:", "INSTALL", "YÜKLE")):
                                dialog = win
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            if dialog:
                break

        if not dialog:
            raise RuntimeError("Dialog not found")

        dialog.set_focus()
        time.sleep(0.4)
        drive_selected  = _select_drive_in_dialog(dialog, drive_letter)
        install_clicked = _click_button(
            dialog, ["install", "yükle", "next", "ileri", "ok", "tamam"]
        )

        if install_clicked:
            suffix = f"Selected {drive_label} and" if drive_selected else "Default drive used, but"
            return f"{suffix} clicked Install for '{game_name}'."
        return f"Please click Install manually in Steam for '{game_name}'."

    except ImportError:
        return _handle_install_dialog_pyautogui(game_name, best_drive)
    except Exception as e:
        print(f"[GameUpdater] ⚠️ pywinauto failed: {e}")
        return _handle_install_dialog_pyautogui(game_name, best_drive)

def _ensure_steam_running(steam_path: Path) -> bool:
    if _is_steam_running():
        return True

    exe = _steam_exe(steam_path)
    if not exe.exists():
        print(f"[GameUpdater] ❌ Steam not found: {exe}")
        return False

    print("[GameUpdater] 🚀 Starting Steam...")
    if is_mac():
        subprocess.Popen(["open", "-a", "Steam"])
    else:
        subprocess.Popen([str(exe)])

    for _ in range(20):
        time.sleep(1)
        if _is_steam_running():
            print("[GameUpdater] ✅ Steam is running")
            time.sleep(4)
            if is_windows():
                _handle_steam_profile_selection()
                time.sleep(2)
            return True

    print("[GameUpdater] ⚠️ Could not start Steam")
    return False

def _search_steam_appid(game_name: str) -> tuple[str | None, str | None]:
    name_lower = game_name.lower().strip()


    steam_path = _find_steam_path()
    if steam_path:
        for g in _get_steam_games(steam_path):
            if name_lower in g["name"].lower():
                return g["id"], g["name"]

    if name_lower in _KNOWN_APPIDS:
        app_id, canonical = _KNOWN_APPIDS[name_lower]
        print(f"[GameUpdater] 📖 Bilinen: {canonical} ({app_id})")
        return app_id, canonical

    for key, (app_id, canonical) in _KNOWN_APPIDS.items():
        if name_lower in key or key in name_lower:
            print(f"[GameUpdater] 📖 Partial match: {canonical} ({app_id})")
            return app_id, canonical

    try:
        import urllib.request, urllib.parse
        query = urllib.parse.quote(game_name)
        url   = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
        req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            items = json.loads(resp.read().decode()).get("items", [])
        if items:
            best = items[0]
            print(f"[GameUpdater] 🌐 Store API: {best['name']} ({best['id']})")
            return str(best["id"]), best["name"]
    except Exception as e:
        print(f"[GameUpdater] ⚠️ AppID lookup failed: {e}")

    return None, None

def _update_steam_games(steam_path: Path, game_name: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."

    exe   = _steam_exe(steam_path)
    games = _get_steam_games(steam_path)
    if not games:
        return "No Steam games found."

    if game_name:
        name_lower = game_name.lower()
        targets    = [g for g in games if name_lower in g["name"].lower()]
        if not targets:
            available = ", ".join(g["name"] for g in games[:5])
            return f"Game '{game_name}' not found. Installed: {available}..."
    else:
        targets = games

    already_updated, already_running, update_started, errors = [], [], [], []

    for game in targets:
        state = game["state"]
        name  = game["name"]
        if state == 4:
            already_updated.append(name)
        elif state == 1026:
            already_running.append(name)
        else:
            try:
                _launch_steam_url(exe, f"steam://update/{game['id']}")
                update_started.append(name)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"{name}: {e}")

    parts = []
    if update_started:
        names  = ", ".join(update_started[:3])
        suffix = f" and {len(update_started) - 3} more" if len(update_started) > 3 else ""
        parts.append(f"Update started for: {names}{suffix}.")
    if already_running:
        parts.append(f"Already updating: {', '.join(already_running)}.")
    if already_updated:
        parts.append(
            f"{already_updated[0]} is already up to date."
            if game_name else
            f"{len(already_updated)} game(s) already up to date."
        )
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}.")
    return " ".join(parts) if parts else "No games to update."

def _install_steam_game(steam_path: Path, game_name: str = None,
                        app_id: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."

    exe             = _steam_exe(steam_path)
    installed_games = _get_steam_games(steam_path)

    already = None
    if app_id:
        already = next((g for g in installed_games if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        already    = next((g for g in installed_games
                           if name_lower in g["name"].lower()), None)
    else:
        return "Please specify a game name or AppID."

    if already:
        state = already["state"]
        name  = already["name"]
        if state == 4:
            return f"'{name}' is already installed and up to date."
        if state == 1026:
            return f"'{name}' is currently downloading or updating."
        if state in (6, 516):
            _launch_steam_url(exe, f"steam://update/{already['id']}")
            return f"'{name}' has a pending update. Update started."
        return f"'{name}' is already installed."

    if not app_id and game_name:
        found_id, found_name = _search_steam_appid(game_name)
        if not found_id:
            return (f"Could not find '{game_name}' on Steam. "
                    f"Try providing the AppID directly.")
        app_id    = found_id
        game_name = found_name or game_name
        print(f"[GameUpdater] 🔍 Kuruluyor: {game_name} (AppID: {app_id})")

    try:
        _launch_steam_url(exe, f"steam://install/{app_id}")

        if is_windows():
            threading.Thread(
                target=_handle_install_dialog,
                args=(game_name or str(app_id),),
                daemon=True
            ).start()
        return f"Install started for '{game_name}'. Steam will open the download dialog."
    except Exception as e:
        return f"Install failed: {e}"

def _get_download_status(steam_path: Path) -> str:
    games   = _get_steam_games(steam_path)
    active  = [g for g in games if g["state"] == 1026]
    pending = [g for g in games if g["state"] in (6, 516)]
    lines   = []
    if active:
        lines.append(f"Downloading: {', '.join(g['name'] for g in active)}.")
    if pending:
        names  = ", ".join(g["name"] for g in pending[:5])
        suffix = f" and {len(pending) - 5} more" if len(pending) > 5 else ""
        lines.append(f"Pending updates: {names}{suffix}.")
    return " ".join(lines) if lines else "No active downloads or pending updates."


def _launch_steam_game(steam_path: Path, game_name: str = None, app_id: str = None) -> str:
    """
    Protocolo robusto de execução de jogos Steam (duas camadas):

    CAMADA 1 - GUI Automation (Primária):
    1. Garantir Steam rodando e janela ativa
    2. Navegar para aba 'Biblioteca' (Library)
    3. Localizar campo de pesquisa 'Search' e inserir game_name
    4. Identificar jogo nos resultados filtrados e selecioná-lo
    5. Acionar botão 'Jogar' / 'Play'

    CAMADA 2 - URI Protocol (Fallback/Contingência):
    - Se GUI falhar: steam://run/<app_id> direto
    """
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."

    exe = _steam_exe(steam_path)
    installed_games = _get_steam_games(steam_path)

    target_game = None
    if app_id:
        target_game = next((g for g in installed_games if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        target_game = next((g for g in installed_games if name_lower in g["name"].lower()), None)
    else:
        return "Please specify a game name or AppID."

    if not target_game:
        return f"Game '{game_name or app_id}' not found in installed Steam games."

    state = target_game["state"]
    name = target_game["name"]
    game_id = target_game["id"]

    if state == 1026:
        return f"'{name}' is currently downloading/updating. Wait for it to finish."
    if state not in (4, 6, 516):
        return f"'{name}' is not ready to launch (state: {state})."

    print(f"[GameUpdater] 🎮 Iniciando protocolo de lançamento para {name} (AppID: {game_id})")

    # --- CAMADA 1: GUI AUTOMATION (PRIMÁRIA) ---
    if is_windows():
        gui_success = _launch_via_gui_automation(steam_path, exe, name, game_id)
        if gui_success:
            # Após lançar, tentar lidar com launcher específico do jogo (GTA V, Cyberpunk, etc.)
            time.sleep(3)
            try:
                _handle_game_launcher_ui(name)
            except Exception as e:
                print(f"[GameUpdater] ⚠️ Launcher UI handling failed: {e}")
            return f"Launched '{name}' via GUI automation."

    # --- CAMADA 2: URI PROTOCOL (FALLBACK) ---
    print(f"[GameUpdater] 🔄 Fallback: usando URI protocol steam://run/{game_id}")
    try:
        _launch_steam_url(exe, f"steam://run/{game_id}")
        time.sleep(3)
        if is_windows():
            try:
                _handle_game_launcher_ui(name)
            except Exception as e:
                print(f"[GameUpdater] ⚠️ Launcher UI handling failed: {e}")
        return f"Launched '{name}' via URI protocol (fallback)."
    except Exception as e:
        return f"Failed to launch '{name}': {e}"


def _launch_via_gui_automation(steam_path: Path, exe: Path, game_name: str, game_id: str) -> bool:
    """
    Executa fluxo completo de GUI Automation no Steam:
    1. Foca/restaura janela Steam
    2. Clica aba 'Library' / 'Biblioteca'
    3. Foca campo 'Search' / 'Pesquisar' e digita game_name
    4. Seleciona o jogo nos resultados
    5. Clica botão 'Play' / 'Jogar'
    """
    try:
        import pygetwindow as gw
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError:
        print("[GameUpdater] ⚠️ pygetwindow/pyautogui não disponível")
        return False

    # --- 1. LOCALIZAR E ATIVAR JANELA STEAM ---
    steam_win = None
    for _ in range(10):  # Wait up to 5 seconds
        for w in gw.getAllWindows():
            if w.width > 400 and w.height > 300 and w.visible:
                title_lower = w.title.lower()
                if "steam" in title_lower and ("library" in title_lower or "biblioteca" in title_lower or "store" in title_lower or "home" in title_lower or title_lower.strip() == "steam"):
                    steam_win = w
                    break
        if steam_win:
            break
        time.sleep(0.5)

    # Se não achou janela aberta, tentar restaurar da system tray ou reabrir
    if not steam_win:
        print("[GameUpdater] 🔍 Steam window not found, trying to restore from tray...")
        if not _restore_steam_from_tray():
            print("[GameUpdater] ⚠️ Could not restore Steam window")
            return False
        time.sleep(2)
        for w in gw.getAllWindows():
            if w.width > 400 and w.height > 300 and w.visible and "steam" in w.title.lower():
                steam_win = w
                break

    if not steam_win:
        print("[GameUpdater] ❌ Steam window not found after restore attempt")
        return False

    print(f"[GameUpdater] 🖥️ Steam window found: {steam_win.title} ({steam_win.width}x{steam_win.height})")

    try:
        steam_win.activate()
        time.sleep(0.5)
    except Exception:
        pass

    wx, wy = steam_win.left, steam_win.top
    ww, wh = steam_win.width, steam_win.height

    # --- 2. NAVEGAR PARA ABA 'BIBLIOTECA' / 'LIBRARY' ---
    if not _click_steam_tab(steam_win, ["library", "biblioteca"]):
        print("[GameUpdater] ⚠️ Could not click Library tab, trying keyboard shortcut...")
        # Ctrl+2 geralmente abre Library no Steam
        pyautogui.hotkey('ctrl', '2')
        time.sleep(1)

    time.sleep(1)

    # --- 3. LOCALIZAR CAMPO DE PESQUISA E DIGITAR NOME DO JOGO ---
    search_clicked = _click_steam_search_field(steam_win)
    if not search_clicked:
        print("[GameUpdater] ⚠️ Could not click search field, trying keyboard...")
        # Ctrl+F ou Ctrl+K para focar search
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(0.3)

    # Limpar campo e digitar nome do jogo
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.press('delete')
    time.sleep(0.1)
    pyautogui.typewrite(game_name, interval=0.02)
    time.sleep(1.5)  # Aguardar resultados filtrados

    # --- 4. SELECIONAR JOGO NOS RESULTADOS ---
    if not _select_game_in_results(steam_win, game_name):
        print("[GameUpdater] ⚠️ Could not select game in results, trying Enter...")
        pyautogui.press('enter')
        time.sleep(1)

    # --- 5. CLICAR BOTÃO 'PLAY' / 'JOGAR' ---
    if not _click_play_button(steam_win, game_name):
        print("[GameUpdater] ⚠️ Could not click Play button")
        return False

    print(f"[GameUpdater] ✅ GUI Automation successful for {game_name}")
    return True


def _restore_steam_from_tray() -> bool:
    """Tenta restaurar Steam da system tray via pywinauto ou pyautogui."""
    try:
        from pywinauto import Application, findwindows
        # Procurar ícone na system tray
        for _ in range(5):
            try:
                hwnds = findwindows.find_windows(title_re=r"(?i)steam", visible_only=False)
                for hwnd in hwnds:
                    try:
                        app = Application(backend="uia").connect(handle=hwnd)
                        win = app.window(handle=hwnd)
                        if win.exists():
                            # Tentar restaurar
                            win.restore()
                            win.set_focus()
                            return True
                    except Exception:
                        continue
            except Exception:
                pass
            time.sleep(0.5)
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: clicar na área da system tray (canto inferior direito)
    try:
        import pyautogui
        import pygetwindow as gw
        # Tentar achar ícone do Steam na tray
        screen_w, screen_h = pyautogui.size()
        # Área típica da system tray (canto inferior direito)
        pyautogui.click(screen_w - 100, screen_h - 30, button='right')
        time.sleep(0.3)
        # Procurar menu "Open Steam" / "Abrir Steam"
        pyautogui.press('up')
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(1)
        return True
    except Exception:
        pass

    return False


def _click_steam_tab(steam_win, tab_keywords: list[str]) -> bool:
    """Clica na aba especificada (Library/Biblioteca) na janela do Steam."""
    try:
        import pyautogui
        import pygetwindow as gw
        import numpy as np

        wx, wy = steam_win.left, steam_win.top
        ww, wh = steam_win.width, steam_win.height

        # Screenshot da área superior (tabs)
        tab_region_h = int(wh * 0.15)
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, tab_region_h))
        img = np.array(screenshot)

        # Usar OCR simples via template matching ou detecção de texto
        # Por simplicidade, usar posições conhecidas relativas
        # Tabs geralmente ficam no topo: Store, Library, Community, etc.

        # Tentar clicar em posições conhecidas das tabs (relative)
        # Library costuma ser a 2ª tab (índice 1)
        tab_y = wy + tab_region_h // 2
        tab_positions = [
            wx + ww * 0.15,  # Store
            wx + ww * 0.28,  # Library
            wx + ww * 0.41,  # Community
        ]

        # Clicar na posição da Library tab
        pyautogui.click(tab_positions[1], tab_y)
        return True

    except Exception as e:
        print(f"[GameUpdater] ⚠️ Tab click failed: {e}")
        return False


def _click_steam_search_field(steam_win) -> bool:
    """Localiza e clica no campo de pesquisa da Biblioteca."""
    try:
        import pyautogui
        import pygetwindow as gw
        import numpy as np
        import cv2

        wx, wy = steam_win.left, steam_win.top
        ww, wh = steam_win.width, steam_win.height

        # Screenshot da área superior da biblioteca (onde fica o search)
        search_region_h = int(wh * 0.2)
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, search_region_h))
        img = np.array(screenshot)
        h, w = img.shape[:2]

        # Converter para escala de cinza
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Procurar por ícone de lupa / search box (área clara retangular no topo)
        # O campo de search costuma ser uma barra larga no topo central
        search_y1, search_y2 = int(h * 0.05), int(h * 0.6)
        search_x1, search_x2 = int(w * 0.2), int(w * 0.8)
        search_area = gray[search_y1:search_y2, search_x1:search_x2]

        # Threshold para encontrar área clara (campo de input)
        _, thresh = cv2.threshold(search_area, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_box = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 1000 < area < 50000:
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = bw / bh if bh > 0 else 0
                if 5 < aspect < 30:  # Campo de search é bem largo
                    if area > best_area:
                        best_area = area
                        best_box = (x, y, bw, bh)

        if best_box:
            x, y, bw, bh = best_box
            click_x = wx + search_x1 + x + bw // 2
            click_y = wy + search_y1 + y + bh // 2
            pyautogui.click(click_x, click_y)
            return True

        # Fallback: posição relativa conhecida (topo centro)
        fallback_x = wx + ww // 2
        fallback_y = wy + int(wh * 0.08)
        pyautogui.click(fallback_x, fallback_y)
        return True

    except ImportError:
        # Fallback sem OpenCV
        try:
            import pyautogui
            wx, wy = steam_win.left, steam_win.top
            ww, wh = steam_win.width, steam_win.height
            pyautogui.click(wx + ww // 2, wy + int(wh * 0.08))
            return True
        except Exception:
            return False
    except Exception as e:
        print(f"[GameUpdater] ⚠️ Search field click failed: {e}")
        return False


def _select_game_in_results(steam_win, game_name: str) -> bool:
    """Seleciona o jogo nos resultados da pesquisa (primeiro resultado visível)."""
    try:
        import pyautogui
        import pygetwindow as gw
        import numpy as np
        import cv2

        wx, wy = steam_win.left, steam_win.top
        ww, wh = steam_win.width, steam_win.height

        # Screenshot da área de resultados (abaixo do search)
        results_y1 = int(wh * 0.15)
        results_h = int(wh * 0.7)
        screenshot = pyautogui.screenshot(region=(wx, wy + results_y1, ww, results_h))
        img = np.array(screenshot)
        h, w = img.shape[:2]

        # Procurar por itens de jogo (caixas com imagem + texto)
        # Geralmente primeira linha de resultados
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Detectar primeira "linha" de resultado (área com contraste)
        # Clicar no primeiro item visível (geralmente o mais relevante)
        item_y = int(h * 0.15)  # Primeiro resultado
        item_x = int(w * 0.1)   # Início da lista

        # Clicar no primeiro resultado
        click_x = wx + item_x
        click_y = wy + results_y1 + item_y
        pyautogui.click(click_x, click_y)
        time.sleep(0.5)

        # Double-click para garantir seleção/abertura
        pyautogui.click(click_x, click_y)
        return True

    except Exception as e:
        print(f"[GameUpdater] ⚠️ Game selection failed: {e}")
        return False


def _click_play_button(steam_win, game_name: str) -> bool:
    """Clica no botão Play/Jogar na página do jogo."""
    try:
        import pyautogui
        import pygetwindow as gw
        import numpy as np
        import cv2

        wx, wy = steam_win.left, steam_win.top
        ww, wh = steam_win.width, steam_win.height

        # Aguardar página do jogo carregar
        time.sleep(2)

        # Screenshot da área direita/inferior onde fica o botão Play
        # Na página do jogo, o botão Play fica proeminente à direita
        play_y1 = int(wh * 0.3)
        play_x1 = int(ww * 0.5)
        screenshot = pyautogui.screenshot(region=(wx + play_x1, wy + play_y1, ww - play_x1, wh - play_y1))
        img = np.array(screenshot)
        h, w = img.shape[:2]

        # Converter para HSV para detectar botão verde/azul
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Verde (Play button padrão Steam)
        green_lower = np.array([35, 50, 50])
        green_upper = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, green_lower, green_upper)

        # Azul (alternativo)
        blue_lower = np.array([100, 50, 50])
        blue_upper = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)

        combined = green_mask | blue_mask

        # Encontrar contornos de botões
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_btn = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 800 < area < 80000:
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = bw / bh if bh > 0 else 0
                if 2 < aspect < 8:
                    if area > best_area:
                        best_area = area
                        best_btn = (x, y, bw, bh)

        if best_btn:
            x, y, bw, bh = best_btn
            click_x = wx + play_x1 + x + bw // 2
            click_y = wy + play_y1 + y + bh // 2
            pyautogui.click(click_x, click_y)
            print(f"[GameUpdater] 🎮 Play button clicked at ({click_x}, {click_y})")
            return True

        # Fallback: posição conhecida do botão Play (lado direito, meio vertical)
        fallback_x = wx + int(ww * 0.75)
        fallback_y = wy + int(wh * 0.5)
        pyautogui.click(fallback_x, fallback_y)
        print(f"[GameUpdater] 🎮 Fallback Play click at ({fallback_x}, {fallback_y})")
        return True

    except Exception as e:
        print(f"[GameUpdater] ⚠️ Play button click failed: {e}")
        return False


def _handle_game_launcher_ui(game_name: str) -> bool:
    """Detect and click Play button in game launchers (GTA V, Cyberpunk, etc.)."""
    try:
        import pygetwindow as gw
        import pyautogui
        import numpy as np

        # Wait for launcher window to appear
        launcher_keywords = [
            "launcher", "social club", "rockstar", "gta", "cyberpunk",
            "red launcher", "epic games", "ubisoft connect", "ea app"
        ]

        launcher_win = None
        for _ in range(20):  # Wait up to 10 seconds
            time.sleep(0.5)
            for w in gw.getAllWindows():
                if w.width > 300 and w.height > 200 and w.visible:
                    title_lower = w.title.lower()
                    if any(kw in title_lower for kw in launcher_keywords):
                        if game_name.lower() in title_lower or any(kw in title_lower for kw in ["play", "jogar", "launch", "iniciar"]):
                            launcher_win = w
                            break
            if launcher_win:
                break

        if not launcher_win:
            return False

        print(f"[GameUpdater] 🎯 Launcher detected: {launcher_win.title}")
        launcher_win.activate()
        time.sleep(0.5)

        # Take screenshot of launcher window
        wx, wy = launcher_win.left, launcher_win.top
        ww, wh = launcher_win.width, launcher_win.height
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img = np.array(screenshot)
        h, w = img.shape[:2]

        # Look for "Play" / "Jogar" / "Launch" buttons (typically green/blue, bottom area)
        search_y1, search_y2 = int(h * 0.5), h
        search_x1, search_x2 = int(w * 0.1), int(w * 0.9)
        region = img[search_y1:search_y2, search_x1:search_x2]

        # Convert to HSV for better color detection
        import cv2
        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)

        # Green play button range (typical Steam/launcher play buttons)
        green_lower = np.array([35, 50, 50])
        green_upper = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, green_lower, green_upper)

        # Blue play button range
        blue_lower = np.array([100, 50, 50])
        blue_upper = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)

        # Orange/red (some launchers)
        red_lower1 = np.array([0, 50, 50])
        red_upper1 = np.array([10, 255, 255])
        red_lower2 = np.array([170, 50, 50])
        red_upper2 = np.array([180, 255, 255])
        red_mask = cv2.inRange(hsv, red_lower1, red_upper1) | cv2.inRange(hsv, red_lower2, red_upper2)

        combined_mask = green_mask | blue_mask | red_mask

        # Find contours (button-like shapes)
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_button = None
        best_area = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 500 < area < 50000:  # Reasonable button size
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = bw / bh if bh > 0 else 0
                if 1.5 < aspect < 6:  # Button-like aspect ratio
                    if area > best_area:
                        best_area = area
                        best_button = (x, y, bw, bh)

        if best_button:
            x, y, bw, bh = best_button
            # Click center of detected button
            click_x = wx + search_x1 + x + bw // 2
            click_y = wy + search_y1 + y + bh // 2
            print(f"[GameUpdater] 🎮 Clicking Play button at ({click_x}, {click_y})")
            pyautogui.click(click_x, click_y)
            return True

        # Fallback: click bottom center of launcher window (common Play button position)
        fallback_x = wx + ww // 2
        fallback_y = wy + int(wh * 0.85)
        print(f"[GameUpdater] 🎮 Fallback click at ({fallback_x}, {fallback_y})")
        pyautogui.click(fallback_x, fallback_y)
        return True

    except ImportError:
        print("[GameUpdater] ⚠️ cv2/pyautogui not available for launcher UI")
        return False
    except Exception as e:
        print(f"[GameUpdater] ⚠️ Launcher UI error: {e}")
        return False


def _system_shutdown() -> None:
    if is_windows():
        subprocess.run(["shutdown", "/s", "/t", "10"], **_CNW)
    elif is_mac():
        subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.run(["systemctl", "poweroff"])


def _watch_and_shutdown(steam_path: Path, speak=None,
                        check_interval: int = 30, timeout_hours: int = 12):
    print("[GameUpdater]...")
    deadline = time.time() + timeout_hours * 3600

    for _ in range(24):
        time.sleep(5)
        active = [g for g in _get_steam_games(steam_path) if g["state"] == 1026]
        if active:
            names = ", ".join(g["name"] for g in active)
            if speak:
                speak(f"Download started for {names}. I'll shut down when done.")
            break
    else:
        return  

    while time.time() < deadline:
        time.sleep(check_interval)
        if not any(g["state"] == 1026 for g in _get_steam_games(steam_path)):
            if speak:
                speak("Download complete. Shutting down now.")
            time.sleep(5)
            _system_shutdown()
            return

    if speak:
        speak("Download taking too long. Cancelling auto-shutdown.")


def _find_epic_exe() -> Path | None:
    if is_windows(): return _find_epic_exe_windows()
    if is_mac():     return _find_epic_exe_mac()
    return _find_epic_exe_linux()


def _find_epic_exe_windows() -> Path | None:
    try:
        import winreg
        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "AppDataPath")
                winreg.CloseKey(key)
                exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
                if exe.exists():
                    return exe
            except Exception:
                continue
    except ImportError:
        pass
    for candidate in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        Path(os.environ.get("ProgramFiles", ""))       / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))        / "EpicGamesLauncher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_epic_exe_mac() -> Path | None:
    p = Path("/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher")
    return p if p.exists() else None


def _find_epic_exe_linux() -> Path | None:
    for c in [Path.home() / ".local" / "bin" / "heroic", Path("/usr/bin/heroic")]:
        if c.exists():
            return c
    return None


def _epic_manifests_path() -> Path | None:
    if is_windows():
        p = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) \
            / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        return p if p.exists() else None
    if is_mac():
        p = Path.home() / "Library" / "Application Support" \
            / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        return p if p.exists() else None
    return None  


def _get_epic_games() -> list[dict]:
    manifests = _epic_manifests_path()
    if not manifests:
        return []
    games = []
    for item_file in manifests.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({"id": data.get("AppName", ""), "name": name})
        except Exception:
            continue
    return games


def _is_epic_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq EpicGamesLauncher.exe"],
                capture_output=True, text=True, **_CNW
            ).stdout
            return "epicgameslauncher.exe" in out.lower()
        proc = "EpicGamesLauncher" if is_mac() else "heroic"
        return bool(subprocess.run(["pgrep", "-x", proc],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        return False


def _update_epic_games(epic_exe: Path, game_name: str = None) -> str:
    games = _get_epic_games()

    if game_name:
        name_lower = game_name.lower()
        matched    = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            return f"'{game_name}' not found in Epic."
        try:
            url = f"com.epicgames.launcher://apps/{matched[0]['id']}?action=launch&silent=true"
            if is_mac():
                subprocess.Popen(["open", url])
            elif is_linux():
                subprocess.Popen([str(epic_exe), url] if epic_exe else ["xdg-open", url])
            else:
                subprocess.Popen([str(epic_exe), url])
            return f"Opened Epic for '{matched[0]['name']}'."
        except Exception as e:
            return f"Epic update failed: {e}"
    else:
        try:
            if is_mac():
                subprocess.Popen(["open", "-a", "Epic Games Launcher"])
            elif is_linux():
                if epic_exe:
                    subprocess.Popen([str(epic_exe)])
                else:
                    return ("Epic Games is not natively supported on Linux. "
                            "Consider using Heroic Launcher.")
            else:

                if _is_epic_running():
                    for g in games[:10]:
                        subprocess.Popen([str(epic_exe),
                            f"com.epicgames.launcher://apps/{g['id']}?action=launch&silent=true"])
                        time.sleep(0.5)
                    return f"Triggered update check for {len(games)} Epic game(s)."
                else:
                    subprocess.Popen([str(epic_exe)])
            count = len(games)
            return (f"Epic Games Launcher opened. {count} game(s) will be checked."
                    if count else "Epic Games Launcher opened.")
        except Exception as e:
            return f"Epic launch failed: {e}"

def _schedule_daily_update(hour: int = 3, minute: int = 0) -> str:
    if is_windows(): return _schedule_windows(hour, minute)
    if is_mac():     return _schedule_mac(hour, minute)
    return _schedule_linux(hour, minute)


def _schedule_windows(hour: int, minute: int) -> str:
    task_name   = "JARVIS_GameUpdater"
    script_path = Path(__file__).resolve()
    subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True, **_CNW)
    for extra in (["/RL", "HIGHEST", "/RU", "SYSTEM"], []):
        cmd    = ["schtasks", "/Create", "/TN", task_name,
                  "/TR", f'"{sys.executable}" "{script_path}" --scheduled',
                  "/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}", "/F", *extra]
        result = subprocess.run(cmd, capture_output=True, text=True, **_CNW)
        if result.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d}."
    return f"Scheduling failed: {result.stderr.strip()}"


def _schedule_mac(hour: int, minute: int) -> str:
    plist_dir   = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path  = plist_dir / "com.jarvis.gameupdater.plist"
    script_path = Path(__file__).resolve()
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.jarvis.gameupdater</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
        <string>--scheduled</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{hour}</integer>
        <key>Minute</key><integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key><false/>
</dict></plist>"""
    try:
        plist_path.write_text(plist_content, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        result = subprocess.run(["launchctl", "load", str(plist_path)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d} via launchd."
        return f"Scheduling failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _schedule_linux(hour: int, minute: int) -> str:
    script_path = Path(__file__).resolve()
    marker      = "# JARVIS_GameUpdater"
    cron_entry  = f"{minute} {hour} * * * {sys.executable} {script_path} --scheduled  {marker}"
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines    = [l for l in existing.stdout.splitlines()
                    if marker not in l and str(script_path) not in l]
        lines.append(cron_entry)
        proc = subprocess.run(["crontab", "-"],
                              input="\n".join(lines) + "\n",
                              text=True, capture_output=True)
        if proc.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d} via cron."
        return f"Scheduling failed: {proc.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _cancel_scheduled_update() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", "JARVIS_GameUpdater", "/F"],
            capture_output=True, text=True, **_CNW
        )
        return ("Scheduled update cancelled."
                if result.returncode == 0 else "No scheduled update found.")
    if is_mac():
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.jarvis.gameupdater.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            return "Scheduled update cancelled."
        return "No scheduled update found."

    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines    = [l for l in existing.stdout.splitlines()
                    if "JARVIS_GameUpdater" not in l]
        subprocess.run(["crontab", "-"],
                       input="\n".join(lines) + "\n", text=True)
        return "Scheduled update cancelled."
    except Exception as e:
        return f"Cancel failed: {e}"


def _get_schedule_status() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", "JARVIS_GameUpdater", "/FO", "LIST"],
            capture_output=True, text=True, **_CNW
        )
        if result.returncode != 0:
            return "No scheduled game update found."
        for line in result.stdout.strip().splitlines():
            if any(k in line for k in
                   ("Next Run", "Sonraki", "Prochaine", "Próxima", "Nächste")):
                return f"Game update scheduled. {line.strip()}"
        return "Game update is scheduled."
    if is_mac():
        plist_path = (Path.home() / "Library" / "LaunchAgents"
                      / "com.jarvis.gameupdater.plist")
        return ("Game update is scheduled via launchd."
                if plist_path.exists() else "No scheduled game update found.")

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "JARVIS_GameUpdater" in result.stdout:
            for line in result.stdout.splitlines():
                if "JARVIS_GameUpdater" in line:
                    return f"Game update is scheduled: {line.split('#')[0].strip()}"
        return "No scheduled game update found."
    except Exception:
        return "No scheduled game update found."


def game_updater(parameters: dict, player=None, speak=None) -> str:
    p         = parameters or {}
    action    = p.get("action",    "update").lower().strip()
    platform  = p.get("platform",  "both").lower().strip()
    game_name = (p.get("game_name") or "").strip() or None
    app_id    = (p.get("app_id")    or "").strip() or None
    hour      = int(p.get("hour",   3))
    minute    = int(p.get("minute", 0))
    shutdown  = str(p.get("shutdown_when_done", "false")).lower() == "true"

    results = []

    if action == "schedule":        return _schedule_daily_update(hour=hour, minute=minute)
    if action == "cancel_schedule": return _cancel_scheduled_update()
    if action == "schedule_status": return _get_schedule_status()

    if action == "list":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                games = _get_steam_games(steam_path)
                if games:
                    names  = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games) - 8} more" if len(games) > 8 else ""
                    results.append(f"Steam ({len(games)} games): {names}{suffix}.")
                else:
                    results.append("Steam: No games found.")
            else:
                results.append("Steam: Not installed.")
        if platform in ("epic", "both"):
            if is_linux():
                results.append("Epic: Not natively supported on Linux.")
            else:
                games = _get_epic_games()
                if games:
                    names  = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games) - 8} more" if len(games) > 8 else ""
                    results.append(f"Epic ({len(games)} games): {names}{suffix}.")
                else:
                    results.append("Epic: No games found.")
        return " | ".join(results) or "No platforms found."

    if action == "download_status":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            results.append(
                _get_download_status(steam_path) if steam_path else "Steam: Not installed."
            )
        if platform in ("epic", "both"):
            results.append("Epic download status not available directly.")
        return " ".join(results)

    if action == "launch":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam: Not installed.")
            else:
                if game_name or app_id:
                    msg = _launch_steam_game(steam_path, game_name=game_name, app_id=app_id)
                    results.append(f"Steam: {msg}")
                else:
                    results.append("Steam: Please specify a game name or AppID to launch.")
        if platform in ("epic", "both"):
            results.append("Epic launch not implemented yet.")
        return " | ".join(results) or "Nothing to launch."

    if action in ("install", "update"):
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam: Not installed.")
            else:
                if game_name:
                    installed  = _get_steam_games(steam_path)
                    name_lower = game_name.lower()
                    is_installed = any(
                        name_lower in g["name"].lower() for g in installed
                    )
                    if not is_installed:
                        msg = _install_steam_game(
                            steam_path, game_name=game_name, app_id=app_id
                        )
                        if shutdown:
                            threading.Thread(
                                target=_watch_and_shutdown,
                                kwargs={"steam_path": steam_path, "speak": speak},
                                daemon=True
                            ).start()
                            msg += " Auto-shutdown enabled."
                        if player: player.write_log(f"[GameUpdater] {msg[:100]}")
                        if speak:  speak(msg)
                        return msg
                    else:
                        results.append(
                            f"Steam: {_update_steam_games(steam_path, game_name=game_name)}"
                        )
                else:
                    if action == "install":
                        results.append("Steam: Please specify a game name to install.")
                    else:
                        results.append(f"Steam: {_update_steam_games(steam_path)}")

                if shutdown:
                    threading.Thread(
                        target=_watch_and_shutdown,
                        kwargs={"steam_path": steam_path, "speak": speak},
                        daemon=True
                    ).start()
                    results.append("Auto-shutdown enabled.")

        if platform in ("epic", "both"):
            if is_linux():
                results.append(
                    "Epic: Not natively supported on Linux. Use Heroic Launcher."
                )
            else:
                epic_exe = _find_epic_exe()
                if epic_exe:
                    results.append(
                        f"Epic: {_update_epic_games(epic_exe, game_name=game_name)}"
                    )
                else:
                    results.append("Epic: Not installed.")

        output = " | ".join(results) or "Nothing to do."
        if player: player.write_log(f"[GameUpdater] {output[:100]}")
        if speak:  speak(output)
        return output

    return f"Unknown action: '{action}'."


if __name__ == "__main__":
    if "--scheduled" in sys.argv:
        print(f"[GameUpdater] 🕐 Scheduled run at {datetime.now().strftime('%H:%M')}")
        result = game_updater({"action": "update", "platform": "both"})
        print(f"[GameUpdater] ✅ {result}")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "game_updater",
    "description": "THE ONLY tool for ANY Steam or Epic Games request. Use for: installing, downloading, updating games, listing installed games, checking download status, scheduling updates. ALWAYS call directly for any Steam/Epic/game request. NEVER use browser_control or web_search for Steam/Epic.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "update | install | launch | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"
            },
            "platform": {
                "type": "STRING",
                "description": "steam | epic | both (default: both)"
            },
            "game_name": {
                "type": "STRING",
                "description": "Game name (partial match supported)"
            },
            "app_id": {
                "type": "STRING",
                "description": "Steam AppID for install (optional)"
            },
            "hour": {
                "type": "INTEGER",
                "description": "Hour for scheduled update 0-23 (default: 3)"
            },
            "minute": {
                "type": "INTEGER",
                "description": "Minute for scheduled update 0-59 (default: 0)"
            },
            "shutdown_when_done": {
                "type": "BOOLEAN",
                "description": "Shut down PC when download finishes"
            }
        },
        "required": []
    },
    "handler": game_updater,
}
