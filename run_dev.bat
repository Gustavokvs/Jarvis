@echo off
chcp 65001 >nul
title JARVIS / Ramma - MODO DESENVOLVIMENTO
echo ========================================================
echo  JARVIS / Ramma - MODO DESENVOLVIMENTO (Auto-reload)
echo ========================================================
echo.
echo [INFO] Este modo reinicia a IA automaticamente ao detectar
echo        mudanças nos arquivos .py (com proteção de backup).
echo.
echo [INFO] Recursos disponíveis:
echo   - Otimização de RAM: Diga "otimize a ram" ou "libere memória"
echo   - Volume da voz: Diga "abaixe sua voz" ou "aumente seu volume"
echo   - Volume do sistema: Diga "volume do sistema 30"
echo.
echo [RAM] Otimização automática ativa (intervalo: 5 min em foreground)
echo [RAM] Garbage collection agressivo: ON
echo.

:: Verifica se Python está disponível
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python não encontrado no PATH.
    pause
    exit /b 1
)

:: Verifica se está no diretório correto
if not exist "modo_dev.py" (
    echo [ERRO] Execute este arquivo na pasta do projeto (onde está modo_dev.py)
    pause
    exit /b 1
)

:: Verifica dependências
python -c "import psutil, sounddevice, numpy, google.genai, pycaw, comtypes" 2>nul
if %errorlevel% neq 0 (
    echo [AVISO] Algumas dependências podem estar faltando.
    echo Instalando via requirements.txt...
    pip install -r requirements.txt --quiet
    echo.
)

:: Inicia o Modo Desenvolvimento
echo [START] Iniciando MODO DESENVOLVIMENTO...
echo.
python modo_dev.py

echo.
echo ========================================================
echo  Modo Desenvolvimento finalizado.
echo ========================================================
pause