import os
import sys
import time
import subprocess
import shutil
import ast
import zipfile
from datetime import datetime, timedelta

PASTA_BACKUP = "backups_ia"

# Configurações de retenção de backups
DIAS_RETENCAO = 7          # Mantém backups dos últimos 7 dias
MAX_BACKUPS_COMPLETOS = 10 # Mantém no máximo 10 backups completos (ZIP)
MAX_SNAPSHOTS = 50         # Mantém no máximo 50 snapshots individuais (.bak)

def limpar_backups_antigos():
    """Remove backups antigos baseado em idade e quantidade."""
    if not os.path.exists(PASTA_BACKUP):
        return

    agora = datetime.now()
    cutoff = agora - timedelta(days=DIAS_RETENCAO)

    arquivos = []
    for f in os.listdir(PASTA_BACKUP):
        caminho = os.path.join(PASTA_BACKUP, f)
        if os.path.isfile(caminho):
            mtime = datetime.fromtimestamp(os.path.getmtime(caminho))
            arquivos.append((f, caminho, mtime))

    # Separar por tipo
    zips = [(f, c, m) for f, c, m in arquivos if f.startswith("backup_completo_") and f.endswith(".zip")]
    baks = [(f, c, m) for f, c, m in arquivos if f.endswith(".bak")]
    logs = [(f, c, m) for f, c, m in arquivos if f == "ultimo_crash.log"]

    removidos = 0

    # 1. Remover por idade (mais antigos que DIAS_RETENCAO)
    for f, caminho, mtime in zips + baks + logs:
        if mtime < cutoff:
            try:
                os.remove(caminho)
                removidos += 1
                print(f"[Limpeza 🗑️] Removido antigo: {f}")
            except OSError:
                pass

    # 2. Limitar quantidade de backups completos (manter os mais recentes)
    zips_restantes = [(f, c, m) for f, c, m in zips if m >= cutoff]
    zips_restantes.sort(key=lambda x: x[2], reverse=True)
    for f, caminho, _ in zips_restantes[MAX_BACKUPS_COMPLETOS:]:
        try:
            os.remove(caminho)
            removidos += 1
            print(f"[Limpeza 🗑️] Limite ZIP excedido: {f}")
        except OSError:
            pass

    # 3. Limitar quantidade de snapshots (manter os mais recentes)
    baks_restantes = [(f, c, m) for f, c, m in baks if m >= cutoff]
    baks_restantes.sort(key=lambda x: x[2], reverse=True)
    for f, caminho, _ in baks_restantes[MAX_SNAPSHOTS:]:
        try:
            os.remove(caminho)
            removidos += 1
            print(f"[Limpeza 🗑️] Limite snapshot excedido: {f}")
        except OSError:
            pass

    if removidos > 0:
        print(f"[Limpeza 🗑️] Total removido: {removidos} arquivo(s)\n")
    else:
        print(f"[Limpeza 🗑️] Nenhum backup antigo para remover.\n")

def criar_backup_geral():
    """Camada 1: Cria um arquivo ZIP de todo o projeto ao abrir o modo dev."""
    if not os.path.exists(PASTA_BACKUP):
        os.makedirs(PASTA_BACKUP)
        
    agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_zip = os.path.join(PASTA_BACKUP, f"backup_completo_{agora}.zip")
    pastas_ignoradas = {PASTA_BACKUP, ".git", "__pycache__", "venv", "env"}
    
    print(f"[Segurança 🛡️] Criando Ponto de Restauração Geral...")
    with zipfile.ZipFile(nome_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in pastas_ignoradas]
            for file in files:
                if not file.endswith(".zip") and not file.endswith(".bak"):
                    caminho_completo = os.path.join(root, file)
                    zipf.write(caminho_completo, arcname=caminho_completo)
                    
    print(f"[Segurança 🛡️] Ponto de Restauração salvo em: {nome_zip}\n")

def mapear_arquivos():
    mtimes = {}
    for root, dirs, files in os.walk("."):
        if PASTA_BACKUP in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                mtimes[filepath] = os.path.getmtime(filepath)
    return mtimes

def iniciar_ia():
    # Redireciona os erros para conseguirmos salvar no log de crash
    return subprocess.Popen([sys.executable, "main.py"], stderr=subprocess.PIPE, text=True)

def verificar_sintaxe(arquivos_modificados):
    """Camada 2: Verifica erros de digitação do Autosave."""
    for arquivo in arquivos_modificados:
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                codigo = f.read()
            ast.parse(codigo, filename=arquivo)
        except SyntaxError as e:
            print(f"\n[Filtro 🚨] Autosave detectou erro em {arquivo} (Linha {e.lineno})")
            print("             -> A IA atual continuará rodando ilesa.\n")
            return False
        except Exception:
            return False
    return True

def criar_snapshot(arquivos_modificados):
    """Camada 3: Copia o arquivo antes de aplicar a mudança."""
    backups_feitos = {}
    for arquivo in arquivos_modificados:
        nome_seguro = arquivo.replace(os.sep, "_").replace(".py", ".bak")
        caminho_backup = os.path.join(PASTA_BACKUP, nome_seguro)
        shutil.copy2(arquivo, caminho_backup)
        backups_feitos[arquivo] = caminho_backup
    return backups_feitos

def restaurar_snapshot(backups_feitos):
    """Camada 5: Desfaz a alteração caso o sistema quebre."""
    for arquivo_original, arquivo_backup in backups_feitos.items():
        shutil.copy2(arquivo_backup, arquivo_original)
        print(f"[Rollback ⏪] Arquivo {arquivo_original} restaurado para a versão funcional.")

# Verifica se deve pular backup (para rodar via comando direto)
SKIP_BACKUP = os.environ.get("SKIP_BACKUP") == "1" or os.environ.get("DEV_MODE_NO_BACKUP") == "1"

print("=========================================================")
print(" 🚀 MODO DEV BLINDADO [COM COLETA DE CRASH LOGS]")
print(" 1. Ponto de Restauração Inicial")
print(" 2. Proteção Anti-Autosave")
print(" 3. Auto'-Rollback em caso de falha fatal (Crash)")
print(" 4. Log de Erros salvo automaticamente")
print(" 5. Limpeza automática de backups antigos")
print("=========================================================\n")

# Limpeza de backups antigos (roda antes de criar novos)
limpar_backups_antigos()

if not SKIP_BACKUP:
    criar_backup_geral()
else:
    print("[Segurança 🛡️] BACKUP PULADO (SKIP_BACKUP=1)\n")
processo = iniciar_ia()
arquivos_anteriores = mapear_arquivos()

try:
    while True:
        time.sleep(1)
        arquivos_atuais = mapear_arquivos()
        modificados = [f for f in arquivos_atuais if arquivos_atuais[f] != arquivos_anteriores.get(f)]
        
        if modificados:
            if verificar_sintaxe(modificados):
                backups = criar_snapshot(modificados)
                print(f"\n[DevMode 🔄] Alteração em {modificados[0]} aprovada. Reiniciando a IA...")
                
                # Kill é agressivo e garante que nenhum pedaço da IA antiga fique travando o PC
                processo.kill()
                processo.wait()
                processo = iniciar_ia()
                
                # Camada 4: Teste de Sobrevivência (Espera 2.5 segundos)
                time.sleep(2.5)
                
                if processo.poll() is not None:
                    # O processo morreu. Vamos capturar o erro e salvar.
                    erro = processo.stderr.read() if processo.stderr else "Erro desconhecido."
                    caminho_log = os.path.join(PASTA_BACKUP, "ultimo_crash.log")
                    
                    with open(caminho_log, "w", encoding="utf-8") as f:
                        f.write(f"Crash em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(erro)

                    print("\n[CRASH DETECTADO 💥] O código novo fez a IA fechar sozinha!")
                    print(f"[Log 📝] Erro detalhado salvo em: {caminho_log}")
                    print("[Emergência 🚨] Iniciando protocolo de reversão...")
                    
                    restaurar_snapshot(backups)
                    print("[DevMode 🔄] Ressuscitando a IA com o código antigo...\n")
                    processo = iniciar_ia()
                else:
                    print("[Sucesso ✅] IA reiniciada e estável com o novo código!\n")
            
            # Atualiza o mapa de arquivos independentemente do resultado
            arquivos_anteriores = mapear_arquivos()
            
except KeyboardInterrupt:
    processo.kill()
    print("\n[DevMode] Sistema encerrado de forma segura.")