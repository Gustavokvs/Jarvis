import os
import json
import time
import tempfile

# Cria o arquivo na pasta temporária nativa do Windows (Auto-limpeza pelo SO)
CACHE_FILE = os.path.join(tempfile.gettempdir(), "ramma_hotreload_cache.json")
MINUTOS_LIMITE = 5
MAX_MENSAGENS = 20 # Limita o tamanho do arquivo guardando apenas as falas recentes

def salvar_estado(historico):
    """Salva apenas o final da conversa na pasta temporária do Windows."""
    if not historico:
        return
        
    try:
        # Pega apenas as últimas MAX_MENSAGENS para garantir que o arquivo seja minúsculo
        historico_recente = historico[-MAX_MENSAGENS:] if len(historico) > MAX_MENSAGENS else historico
        
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(historico_recente, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Memória Cache] ❌ Erro ao salvar cache: {e}")

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