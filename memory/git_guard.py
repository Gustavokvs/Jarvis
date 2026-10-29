"""
Git Guard - Bloqueio automático de dados íntimos/sensíveis no git
Pre-commit hook + scanner de arquivos perigosos
"""
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
GIT_DIR = BASE_DIR / ".git"
HOOKS_DIR = GIT_DIR / "hooks"
PRE_COMMIT_HOOK = HOOKS_DIR / "pre-commit"

# Padrões de arquivos/dados que NUNCA devem ir pro git
FORBIDDEN_PATTERNS = [
    # Memória segura
    r"memory/secure/vault\.enc",
    r"memory/secure/salt\.bin",
    # WhatsApp/session
    r"whatsapp_session/",
    r"whatsapp.*\.json",
    r"session.*\.json",
    # Backups
    r"backups_ia/",
    r"backup_completo_",
    r"\.bak$",
    # Temp
    r"temp/",
    r"\.tmp$",
    # Config sensível
    r"config/api_keys\.json",
    r"config/.*_token\.json",
    r"config/google_credentials\.json",
    r"config/caldav\.json",
    # Logs pessoais
    r"ultimo_crash\.log",
    # Models/voices (grandes)
    r"voices/\.onnx$",
    r"models/",
]

FORBIDDEN_CONTENT_PATTERNS = [
    # Conteúdo íntimo/roleplay
    r"(?i)(roleplay|íntimo|intimo|sensual|er[oó]tico|nsfw|adult)\s*[:\-]",
    # Senhas/tokens
    r"(?i)(password|senha|token|secret|api_key|apikey)\s*[=:]\s*\S+",
    # Chaves privadas
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    # Emails/pessoal
    r"(?i)(cpf|cnpj|rg|endereço|telefone|celular)\s*[=:]\s*\S+",
]

FORBIDDEN_FILENAMES = {
    "vault.enc", "salt.bin", "api_keys.json", "google_credentials.json",
    "caldav.json", "whatsapp_session", "ultimo_crash.log"
}


class GitGuard:
    """Protege contra commit de dados sensíveis."""

    def __init__(self):
        self.hook_installed = False

    def install_hook(self) -> bool:
        """Instala pre-commit hook no .git/hooks/."""
        try:
            HOOKS_DIR.mkdir(parents=True, exist_ok=True)

            hook_content = '''#!/bin/bash
# Ramma Git Guard - Auto-installed
# Bloqueia commit de dados íntimos/sensíveis

echo "🔒 Ramma Git Guard: Scanning staged files..."

# Chama o scanner Python
python -m memory.git_guard scan-staged
RESULT=$?

if [ $RESULT -ne 0 ]; then
    echo ""
    echo "❌ COMMIT BLOQUEADO: Dados sensíveis detectados!"
    echo "   Use 'git commit --no-verify' SE tiver CERTEZA (não recomendado)"
    echo "   Ou remova os arquivos: git reset HEAD <arquivo>"
    exit 1
fi

echo "✅ Ramma Git Guard: OK"
exit 0
'''

            PRE_COMMIT_HOOK.write_text(hook_content, encoding="utf-8")
            # Torna executável (Linux/Mac) - no Windows o git usa o shebang
            try:
                os.chmod(PRE_COMMIT_HOOK, 0o755)
            except:
                pass

            self.hook_installed = True
            print("[GitGuard] ✅ Pre-commit hook instalado")
            return True
        except Exception as e:
            print(f"[GitGuard] ❌ Falha ao instalar hook: {e}")
            return False

    def uninstall_hook(self) -> bool:
        try:
            if PRE_COMMIT_HOOK.exists():
                PRE_COMMIT_HOOK.unlink()
            self.hook_installed = False
            print("[GitGuard] Hook removido")
            return True
        except Exception as e:
            print(f"[GitGuard] Erro ao remover: {e}")
            return False

    def scan_file(self, filepath: Path) -> List[str]:
        """Escaneia um arquivo por padrões perigosos. Retorna lista de violações."""
        violations = []

        # Verifica nome do arquivo
        rel_path = str(filepath.relative_to(BASE_DIR)) if filepath.is_relative_to(BASE_DIR) else str(filepath)
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, rel_path):
                violations.append(f"Arquivo proibido: {rel_path} (match: {pattern})")

        # Verifica nome base
        if filepath.name in FORBIDDEN_FILENAMES:
            violations.append(f"Nome de arquivo proibido: {filepath.name}")

        # Verifica conteúdo (só arquivos de texto pequenos)
        try:
            if filepath.stat().st_size > 1024 * 1024:  # > 1MB pula
                return violations

            if filepath.suffix in {'.json', '.txt', '.log', '.py', '.md', '.yaml', '.yml', '.ini', '.cfg', '.conf'}:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                for pattern in FORBIDDEN_CONTENT_PATTERNS:
                    matches = list(re.finditer(pattern, content))
                    if matches:
                        for m in matches[:3]:  # max 3 por padrão
                            line_num = content[:m.start()].count('\n') + 1
                            violations.append(f"Conteúdo sensível em {rel_path}:{line_num} (match: {pattern[:50]})")
        except:
            pass

        return violations

    def scan_staged(self) -> int:
        """Escaneia arquivos staged para commit. Retorna 0=OK, 1=BLOQUEAR."""
        try:
            # Lista arquivos staged
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=BASE_DIR, capture_output=True, text=True, timeout=10
            )
            staged = [BASE_DIR / f for f in result.stdout.strip().split('\n') if f.strip()]

            all_violations = []
            for f in staged:
                if f.exists():
                    violations = self.scan_file(f)
                    all_violations.extend(violations)

            if all_violations:
                print("\n🚨 VIOLAÇÕES DETECTADAS:")
                for v in all_violations:
                    print(f"  - {v}")
                print("\n💡 Para permitir mesmo assim: git commit --no-verify")
                return 1

            return 0
        except Exception as e:
            print(f"[GitGuard] Erro no scan: {e}")
            return 0  # Não bloqueia se erro

    def scan_all(self) -> Dict[str, List[str]]:
        """Escaneia todo o repo (útil para auditoria)."""
        violations = {}
        for root, dirs, files in os.walk(BASE_DIR):
            # Pula .git
            if '.git' in root:
                continue
            for f in files:
                filepath = Path(root) / f
                v = self.scan_file(filepath)
                if v:
                    violations[str(filepath.relative_to(BASE_DIR))] = v
        return violations

    def check_gitignore(self) -> List[str]:
        """Verifica se .gitignore cobre os padrões proibidos."""
        gitignore = BASE_DIR / ".gitignore"
        missing = []

        if not gitignore.exists():
            return ["⚠️ .gitignore não existe!"]

        content = gitignore.read_text(encoding="utf-8")

        # Verifica padrões essenciais
        essential = [
            "memory/secure/",
            "whatsapp_session/",
            "backups_ia/",
            "temp/",
            "*.bak",
            "config/api_keys.json",
            "config/*_token.json",
            "config/google_credentials.json",
            "ultimo_crash.log",
        ]

        for pattern in essential:
            if pattern not in content:
                missing.append(f"Falta no .gitignore: {pattern}")

        return missing


_guard: Optional[GitGuard] = None


def get_git_guard() -> GitGuard:
    global _guard
    if _guard is None:
        _guard = GitGuard()
    return _guard


def git_guard_tool(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Proteção git automática: instala hook, escaneia staged, audita repo, verifica .gitignore."""
    params = parameters or {}
    op = params.get("operation", "status").lower()

    guard = get_git_guard()

    if op == "install":
        if guard.install_hook():
            return "✅ Pre-commit hook instalado. Commits com dados sensíveis serão bloqueados."
        return "❌ Falha ao instalar"

    elif op == "uninstall":
        if guard.uninstall_hook():
            return "🗑️ Hook removido"
        return "❌ Falha ao remover"

    elif op == "scan_staged":
        result = guard.scan_staged()
        return "✅ Staged limpo" if result == 0 else "❌ Violações encontradas (veja logs acima)"

    elif op == "scan_all":
        violations = guard.scan_all()
        if not violations:
            return "✅ Repo limpo - nenhum dado sensível encontrado"
        lines = [f"🚨 {len(violations)} arquivo(s) com violações:"]
        for f, vs in list(violations.items())[:20]:
            lines.append(f"  📄 {f}")
            for v in vs[:3]:
                lines.append(f"    - {v}")
        if len(violations) > 20:
            lines.append(f"  ... e mais {len(violations) - 20} arquivos")
        return "\n".join(lines)

    elif op == "check_gitignore":
        missing = guard.check_gitignore()
        if not missing:
            return "✅ .gitignore cobre todos os padrões essenciais"
        return "⚠️ .gitignore incompleto:\n" + "\n".join(f"  - {m}" for m in missing)

    elif op == "fix_gitignore":
        gitignore = BASE_DIR / ".gitignore"
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        essential = [
            "\n# Ramma - Dados sensíveis (auto-protegidos)",
            "memory/secure/",
            "whatsapp_session/",
            "backups_ia/",
            "temp/",
            "*.bak",
            "config/api_keys.json",
            "config/*_token.json",
            "config/google_credentials.json",
            "config/caldav.json",
            "ultimo_crash.log",
        ]
        added = []
        for line in essential:
            if line not in content:
                content += "\n" + line
                added.append(line)
        gitignore.write_text(content.strip() + "\n", encoding="utf-8")
        if added:
            return "✅ .gitignore atualizado:\n" + "\n".join(added)
        return "✅ .gitignore já estava completo"

    elif op == "status":
        hook_status = "✅ Instalado" if guard.hook_installed or PRE_COMMIT_HOOK.exists() else "❌ Não instalado"
        missing = guard.check_gitignore()
        gi_status = "✅ Completo" if not missing else f"⚠️ {len(missing)} faltando"
        return f"Hook: {hook_status}\n.gitignore: {gi_status}"

    return "Ops: install, uninstall, scan_staged, scan_all, check_gitignore, fix_gitignore, status"


TOOL = {
    "name": "git_guard",
    "description": "Proteção git contra vazamento de dados íntimos/sensíveis. Instala pre-commit hook que bloqueia commit de vault.enc, whatsapp_session, api_keys, backups, etc. Ops: install, uninstall, scan_staged, scan_all, check_gitignore, fix_gitignore, status.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "install | uninstall | scan_staged | scan_all | check_gitignore | fix_gitignore | status"},
        },
        "required": ["operation"],
    },
    "handler": git_guard_tool,
}