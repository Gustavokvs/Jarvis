"""
Calendar Tool - Google Calendar local / CalDAV integration
Para: criar eventos, listar, verificar conflitos, lembretes.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
import sys

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

try:
    import caldav
    HAS_CALDAV = True
except ImportError:
    HAS_CALDAV = False

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_FILE = BASE_DIR / "config" / "google_token.json"
CREDS_FILE = BASE_DIR / "config" / "google_credentials.json"
CALDAV_CONFIG = BASE_DIR / "config" / "caldav.json"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarProvider:
    """Provedor de calendário - Google Calendar ou CalDAV local."""

    def __init__(self):
        self.service = None
        self.caldav_client = None
        self._mode = "none"  # "google" | "caldav" | "local"

    def setup_google(self) -> bool:
        """Configura Google Calendar OAuth."""
        if not HAS_GOOGLE:
            print("[Calendar] ❌ google-api-python-client não instalado")
            return False

        creds = None
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except:
                    creds = None
            if not creds:
                if not CREDS_FILE.exists():
                    print("[Calendar] ❌ google_credentials.json não encontrado em config/")
                    print("   Baixe do Google Cloud Console > Credentials > OAuth 2.0 Client")
                    return False
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)

            TOKEN_FILE.write_text(creds.to_json())

        try:
            self.service = build("calendar", "v3", credentials=creds)
            self._mode = "google"
            print("[Calendar] ✅ Google Calendar conectado")
            return True
        except Exception as e:
            print(f"[Calendar] ❌ Google connect failed: {e}")
            return False

    def setup_caldav(self, url: str, username: str, password: str) -> bool:
        """Configura CalDAV (Nextcloud, ownCloud, Radicale, etc.)."""
        if not HAS_CALDAV:
            print("[Calendar] ❌ caldav não instalado. pip install caldav")
            return False

        try:
            self.caldav_client = caldav.DAVClient(url=url, username=username, password=password)
            principal = self.caldav_client.principal()
            calendars = principal.calendars()
            if calendars:
                self.calendar = calendars[0]  # usa o primeiro
                self._mode = "caldav"
                print(f"[Calendar] ✅ CalDAV conectado: {len(calendars)} calendários")
                return True
        except Exception as e:
            print(f"[Calendar] ❌ CalDAV failed: {e}")
        return False

    def load_config(self) -> bool:
        """Carrega config salva (CalDAV)."""
        if CALDAV_CONFIG.exists():
            try:
                cfg = json.loads(CALDAV_CONFIG.read_text(encoding="utf-8"))
                return self.setup_caldav(cfg["url"], cfg["username"], cfg["password"])
            except:
                pass
        return False

    def save_caldav_config(self, url: str, username: str, password: str):
        CALDAV_CONFIG.write_text(json.dumps({
            "url": url, "username": username, "password": password
        }, indent=2), encoding="utf-8")

    # --- Operações unificadas ---

    def create_event(self, summary: str, start: datetime, end: datetime,
                     description: str = "", location: str = "",
                     reminders: List[int] = None) -> Dict:
        """Cria evento. reminders = minutos antes [10, 30, 60]."""
        if self._mode == "google":
            return self._create_google(summary, start, end, description, location, reminders)
        elif self._mode == "caldav":
            return self._create_caldav(summary, start, end, description, location, reminders)
        else:
            return {"error": "Nenhum calendário configurado. Use setup_google ou setup_caldav."}

    def _create_google(self, summary, start, end, description, location, reminders):
        event = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"},
        }
        if reminders:
            event["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": m} for m in reminders]
            }
        created = self.service.events().insert(calendarId="primary", body=event).execute()
        return {"id": created["id"], "link": created.get("htmlLink"), "status": "created"}

    def _create_caldav(self, summary, start, end, description, location, reminders):
        from icalendar import Calendar, Event, vText
        import uuid

        cal = Calendar()
        cal.add("prodid", "-//Ramma//Calendar//PT")
        cal.add("version", "2.0")

        event = Event()
        event.add("uid", str(uuid.uuid4()))
        event.add("summary", summary)
        event.add("dtstart", start)
        event.add("dtend", end)
        if description:
            event.add("description", description)
        if location:
            event.add("location", vText(location))
        if reminders:
            from icalendar import Alarm
            for m in reminders:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("trigger", timedelta(minutes=-m))
                alarm.add("description", summary)
                event.add_component(alarm)

        cal.add_component(event)
        ical_data = cal.to_ical()

        new_event = self.calendar.add_event(ical_data)
        return {"id": new_event.url, "status": "created"}

    def list_events(self, days_ahead: int = 7, max_results: int = 20) -> List[Dict]:
        """Lista eventos próximos."""
        now = datetime.utcnow().isoformat() + "Z"
        later = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

        if self._mode == "google":
            events = self.service.events().list(
                calendarId="primary", timeMin=now, timeMax=later,
                maxResults=max_results, singleEvents=True, orderBy="startTime"
            ).execute().get("items", [])
            return [{
                "id": e["id"],
                "summary": e.get("summary", "(sem título)"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
                "location": e.get("location", ""),
                "link": e.get("htmlLink", "")
            } for e in events]

        elif self._mode == "caldav":
            results = []
            for event in self.calendar.date_search(
                datetime.utcnow(), datetime.utcnow() + timedelta(days=days_ahead)
            ):
                vevent = event.vobject_instance.vevent
                results.append({
                    "id": event.url,
                    "summary": str(vevent.summary.value),
                    "start": vevent.dtstart.value.isoformat() if hasattr(vevent.dtstart.value, "isoformat") else str(vevent.dtstart.value),
                    "end": vevent.dtend.value.isoformat() if hasattr(vevent.dtend.value, "isoformat") else str(vevent.dtend.value),
                })
            return results[:max_results]

        return []

    def check_conflicts(self, start: datetime, end: datetime) -> List[Dict]:
        """Verifica conflitos no horário."""
        events = self.list_events(days_ahead=1, max_results=50)
        conflicts = []
        for e in events:
            try:
                e_start = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
                e_end = datetime.fromisoformat(e["end"].replace("Z", "+00:00"))
                if start < e_end and end > e_start:  # overlap
                    conflicts.append(e)
            except:
                pass
        return conflicts

    def delete_event(self, event_id: str) -> bool:
        if self._mode == "google":
            try:
                self.service.events().delete(calendarId="primary", eventId=event_id).execute()
                return True
            except:
                return False
        elif self._mode == "caldav":
            try:
                event = self.calendar.event_by_url(event_id)
                event.delete()
                return True
            except:
                return False
        return False


_calendar: Optional[CalendarProvider] = None


def get_calendar() -> CalendarProvider:
    global _calendar
    if _calendar is None:
        _calendar = CalendarProvider()
        # Tenta carregar config salva
        _calendar.load_config()
    return _calendar


def calendar_tool(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Gerencia calendário: create, list, conflicts, delete, setup."""
    params = parameters or {}
    op = params.get("operation", "list").lower()

    cal = get_calendar()

    if op == "setup_google":
        if cal.setup_google():
            return "✅ Google Calendar configurado e conectado"
        return "❌ Falha ao configurar Google Calendar. Verifique config/google_credentials.json"

    elif op == "setup_caldav":
        url = params.get("url", "").strip()
        user = params.get("username", "").strip()
        pwd = params.get("password", "").strip()
        if not all([url, user, pwd]):
            return "Forneça url, username, password do servidor CalDAV"
        if cal.setup_caldav(url, user, pwd):
            cal.save_caldav_config(url, user, pwd)
            return "✅ CalDAV configurado e conectado"
        return "❌ Falha ao conectar CalDAV"

    elif op == "create":
        try:
            summary = params.get("summary", "").strip()
            start_str = params.get("start", "").strip()  # ISO format
            end_str = params.get("end", "").strip()
            desc = params.get("description", "")
            loc = params.get("location", "")
            reminders = params.get("reminders", [10, 30])  # default 10 e 30 min

            if not summary or not start_str or not end_str:
                return "Forneça: summary, start (ISO), end (ISO). Ex: '2025-01-15T14:00:00'"

            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)

            # Verifica conflitos
            conflicts = cal.check_conflicts(start, end)
            if conflicts:
                conflict_str = ", ".join([c["summary"] for c in conflicts[:3]])
                return f"⚠️ Conflito detectado com: {conflict_str}. Quer mesmo criar?"

            result = cal.create_event(summary, start, end, desc, loc, reminders)
            if "error" in result:
                return result["error"]
            return f"✅ Evento criado: {summary} — {start.strftime('%d/%m %H:%M')} a {end.strftime('%H:%M')}"
        except Exception as e:
            return f"Erro ao criar evento: {e}"

    elif op == "list":
        days = params.get("days", 7)
        events = cal.list_events(days_ahead=days)
        if not events:
            return f"📅 Nenhum evento nos próximos {days} dias."
        lines = [f"📅 Próximos {days} dias:"]
        for e in events:
            try:
                start = datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
                fmt = start.strftime("%d/%m %H:%M")
            except:
                fmt = e["start"]
            lines.append(f"  • {fmt} — {e['summary']}" + (f" @ {e['location']}" if e.get("location") else ""))
        return "\n".join(lines)

    elif op == "conflicts":
        start_str = params.get("start", "").strip()
        end_str = params.get("end", "").strip()
        if not start_str or not end_str:
            return "Forneça start e end (ISO)"
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        conflicts = cal.check_conflicts(start, end)
        if not conflicts:
            return "✅ Sem conflitos nesse horário."
        return "⚠️ Conflitos: " + ", ".join([f'{c["summary"]} ({c["start"]})' for c in conflicts])

    elif op == "delete":
        eid = params.get("id", "").strip()
        if not eid:
            return "Forneça o id do evento"
        if cal.delete_event(eid):
            return "🗑️ Evento removido"
        return "❌ Falha ao remover (verifique ID)"

    elif op == "status":
        return f"Modo: {cal._mode}" + (f" — Google OK" if cal._mode == "google" else "")

    return "Operações: setup_google, setup_caldav (url,username,password), create (summary,start,end,description,location,reminders), list (days), conflicts (start,end), delete (id), status"


TOOL = {
    "name": "calendar",
    "description": "Gerencia calendário (Google Calendar ou CalDAV). Ops: setup_google, setup_caldav(url,username,password), create(summary,start_ISO,end_ISO,description,location,reminders[]), list(days), conflicts(start_ISO,end_ISO), delete(id), status.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "setup_google | setup_caldav | create | list | conflicts | delete | status"},
            "summary": {"type": "STRING"},
            "start": {"type": "STRING", "description": "ISO datetime: 2025-01-15T14:00:00"},
            "end": {"type": "STRING", "description": "ISO datetime"},
            "description": {"type": "STRING"},
            "location": {"type": "STRING"},
            "reminders": {"type": "ARRAY", "items": {"type": "INTEGER"}, "description": "Minutos antes: [10, 30, 60]"},
            "url": {"type": "STRING"},
            "username": {"type": "STRING"},
            "password": {"type": "STRING"},
            "days": {"type": "INTEGER", "description": "Para list"},
            "id": {"type": "STRING", "description": "Event ID para delete"},
        },
        "required": ["operation"],
    },
    "handler": calendar_tool,
}