"""
Context Bridge - Cross-app contextual awareness
Detecta compromissos no WhatsApp/Discord/email → cria no calendário
Detecta erros no código → busca solução
"""
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any

try:
    from actions.web_search import web_search
except Exception:
    def web_search(params, **kwargs): return "Web search unavailable"

try:
    from actions.calendar import get_calendar
except Exception:
    def get_calendar(): return None

try:
    from memory.memory_manager import save_memory, load_memory
except Exception:
    def save_memory(d): pass
    def load_memory(): return {}

BASE_DIR = Path(__file__).resolve().parent.parent
CONTEXT_FILE = BASE_DIR / "memory" / "context_cache.json"


class ContextBridge:
    """Ponte de contexto entre apps - extrai intenções e age."""

    # Padrões de compromisso em texto
    APPOINTMENT_PATTERNS = [
        r"(?:vamos|marcar|agendar|combinar)\s+(?:para|no dia?|em)\s+(.+?)(?:\s+às|\s+as\s+)(\d{1,2}h?\d{0,2})",
        r"(?:dia|data)\s+(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)\s+(?:às|as)\s+(\d{1,2}h?\d{0,2})",
        r"(?:amanhã|depois de amanhã|na (?:segunda|terça|quarta|quinta|sexta|sábado|domingo))\s+(?:às|as)\s+(\d{1,2}h?\d{0,2})",
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(\d{1,2}:\d{2})",
    ]

    # Padrões de erro de programação
    ERROR_PATTERNS = [
        r"(?:Error|Exception|Traceback|Failed|Erro|Falha|Error:)\s*:?\s*(.+)",
        r"(?:SyntaxError|TypeError|ValueError|AttributeError|ImportError|ModuleNotFoundError)\s*:\s*(.+)",
        r"line\s+\d+.*?(?:Error|Exception)\s*:\s*(.+)",
    ]

    def __init__(self):
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        try:
            if CONTEXT_FILE.exists():
                return json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
        except:
            pass
        return {"appointments": [], "errors": [], "last_scan": 0}

    def _save_cache(self):
        try:
            CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONTEXT_FILE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass

    def scan_screen_for_appointments(self, screen_text: str) -> List[Dict]:
        """Escaneia texto da tela procurando compromissos."""
        found = []
        for pattern in self.APPOINTMENT_PATTERNS:
            matches = re.finditer(pattern, screen_text, re.IGNORECASE)
            for m in matches:
                groups = m.groups()
                if len(groups) >= 2:
                    date_str, time_str = groups[0], groups[1]
                    found.append({
                        "raw": m.group(0),
                        "date_text": date_str,
                        "time_text": time_str,
                        "context": screen_text[max(0,m.start()-100):m.end()+100],
                        "timestamp": datetime.now().isoformat()
                    })
        # Deduplica
        unique = []
        seen = set()
        for f in found:
            key = f["raw"]
            if key not in seen:
                seen.add(key)
                unique.append(f)
        self.cache["appointments"].extend(unique)
        self.cache["appointments"] = self.cache["appointments"][-50:]
        self._save_cache()
        return unique

    def scan_for_errors(self, screen_text: str) -> List[Dict]:
        """Detecta erros de programação na tela."""
        found = []
        for pattern in self.ERROR_PATTERNS:
            matches = re.finditer(pattern, screen_text, re.IGNORECASE | re.MULTILINE)
            for m in matches:
                error_text = m.group(1) if m.groups() else m.group(0)
                found.append({
                    "error": error_text.strip()[:500],
                    "context": screen_text[max(0,m.start()-200):m.end()+200],
                    "timestamp": datetime.now().isoformat()
                })
        unique = []
        seen = set()
        for f in found:
            key = f["error"][:100]
            if key not in seen:
                seen.add(key)
                unique.append(f)
        self.cache["errors"].extend(unique)
        self.cache["errors"] = self.cache["errors"][-30:]
        self._save_cache()
        return unique

    def parse_appointment_to_datetime(self, date_text: str, time_text: str) -> Optional[datetime]:
        """Converte texto solto para datetime."""
        now = datetime.now()
        try:
            # Hora
            time_clean = time_text.lower().replace("h", ":").replace("hs", "").replace("h", ":")
            if ":" not in time_clean:
                time_clean += ":00"
            hour, minute = map(int, time_clean.split(":")[:2])

            # Data
            date_text = date_text.lower().strip()
            if date_text in ["hoje", "today"]:
                date = now.date()
            elif date_text in ["amanhã", "amanha", "tomorrow"]:
                date = (now + timedelta(days=1)).date()
            elif date_text in ["depois de amanhã", "depois de amanha"]:
                date = (now + timedelta(days=2)).date()
            elif date_text in ["segunda", "monday"]:
                days_ahead = (0 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["terça", "terca", "tuesday"]:
                days_ahead = (1 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["quarta", "wednesday"]:
                days_ahead = (2 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["quinta", "thursday"]:
                days_ahead = (3 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["sexta", "friday"]:
                days_ahead = (4 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["sábado", "sabado", "saturday"]:
                days_ahead = (5 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            elif date_text in ["domingo", "sunday"]:
                days_ahead = (6 - now.weekday()) % 7 or 7
                date = (now + timedelta(days=days_ahead)).date()
            else:
                # Tenta parsear data numérica
                for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"]:
                    try:
                        date = datetime.strptime(date_text, fmt).date()
                        break
                    except:
                        continue
                else:
                    return None

            return datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)
        except:
            return None

    def auto_create_appointment(self, title: str, start: datetime, duration_min: int = 60,
                                description: str = "") -> Dict:
        """Cria compromisso no calendário automaticamente."""
        cal = get_calendar()
        if not cal or cal._mode == "none":
            return {"error": "Calendário não configurado"}

        end = start + timedelta(minutes=duration_min)
        conflicts = cal.check_conflicts(start, end)
        if conflicts:
            return {"warning": "Conflito detectado", "conflicts": [c["summary"] for c in conflicts[:3]]}

        result = cal.create_event(
            summary=title,
            start=start,
            end=end,
            description=description,
            reminders=[10, 30]
        )
        return result

    def search_error_solution(self, error_text: str) -> str:
        """Busca solução para erro detectado."""
        query = f"how to fix {error_text[:200]}"
        result = web_search({"query": query, "mode": "research"}, player=None)
        return result

    def process_screen_context(self, screen_text: str, source: str = "screen") -> Dict:
        """Processa contexto completo da tela - ponto de entrada principal."""
        results = {"appointments": [], "errors": [], "actions_taken": []}

        # 1. Compromissos
        appointments = self.scan_screen_for_appointments(screen_text)
        for appt in appointments:
            dt = self.parse_appointment_to_datetime(appt["date_text"], appt["time_text"])
            if dt and dt > datetime.now():
                # Só cria se for futuro e não muito longe (30 dias)
                if (dt - datetime.now()).days <= 30:
                    title = f"Compromisso detectado em {source}"
                    res = self.auto_create_appointment(title, dt, description=appt["context"])
                    results["actions_taken"].append(f"Calendar: {res}")
            results["appointments"].append({**appt, "parsed_datetime": dt.isoformat() if dt else None})

        # 2. Erros
        errors = self.scan_for_errors(screen_text)
        for err in errors:
            # Só busca solução se for erro "real" (não log normal)
            if any(kw in err["error"].lower() for kw in ["error", "exception", "failed", "traceback", "erro", "falha"]):
                sol = self.search_error_solution(err["error"])
                results["actions_taken"].append(f"Error search: {sol[:200]}...")
            results["errors"].append(err)

        return results


_bridge: Optional[ContextBridge] = None


def get_context_bridge() -> ContextBridge:
    global _bridge
    if _bridge is None:
        _bridge = ContextBridge()
    return _bridge


def context_bridge_tool(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Analisa contexto da tela/apps e age: detecta compromissos, erros, busca soluções."""
    params = parameters or {}
    op = params.get("operation", "scan").lower()

    bridge = get_context_bridge()

    if op == "scan":
        text = params.get("text", "").strip()
        source = params.get("source", "screen")
        if not text:
            return "Forneça o texto a analisar (parâmetro 'text')"
        result = bridge.process_screen_context(text, source)
        lines = ["🔍 Análise de contexto:"]
        if result["appointments"]:
            lines.append(f"  📅 {len(result['appointments'])} compromisso(s) detectado(s)")
            for a in result["appointments"][:3]:
                lines.append(f"    - {a['date_text']} {a['time_text']} → {a['parsed_datetime'] or 'não parseado'}")
        if result["errors"]:
            lines.append(f"  🐛 {len(result['errors'])} erro(s) detectado(s)")
            for e in result["errors"][:2]:
                lines.append(f"    - {e['error'][:80]}")
        if result["actions_taken"]:
            lines.append("  ⚡ Ações:")
            for a in result["actions_taken"][:3]:
                lines.append(f"    - {a[:120]}")
        if not result["appointments"] and not result["errors"]:
            lines.append("  Nada detectado.")
        return "\n".join(lines)

    elif op == "create_appointment":
        title = params.get("title", "Compromisso")
        start_str = params.get("start", "").strip()
        duration = params.get("duration", 60)
        desc = params.get("description", "")
        try:
            start = datetime.fromisoformat(start_str)
            res = bridge.auto_create_appointment(title, start, duration, desc)
            return f"Resultado: {json.dumps(res, ensure_ascii=False)}"
        except Exception as e:
            return f"Erro: {e}"

    elif op == "search_error":
        error = params.get("error", "").strip()
        if not error:
            return "Forneça o texto do erro"
        sol = bridge.search_error_solution(error)
        return sol

    elif op == "recent":
        return json.dumps({
            "appointments": bridge.cache["appointments"][-10:],
            "errors": bridge.cache["errors"][-10:]
        }, ensure_ascii=False, indent=2)

    return "Ops: scan (text,source), create_appointment (title,start_ISO,duration,description), search_error (error), recent"


TOOL = {
    "name": "context_bridge",
    "description": "Ponte contextual cross-app. Escaneia texto da tela/conversa e: detecta compromissos → cria no calendário, detecta erros de código → busca solução. Ops: scan(text,source), create_appointment(title,start_ISO,duration,description), search_error(error), recent.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "scan | create_appointment | search_error | recent"},
            "text": {"type": "STRING", "description": "Texto da tela/chat para analisar (scan)"},
            "source": {"type": "STRING", "description": "Origem: screen, whatsapp, discord, etc."},
            "title": {"type": "STRING"},
            "start": {"type": "STRING", "description": "ISO datetime: 2025-01-15T14:00:00"},
            "duration": {"type": "INTEGER", "description": "Minutos (default 60)"},
            "description": {"type": "STRING"},
            "error": {"type": "STRING", "description": "Texto do erro para buscar solução"},
        },
        "required": ["operation"],
    },
    "handler": context_bridge_tool,
}