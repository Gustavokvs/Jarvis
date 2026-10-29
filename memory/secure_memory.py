"""
Secure Memory - Memória criptografada AES-256 para dados íntimos/sensíveis
Só a SUA máquina consegue ler. Chave derivada do login Windows + hardware.
"""
import os
import json
import base64
import hashlib
import platform
import getpass
from pathlib import Path
from typing import Dict, Any, Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

BASE_DIR = Path(__file__).resolve().parent.parent
SECURE_DIR = BASE_DIR / "memory" / "secure"
SECURE_FILE = SECURE_DIR / "vault.enc"
SALT_FILE = SECURE_DIR / "salt.bin"


class SecureMemory:
    """Vault criptografado para memórias íntimas - NUNCA sai desta máquina."""

    def __init__(self):
        if not HAS_CRYPTO:
            raise RuntimeError("cryptography não instalado. pip install cryptography")

        SECURE_DIR.mkdir(parents=True, exist_ok=True)
        self._key = None
        self._aesgcm = None
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def _derive_key(self) -> bytes:
        """Deriva chave única desta máquina + usuário Windows."""
        # Componentes únicos da máquina
        machine_id = platform.node() + platform.processor() + platform.machine()
        user_id = getpass.getuser()
        # ID do volume C: (Windows)
        volume_id = ""
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_logicaldisk", "where", "deviceid='C:'", "get", "volumeserialnumber"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if line.strip() and not line.startswith("Volume"):
                    volume_id = line.strip()
                    break
        except:
            pass

        # Combina tudo
        seed = f"{machine_id}|{user_id}|{volume_id}|Ramma-Secure-Vault".encode()

        # Salt persistente (gerado uma vez)
        if SALT_FILE.exists():
            salt = SALT_FILE.read_bytes()
        else:
            salt = os.urandom(32)
            SALT_FILE.write_bytes(salt)

        # PBKDF2 - 100k iterações
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        return kdf.derive(seed)

    def _get_key(self) -> bytes:
        if self._key is None:
            self._key = self._derive_key()
            self._aesgcm = AESGCM(self._key)
        return self._key

    def _load(self) -> bool:
        """Carrega e descripta o vault."""
        if self._loaded:
            return True

        if not SECURE_FILE.exists():
            self._data = {"intimate": {}, "personal": {}, "notes": {}}
            self._loaded = True
            return True

        try:
            encrypted = SECURE_FILE.read_bytes()
            # Primeiros 12 bytes = nonce
            nonce = encrypted[:12]
            ciphertext = encrypted[12:]
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
            self._data = json.loads(plaintext.decode())
            self._loaded = True
            print("[SecureMemory] 🔓 Vault descriptografado")
            return True
        except Exception as e:
            print(f"[SecureMemory] ❌ Falha ao descriptar (chave errada ou corrompido): {e}")
            # NÃO apaga - pode ser outra máquina tentando ler
            return False

    def _save(self) -> bool:
        """Cripta e salva o vault."""
        if not self._loaded:
            return False

        try:
            # Ensure key is derived
            self._get_key()
            plaintext = json.dumps(self._data, ensure_ascii=False).encode()
            nonce = os.urandom(12)
            ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
            encrypted = nonce + ciphertext
            SECURE_FILE.write_bytes(encrypted)
            print("[SecureMemory] 🔒 Vault criptografado e salvo")
            return True
        except Exception as e:
            print(f"[SecureMemory] ❌ Falha ao salvar: {e}")
            return False

    # --- API Pública ---

    def store_intimate(self, key: str, value: str, metadata: Dict = None) -> bool:
        """Armazena memória íntima (roleplay, conversas sensuais, segredos)."""
        if not self._load():
            return False
        self._data.setdefault("intimate", {})[key] = {
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "type": "intimate"
        }
        return self._save()

    def store_personal(self, key: str, value: str, metadata: Dict = None) -> bool:
        """Armazena memória pessoal sensível (senhas, chaves, docs)."""
        if not self._load():
            return False
        self._data.setdefault("personal", {})[key] = {
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
            "type": "personal"
        }
        return self._save()

    def get(self, category: str, key: str) -> Optional[str]:
        """Recupera valor descriptografado."""
        if not self._load():
            return None
        cat = self._data.get(category, {})
        item = cat.get(key)
        return item["value"] if item else None

    def get_all(self, category: str) -> Dict[str, Any]:
        """Retorna todas as chaves de uma categoria (sem valores por segurança)."""
        if not self._load():
            return {}
        cat = self._data.get(category, {})
        return {k: {"metadata": v.get("metadata", {}), "timestamp": v.get("timestamp"), "type": v.get("type")}
                for k, v in cat.items()}

    def search(self, query: str, category: str = None) -> List[Dict]:
        """Busca por conteúdo (descripta temporariamente para buscar)."""
        if not self._load():
            return []

        results = []
        cats = [category] if category else ["intimate", "personal", "notes"]
        q = query.lower()

        for cat_name in cats:
            for key, item in self._data.get(cat_name, {}).items():
                if q in key.lower() or q in item["value"].lower():
                    results.append({
                        "category": cat_name,
                        "key": key,
                        "preview": item["value"][:100] + "..." if len(item["value"]) > 100 else item["value"],
                        "timestamp": item.get("timestamp")
                    })
        return results

    def delete(self, category: str, key: str) -> bool:
        if not self._load():
            return False
        if key in self._data.get(category, {}):
            del self._data[category][key]
            return self._save()
        return False

    def wipe(self, confirm: str = None) -> bool:
        """APAGA TUDO - irrecuperável. Use com extrema cautela."""
        if confirm != "EU_QUERO_APAGAR_TUDO_PARA_SEMPRE":
            return False
        try:
            if SECURE_FILE.exists():
                SECURE_FILE.unlink()
            if SALT_FILE.exists():
                SALT_FILE.unlink()
            self._data = {"intimate": {}, "personal": {}, "notes": {}}
            self._loaded = False
            print("[SecureMemory] 💥 VAULT APAGADO PERMANENTEMENTE")
            return True
        except Exception as e:
            print(f"[SecureMemory] Erro ao apagar: {e}")
            return False

    def export_encrypted(self, output_path: Path) -> bool:
        """Exporta vault criptografado (para backup seguro)."""
        if not self._loaded:
            return False
        try:
            encrypted = SECURE_FILE.read_bytes()
            output_path.write_bytes(encrypted)
            return True
        except:
            return False

    def import_encrypted(self, input_path: Path) -> bool:
        """Importa vault (só funciona se for SUA máquina - mesma chave)."""
        try:
            encrypted = input_path.read_bytes()
            # Tenta descriptar para validar
            nonce = encrypted[:12]
            ciphertext = encrypted[12:]
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, None)
            json.loads(plaintext.decode())  # valida JSON
            SECURE_FILE.write_bytes(encrypted)
            self._loaded = False  # força reload
            return self._load()
        except Exception as e:
            print(f"[SecureMemory] Import falhou (chave diferente?): {e}")
            return False


from datetime import datetime

_vault: Optional[SecureMemory] = None


def get_secure_memory() -> SecureMemory:
    global _vault
    if _vault is None:
        _vault = SecureMemory()
    return _vault


def secure_memory_tool(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Memória criptografada AES-256 - só SUA máquina lê. Para dados íntimos/sensíveis."""
    params = parameters or {}
    op = params.get("operation", "status").lower()

    vault = get_secure_memory()

    if op == "store_intimate":
        key = params.get("key", "").strip()
        value = params.get("value", "")
        meta = params.get("metadata", {})
        if not key or not value:
            return "Forneça key e value"
        if vault.store_intimate(key, value, meta):
            return f"🔒 Íntimo salvo: {key}"
        return "❌ Falha ao salvar"

    elif op == "store_personal":
        key = params.get("key", "").strip()
        value = params.get("value", "")
        meta = params.get("metadata", {})
        if not key or not value:
            return "Forneça key e value"
        if vault.store_personal(key, value, meta):
            return f"🔐 Pessoal salvo: {key}"
        return "❌ Falha ao salvar"

    elif op == "get":
        cat = params.get("category", "intimate")
        key = params.get("key", "").strip()
        val = vault.get(cat, key)
        if val is None:
            return f"Não encontrado: {cat}/{key}"
        return val

    elif op == "list":
        cat = params.get("category", "intimate")
        items = vault.get_all(cat)
        if not items:
            return f"📭 {cat} vazio"
        lines = [f"🔑 {cat} ({len(items)} itens):"]
        for k, v in items.items():
            lines.append(f"  • {k} — {v.get('timestamp','?')} — meta: {v.get('metadata')}")
        return "\n".join(lines)

    elif op == "search":
        q = params.get("query", "").strip()
        cat = params.get("category")
        results = vault.search(q, cat)
        if not results:
            return f"Nada encontrado para '{q}'"
        lines = [f"🔍 Resultados para '{q}':"]
        for r in results[:10]:
            lines.append(f"  [{r['category']}] {r['key']} — {r['preview']}")
        return "\n".join(lines)

    elif op == "delete":
        cat = params.get("category", "intimate")
        key = params.get("key", "").strip()
        if vault.delete(cat, key):
            return f"🗑️ Removido: {cat}/{key}"
        return "Não encontrado"

    elif op == "status":
        vault._load()  # testa se consegue abrir
        loaded = "✅ Aberta" if vault._loaded else "🔒 Fechada/Outra máquina"
        return f"Vault: {loaded}\nLocal: {SECURE_FILE}"

    return "Ops: store_intimate(key,value,metadata), store_personal(key,value,metadata), get(category,key), list(category), search(query,category), delete(category,key), status"


TOOL = {
    "name": "secure_memory",
    "description": "Vault criptografado AES-256 - SÓ sua máquina descripta. Chave derivada do hardware+usuário Windows. Para memórias íntimas, roleplay, segredos, senhas. NUNCA vai pro git. Ops: store_intimate, store_personal, get, list, search, delete, status.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "store_intimate | store_personal | get | list | search | delete | status"},
            "category": {"type": "STRING", "description": "intimate | personal | notes"},
            "key": {"type": "STRING", "description": "Chave do item"},
            "value": {"type": "STRING", "description": "Valor a criptografar"},
            "metadata": {"type": "OBJECT", "description": "Metadados extras"},
            "query": {"type": "STRING", "description": "Termo de busca"},
        },
        "required": ["operation"],
    },
    "handler": secure_memory_tool,
}