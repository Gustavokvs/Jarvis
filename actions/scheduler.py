"""
Scheduler Action - Rotinas programadas e aprendizado de padrões
Permite: "todo dia 9h abre Discord", "seg-sex 18h verifica updates Steam"
"""
import json
import time
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional, Any
import croniter
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEDULE_FILE = BASE_DIR / "memory" / "schedules.json"
PATTERN_FILE = BASE_DIR / "memory" / "usage_patterns.json"

try:
    from core.action_loader import discover_actions
except Exception:
    def discover_actions(actions_dir, reserved_names, logger): return None


class ScheduleEngine:
    """Motor de agendamento com suporte a cron expressions."""

    def __init__(self, action_registry=None):
        self.action_registry = action_registry
        self.schedules: List[Dict] = []
        self.patterns: Dict = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._load()

    def _load(self):
        """Carrega agendamentos e padrões salvos."""
        try:
            if SCHEDULE_FILE.exists():
                self.schedules = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if PATTERN_FILE.exists():
                self.patterns = json.loads(PATTERN_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Scheduler] Load error: {e}")
            self.schedules = []
            self.patterns = {}

    def _save(self):
        """Salva agendamentos e padrões."""
        try:
            SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SCHEDULE_FILE.write_text(json.dumps(self.schedules, ensure_ascii=False, indent=2), encoding="utf-8")
            PATTERN_FILE.write_text(json.dumps(self.patterns, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Scheduler] Save error: {e}")

    def add_schedule(self, name: str, cron_expr: str, action: str, params: Dict = None, enabled: bool = True) -> Dict:
        """Adiciona um agendamento.
        cron_expr exemplos:
          "0 9 * * 1-5"     = todo dia útil às 9h
          "0 18 * * *"      = todo dia às 18h
          "0 */2 * * *"     = a cada 2 horas
          "@daily"          = diário meia-noite
        """
        schedule = {
            "id": f"sched_{int(time.time()*1000)}",
            "name": name,
            "cron": cron_expr,
            "action": action,
            "params": params or {},
            "enabled": enabled,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "next_run": self._calc_next(cron_expr)
        }
        self.schedules.append(schedule)
        self._save()
        print(f"[Scheduler] ⏰ Added: {name} ({cron_expr}) → {action}")
        return schedule

    def remove_schedule(self, schedule_id: str) -> bool:
        self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
        self._save()
        return True

    def list_schedules(self) -> List[Dict]:
        return sorted(self.schedules, key=lambda s: s.get("next_run", ""))

    def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        for s in self.schedules:
            if s["id"] == schedule_id:
                s["enabled"] = enabled
                s["next_run"] = self._calc_next(s["cron"]) if enabled else None
                self._save()
                return True
        return False

    def _calc_next(self, cron_expr: str) -> Optional[str]:
        try:
            base = datetime.now()
            if cron_expr.startswith("@"):
                # Simplificado para @daily, @hourly
                if cron_expr == "@daily":
                    next_run = base.replace(hour=0, minute=0, second=0, microsecond=0)
                    if next_run <= base:
                        from datetime import timedelta
                        next_run += timedelta(days=1)
                    return next_run.isoformat()
            else:
                iter = croniter.croniter(cron_expr, base)
                return iter.get_next(datetime).isoformat()
        except:
            return None
        return None

    def record_app_usage(self, app_name: str, timestamp: datetime = None):
        """Registra uso de app para aprender padrões."""
        ts = timestamp or datetime.now()
        key = app_name.lower()
        if key not in self.patterns:
            self.patterns[key] = {"count": 0, "hours": {}, "days": {}}
        self.patterns[key]["count"] += 1
        h = ts.hour
        d = ts.weekday()  # 0=seg
        self.patterns[key]["hours"][str(h)] = self.patterns[key]["hours"].get(str(h), 0) + 1
        self.patterns[key]["days"][str(d)] = self.patterns[key]["days"].get(str(d), 0) + 1
        # Salva periodicamente (não a cada call)
        if self.patterns[key]["count"] % 10 == 0:
            self._save()

    def suggest_schedules_from_patterns(self, min_count: int = 5) -> List[Dict]:
        """Analisa padrões e sugere agendamentos."""
        suggestions = []
        for app, data in self.patterns.items():
            if data["count"] < min_count:
                continue
            # Hora mais frequente
            if data["hours"]:
                top_hour = max(data["hours"], key=data["hours"].get)
                hour_count = data["hours"][top_hour]
                if hour_count >= min_count * 0.6:  # 60% das vezes nessa hora
                    # Dias mais frequentes
                    top_days = sorted(data["days"], key=data["days"].get, reverse=True)[:3]
                    day_str = ",".join(top_days) if len(top_days) < 5 else "*"
                    cron = f"0 {top_hour} * * {day_str}"
                    suggestions.append({
                        "app": app,
                        "cron": cron,
                        "confidence": hour_count / data["count"],
                        "suggested_action": "open_app",
                        "params": {"app_name": app}
                    })
        return suggestions

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Scheduler] 🕐 Engine started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self):
        while self._running:
            now = datetime.now()
            for sched in self.schedules:
                if not sched["enabled"]:
                    continue
                next_run = sched.get("next_run")
                if next_run:
                    try:
                        next_dt = datetime.fromisoformat(next_run)
                        if now >= next_dt:
                            self._execute_schedule(sched)
                            sched["last_run"] = now.isoformat()
                            sched["next_run"] = self._calc_next(sched["cron"])
                            self._save()
                    except Exception as e:
                        print(f"[Scheduler] Error checking {sched['name']}: {e}")
            time.sleep(30)  # Check every 30s

    def _execute_schedule(self, sched: Dict):
        """Executa a ação agendada."""
        if not self.action_registry:
            print(f"[Scheduler] No action registry for {sched['name']}")
            return
        action_name = sched["action"]
        params = sched["params"]
        if self.action_registry.has(action_name):
            try:
                print(f"[Scheduler] ⏰ Running: {sched['name']} → {action_name}")
                ctx = {"player": None, "speak": None, "response": None, "session_memory": None}
                result = self.action_registry.run(action_name, params, ctx)
                print(f"[Scheduler] ✅ {sched['name']} done: {result}")
            except Exception as e:
                print(f"[Scheduler] ❌ {sched['name']} failed: {e}")
        else:
            print(f"[Scheduler] Action not found: {action_name}")


_scheduler: Optional[ScheduleEngine] = None


def get_scheduler(action_registry=None) -> ScheduleEngine:
    global _scheduler
    if _scheduler is None:
        _scheduler = ScheduleEngine(action_registry)
    return _scheduler


# Tool declaration for auto-discovery
def scheduler_tool(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Gerencia agendamentos e rotinas automáticas."""
    params = parameters or {}
    op = params.get("operation", "list").lower()

    sched = get_scheduler()

    if op == "add":
        name = params.get("name", "").strip()
        cron = params.get("cron", "").strip()
        action = params.get("action", "").strip()
        params_action = params.get("params", {})
        if not name or not cron or not action:
            return "Forneça: name, cron, action (ex: 'Abrir Discord', '0 9 * * 1-5', 'open_app', {'app_name': 'discord'})"
        s = sched.add_schedule(name, cron, action, params_action)
        return f"Agendado: {name} — {cron} → {action}"

    elif op == "remove":
        sid = params.get("id", "").strip()
        if not sid:
            return "Forneça o id do agendamento"
        sched.remove_schedule(sid)
        return f"Agendamento {sid} removido"

    elif op == "toggle":
        sid = params.get("id", "").strip()
        enabled = params.get("enabled", True)
        if sched.toggle_schedule(sid, enabled):
            return f"Agendamento {sid} {'ativado' if enabled else 'desativado'}"
        return "Agendamento não encontrado"

    elif op == "suggest":
        suggestions = sched.suggest_schedules_from_patterns()
        if not suggestions:
            return "Ainda não tenho dados suficientes para sugerir rotinas. Use os apps normalmente por alguns dias."
        lines = ["📊 Sugestões baseadas no seu uso:"]
        for i, s in enumerate(suggestions, 1):
            lines.append(f"  {i}. {s['app']} — {s['cron']} (confiança: {s['confidence']:.0%})")
        return "\n".join(lines)

    else:  # list
        items = sched.list_schedules()
        if not items:
            return "Nenhum agendamento. Use operation='add' para criar."
        lines = ["⏰ Agendamentos:"]
        for s in items:
            status = "✅" if s["enabled"] else "⏸️"
            nxt = s.get("next_run", "—")
            if nxt != "—":
                try:
                    nxt = datetime.fromisoformat(nxt).strftime("%d/%m %H:%M")
                except:
                    pass
            lines.append(f"  {status} {s['name']} — {s['cron']} → {s['action']} (próximo: {nxt})")
        return "\n".join(lines)


TOOL = {
    "name": "scheduler",
    "description": "Gerencia rotinas automáticas agendadas (cron). Operações: add (name, cron, action, params), remove (id), toggle (id, enabled), list, suggest (analisa padrões de uso e sugere). Exemplos cron: '0 9 * * 1-5' = 9h dias úteis, '0 18 * * *' = 18h todo dia.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "add | remove | toggle | list | suggest"},
            "name": {"type": "STRING", "description": "Nome do agendamento (para add)"},
            "cron": {"type": "STRING", "description": "Expressão cron (para add)"},
            "action": {"type": "STRING", "description": "Nome da action a executar (ex: open_app)"},
            "params": {"type": "OBJECT", "description": "Parâmetros da action (ex: {'app_name': 'discord'})"},
            "id": {"type": "STRING", "description": "ID do agendamento (para remove/toggle)"},
            "enabled": {"type": "BOOLEAN", "description": "true/false (para toggle)"},
        },
        "required": ["operation"],
    },
    "handler": scheduler_tool,
}