import os
import json
import time
import tempfile
import threading

# Cria o arquivo na pasta temporária nativa do Windows (Auto-limpeza pelo SO)
CACHE_FILE = os.path.join(tempfile.gettempdir(), "ramma_hotreload_cache.json")
MINUTOS_LIMITE = 5
MAX_MENSAGENS = 20  # Limita o tamanho do arquivo guardando apenas as falas recentes

# Batch save: acumula mudanças e salva periodicamente
_SAVE_LOCK = threading.Lock()
_PENDING_HISTORY = None
_PENDING_SAVE = False
_LAST_SAVE_TIME = 0.0
_SAVE_INTERVAL = 2.0      # segundos entre saves
_SAVE_THRESHOLD = 4       # número de mensagens novas antes de forçar save

def _do_save(historico):
    """Função interna que efetivamente escreve no disco."""
    if not historico:
        return
    try:
        historico_recente = historico[-MAX_MENSAGENS:] if len(historico) > MAX_MENSAGENS else historico
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(historico_recente, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memória Cache] ❌ Erro ao salvar cache: {e}")

def salvar_estado(historico):
    """Agenda um save em batch (não bloqueia, escreve no disco de forma assíncrona)."""
    global _PENDING_HISTORY, _PENDING_SAVE, _LAST_SAVE_TIME

    with _SAVE_LOCK:
        _PENDING_HISTORY = historico
        _PENDING_SAVE = True
        now = time.monotonic()

        # Força save se passou o intervalo OU acumulou mensagens suficientes
        should_save = (_LAST_SAVE_TIME == 0.0 or
                       now - _LAST_SAVE_TIME >= _SAVE_INTERVAL or
                       len(historico) % _SAVE_THRESHOLD == 0)

        if should_save:
            _LAST_SAVE_TIME = now
            _PENDING_SAVE = False
            # Escreve em thread separada para não bloquear
            threading.Thread(target=_do_save, args=(historico,), daemon=True).start()

def flush():
    """Força gravação imediata do estado pendente (chamar no shutdown)."""
    global _PENDING_HISTORY, _PENDING_SAVE, _LAST_SAVE_TIME
    with _SAVE_LOCK:
        if _PENDING_SAVE and _PENDING_HISTORY is not None:
            _do_save(_PENDING_HISTORY)
            _PENDING_SAVE = False
            _LAST_SAVE_TIME = time.monotonic()

def carregar_estado():
    """Recupera o histórico e DESTRÓI o arquivo imediatamente (Consumo de Cache)."""
    if not os.path.exists(CACHE_FILE):
        return None
        
    idade_segundos = time.time() - os.path.getmtime(CACHE_FILE)
    historico = None
    
    # 1. Lê o arquivo
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            historico = json.load(f)
    except Exception:
        pass

    # 2. Consumo Imediato: Exclui o arquivo do disco NA HORA. Zero lixo no HD.
    try:
        os.remove(CACHE_FILE)
    except OSError:
        pass

    # 3. Verifica se a conversa ainda é válida (menos de 5 minutos)
    if idade_segundos > (MINUTOS_LIMITE * 60):
        print(f"[Memória Cache] 🧹 Conversa antiga expirou ({int(idade_segundos/60)} min). Começando do zero.")
        return None
        
    if historico:
        tempo_seg = int(idade_segundos)
        print(f"[Memória Cache] 🧠 Retomando papo de {tempo_seg} segundos atrás! Arquivo temporário destruído.")
        return historico
        
    return None