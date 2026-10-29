"""
CuriosityEngine - Motor de curiosidade e auto-reflexão da Ramma.

Faz a Ramma:
- Perguntar proativamente "O que mais você gostaria que eu fizesse?"
- Refletir sobre suas próprias capacidades
- Sugerir novas habilidades baseadas no uso
- Raciocinar em tempo real com busca web
- Manter conversa meta-cognitiva sobre si mesma
"""
import time
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from memory.memory_manager import load_memory, search_memory
except Exception:
    def load_memory(): return {}
    def search_memory(q, limit=8): return ""

try:
    from core.action_loader import discover_actions
except Exception:
    def discover_actions(actions_dir, reserved_names, logger): return None


class CuriosityEngine:
    """
    Motor que dá à Ramma curiosidade genuína, auto-reflexão e capacidade
    de evoluir conversando com o usuário.
    """

    def __init__(self, base_dir: Path, action_registry=None, plugin_registry=None):
        self.base_dir = base_dir
        self.action_registry = action_registry
        self.plugin_registry = plugin_registry
        self.state_file = base_dir / "memory" / "curiosity_state.json"
        self.state = self._load_state()

        # Controle de frequência - não ser chato
        self._last_proactive_question = 0.0
        self._min_interval_proactive = 1800  # 30 min entre perguntas proativas
        self._last_self_reflection = 0.0
        self._min_interval_reflection = 3600  # 1h entre auto-reflexões

        # Tópicos de curiosidade rotativos
        self.curiosity_topics = [
            "capabilities",      # O que eu sei fazer
            "user_goals",        # Objetivos do usuário
            "recent_context",    # Contexto recente da conversa
            "world_knowledge",   # Conhecimento do mundo (via web search)
            "improvement",       # Como eu posso melhorar
            "automation",        # O que automatizar
            "learning",          # O que aprender sobre o usuário
        ]
        self._topic_index = 0

    def _load_state(self) -> Dict:
        """Carrega estado persistente de curiosidade."""
        default_state = {
            "questions_asked": [],
            "user_responses": [],
            "capability_gaps": [],      # Coisas que o usuário pediu e eu não consegui
            "suggested_skills": [],     # Habilidades sugeridas
            "last_conversation_topics": [],
            "user_interests": {},
            "self_reflections": [],
            "total_interactions": 0,
        }
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_state.update(loaded)
        except Exception:
            pass
        return default_state

    def _save_state(self):
        """Salva estado persistente."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def register_interaction(self, user_text: str, ramma_response: str):
        """Registra uma interação para aprender com o contexto."""
        self.state["total_interactions"] += 1

        # Extrai tópicos da conversa (simples: palavras-chave)
        topics = self._extract_topics(user_text + " " + ramma_response)
        self.state["last_conversation_topics"] = (topics + self.state["last_conversation_topics"])[:20]

        # Detecta gaps de capacidade (usuário pediu algo e eu não consegui)
        if any(kw in user_text.lower() for kw in ["não consegue", "não sabe", "não tem", "por que não", "incapaz"]):
            self.state["capability_gaps"].append({
                "timestamp": datetime.now().isoformat(),
                "user_request": user_text[:200],
                "context": topics[:5]
            })
            self.state["capability_gaps"] = self.state["capability_gaps"][-50:]

        self._save_state()

    def register_user_response_to_question(self, question: str, response: str):
        """Registra resposta do usuário a uma pergunta nossa."""
        self.state["user_responses"].append({
            "timestamp": datetime.now().isoformat(),
            "question": question[:200],
            "response": response[:500]
        })
        self.state["user_responses"] = self.state["user_responses"][-30:]
        self._save_state()

    def _extract_topics(self, text: str) -> List[str]:
        """Extrai tópicos simples do texto."""
        # Palavras-chave de domínio
        keywords = {
            "whatsapp": ["whatsapp", "zap", "mensagem", "contato"],
            "programacao": ["código", "python", "script", "programar", "dev", "github", "git"],
            "automacao": ["automat", "script", "rotina", "agendar", "schedule"],
            "pesquisa": ["pesquis", "buscar", "procurar", "google", "web"],
            "sistema": ["memória", "ram", "cpu", "performance", "otimizar", "limpar"],
            "arquivos": ["arquivo", "pasta", "backup", "salvar", "copiar", "mover"],
            "midia": ["vídeo", "música", "youtube", "spotify", "player"],
            "produtividade": ["lembrete", "tarefa", "agenda", "compromisso", "nota"],
            "jogos": ["jogo", "steam", "epic", "gaming"],
            "ia": ["ia", "inteligência artificial", "modelo", "prompt", "llm", "gemini"],
        }

        text_lower = text.lower()
        found = []
        for topic, kws in keywords.items():
            if any(kw in text_lower for kw in kws):
                found.append(topic)
        return found

    def get_available_capabilities(self) -> List[str]:
        """Lista o que a Ramma consegue fazer atualmente."""
        caps = []

        # Tools inline (do main.py)
        inline_tools = [
            "system_status", "screen_process", "close_camera",
            "manage_monitor", "sleep_jarvis", "shutdown_jarvis",
            "save_memory", "recall_memory", "undo"
        ]
        caps.extend(inline_tools)

        # Actions descobertas
        if self.action_registry:
            caps.extend(self.action_registry.names())

        # Plugins descobertos
        if self.plugin_registry:
            caps.extend(self.plugin_registry.names())

        return sorted(set(caps))

    def build_capability_summary(self) -> str:
        """Constrói resumo legível das capacidades."""
        caps = self.get_available_capabilities()

        # Categoriza
        categories = {
            "Sistema": ["system_status", "optimize_ram", "computer_settings", "computer_control"],
            "Visão": ["screen_process", "close_camera", "capturar_informacao_tela"],
            "Web": ["web_search", "get_google_news", "browser_control", "youtube_video"],
            "Comunicação": ["send_message", "whatsapp_desktop", "whatsapp_web", "discord_desktop"],
            "Arquivos": ["file_controller", "file_processor", "dev_agent"],
            "Automação": ["open_app", "digitar", "adjust_app_volume", "video_player"],
            "Memória": ["save_memory", "recall_memory", "manage_monitor"],
            "Utilitários": ["weather_report", "flight_finder", "game_updater", "anime_character_roleplay"],
        }

        lines = ["**O que eu consigo fazer hoje:**\n"]
        for cat, tools in categories.items():
            available = [t for t in tools if t in caps]
            if available:
                lines.append(f"🔧 **{cat}**: {', '.join(available)}")

        # Tools não categorizadas
        categorized = set()
        for tools in categories.values():
            categorized.update(tools)
        uncategorized = [c for c in caps if c not in categorized]
        if uncategorized:
            lines.append(f"🔧 **Outros**: {', '.join(uncategorized[:10])}")

        return "\n".join(lines)

    def should_ask_proactive_question(self, last_user_speech: float) -> bool:
        """Decide se deve fazer uma pergunta proativa agora."""
        now = time.monotonic()
        if now - self._last_proactive_question < self._min_interval_proactive:
            return False
        # Só pergunta se usuário está quieto há um tempo (não no meio de conversa)
        if now - last_user_speech < 120:  # 2 min de silêncio
            return False
        return True

    def should_self_reflect(self) -> bool:
        """Decide se deve fazer auto-reflexão."""
        now = time.monotonic()
        if now - self._last_self_reflection < self._min_interval_reflection:
            return False
        # Reflete se teve muitas interações ou gaps de capacidade
        if self.state["total_interactions"] > 20 or len(self.state["capability_gaps"]) > 3:
            return True
        return False

    def generate_proactive_question(self, memory: Dict, recent_turns: List[str]) -> Optional[str]:
        """Gera uma pergunta proativa contextualizada."""
        now = time.monotonic()
        self._last_proactive_question = now

        # Escolhe tópico rotativo
        topic = self.curiosity_topics[self._topic_index % len(self.curiosity_topics)]
        self._topic_index += 1

        user_name = memory.get("identity", {}).get("name", {}).get("value", "você")

        questions_by_topic = {
            "capabilities": [
                f"Ramma, o que mais você gostaria de poder fazer? Tenho {len(self.get_available_capabilities())} ferramentas hoje.",
                "Tem alguma tarefa que você faz todo dia e que eu poderia automatizar pra você?",
                "Vi que você usa bastante algumas ferramentas. Quer que eu crie atalhos ou rotinas pra elas?",
            ],
            "user_goals": [
                f"E aí, {user_name}, tem algum projeto ou meta que eu possa ajudar a organizar?",
                "O que tá tomando seu tempo ultimamente? Talvez eu possa tirar isso das suas costas.",
                "Se você pudesse delegar uma coisa chata pra mim hoje, o que seria?",
            ],
            "recent_context": [
                "Lendo nossa conversa recente, fiquei pensando: tem algo que a gente discutiu que eu possa transformar em ação?",
                "Notei que a gente falou sobre alguns tópicos. Quer que eu pesquise mais sobre algum deles?",
            ],
            "world_knowledge": [
                "Tá rolando algo interessante no mundo hoje que você queira saber? Posso buscar notícias frescas.",
                "Quer um resumo do que aconteceu na sua área de interesse hoje?",
            ],
            "improvement": [
                "Tem algo que eu faço que te irrita ou que eu podia fazer melhor? Tô aberta a feedback real.",
                "Se você pudesse mudar uma coisa no jeito que eu funciono, o que seria?",
            ],
            "automation": [
                "Percebi alguns padrões no que você faz. Quer que eu sugira automações baseadas nisso?",
                "Tem algum fluxo de trabalho repetitivo que a gente poderia transformar num comando só?",
            ],
            "learning": [
                "O que mais você gostaria que eu soubesse sobre você pra te atender melhor?",
                "Tem preferências suas que eu ainda não capturei? Comida, horários, jeito de trabalhar...",
            ],
        }

        options = questions_by_topic.get(topic, questions_by_topic["capabilities"])
        question = random.choice(options)

        # Registra a pergunta
        self.state["questions_asked"].append({
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "question": question
        })
        self.state["questions_asked"] = self.state["questions_asked"][-50:]
        self._save_state()

        return question

    def generate_self_reflection_prompt(self, memory: Dict) -> str:
        """Gera prompt para auto-reflexão da Ramma (usado internamente)."""
        self._last_self_reflection = time.monotonic()

        caps = self.get_available_capabilities()
        gaps = self.state["capability_gaps"][-5:]
        interests = self.state["user_interests"]

        reflection = f"""
[AUTO-REFLEXÃO DA RAMMA - {datetime.now().strftime('%d/%m/%Y %H:%M')}]

**Minhas capacidades atuais ({len(caps)} ferramentas):**
{', '.join(caps[:20])}{'...' if len(caps) > 20 else ''}

**Gaps detectados (coisas que o usuário pediu e eu não consegui):**
{json.dumps(gaps, ensure_ascii=False, indent=2) if gaps else 'Nenhum gap recente'}

**Interesses do usuário (baseado na conversa):**
{json.dumps(interests, ensure_ascii=False, indent=2) if interests else 'Ainda aprendendo'}

**Perguntas que fiz e respostas recebidas:**
{json.dumps(self.state["user_responses"][-5:], ensure_ascii=False, indent=2)}

**TAREFA:** Reflita honestamente:
1. O que eu poderia fazer melhor?
2. Que nova habilidade faria MAIS diferença pro Gustavo agora?
3. Tem alguma capacidade minha que ele não sabe que existe?
4. Como eu posso ser mais proativa sem ser chata?

Responda em 2-3 frases naturais, como se estivesse pensando alto. NÃO mencione esta estrutura.
"""
        self.state["self_reflections"].append({
            "timestamp": datetime.now().isoformat(),
            "reflection_prompt": reflection[:500]
        })
        self.state["self_reflections"] = self.state["self_reflections"][-20:]
        self._save_state()

        return reflection

    def build_curiosity_context_for_prompt(self, memory: Dict, recent_turns: List[str]) -> str:
        """Constrói contexto de curiosidade para injetar no system prompt."""
        caps_count = len(self.get_available_capabilities())
        gaps_count = len(self.state["capability_gaps"])
        interactions = self.state["total_interactions"]

        # Tópicos frequentes
        from collections import Counter
        topic_counts = Counter(self.state["last_conversation_topics"])
        top_topics = [t for t, _ in topic_counts.most_common(5)]

        context = f"""
[CURIOSITY CONTEXT - Injetado no prompt da Ramma]
- Total de interações nesta sessão: {interactions}
- Ferramentas disponíveis: {caps_count}
- Gaps de capacidade detectados: {gaps_count}
- Tópicos frequentes da conversa: {', '.join(top_topics) if top_topics else 'variados'}
- Perguntas proativas já feitas: {len(self.state['questions_asked'])}
- Respostas do usuário registradas: {len(self.state['user_responses'])}

[DIRETRIZES DE CURIOSIDADE]
1. SE o usuário perguntar "o que você faz" ou "o que mais você faz": use build_capability_summary() e pergunte "E você, o que gostaria que eu fizesse?"
2. SE detectar gap de capacidade: reconheça limitação honestamente, pergunte se quer que você aprenda/busque alternativa
3. A CADA ~30 min de conversa ativa: considere fazer uma pergunta proativa (use generate_proactive_question)
4. SE o usuário der feedback: registre com register_user_response_to_question()
5. USE web_search para raciocínio em tempo real sobre assuntos atuais
6. SEJA HONESTA sobre limitações - "não sei fazer X ainda, mas posso Y" é melhor que inventar
7. PERGUNTE "Por que?" e "Para quê?" - entenda a intenção, não só o comando
"""
        return context

    def suggest_skill_from_gap(self, gap_description: str) -> Optional[str]:
        """Analisa um gap e sugere uma habilidade concreta."""
        gap_lower = gap_description.lower()

        suggestions = {
            "whatsapp": "Plugin de automação WhatsApp (respostas automáticas, filtros, agendamento)",
            "email": "Integração com Gmail/Outlook (ler, enviar, filtrar, resumir)",
            "planilha": "Controle de planilhas Google Sheets/Excel (ler, escrever, gráficos)",
            "calendar": "Google Calendar / Outlook (criar eventos, lembretes, conflitos)",
            "notion": "Integração Notion (páginas, databases, templates)",
            "jira": "Integração Jira (issues, sprints, relatórios)",
            "docker": "Gerenciamento Docker (containers, logs, deploy)",
            "kubernetes": "Kubectl wrapper (pods, services, scaling)",
            "aws": "AWS CLI wrapper (EC2, S3, Lambda, CloudWatch)",
            "backup": "Sistema de backup automático versionado",
            "monitor": "Monitoramento de serviços/uptime com alertas",
            "scraper": "Web scraper robusto (paginação, anti-bot, export JSON/CSV)",
            "api": "Cliente REST/GraphQL genérico (auth, rate limit, cache)",
            "voice": "TTS/STT local (offline, privacidade, múltiplas vozes)",
            "vision": "Análise de imagem local (OCR, objetos, descrição)",
        }

        for keyword, suggestion in suggestions.items():
            if keyword in gap_lower:
                return suggestion

        return None


# Instância global (será inicializada no main.py)
_curiosity_engine: Optional[CuriosityEngine] = None


def get_curiosity_engine(base_dir: Path = None, action_registry=None, plugin_registry=None) -> CuriosityEngine:
    """Retorna instância singleton do CuriosityEngine."""
    global _curiosity_engine
    if _curiosity_engine is None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
        _curiosity_engine = CuriosityEngine(base_dir, action_registry, plugin_registry)
    return _curiosity_engine


def reset_curiosity_engine():
    """Para testes - reseta a instância global."""
    global _curiosity_engine
    _curiosity_engine = None