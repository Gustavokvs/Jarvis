@echo off
chcp 65001 >nul
title JARVIS / Ramma - Assistente de Voz
echo ========================================================
echo  JARVIS / Ramma - Iniciando...
echo ========================================================
echo.

:: Verifica se Python está disponível
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python não encontrado no PATH.
    echo Instale o Python em https://python.org ou via Microsoft Store.
    pause
    exit /b 1
)

:: Verifica se está no diretório correto
if not exist "main.py" (
    echo [ERRO] Execute este arquivo na pasta do projeto (onde está main.py)
    pause
    exit /b 1
)

:: Verifica dependências básicas
python -c "import psutil, sounddevice, numpy, google.genai" 2>nul
if %errorlevel% neq 0 (
    echo [AVISO] Algumas dependências podem estar faltando.
    echo Tentando instalar via requirements.txt...
    pip install -r requirements.txt --quiet
    echo.
)

:: Configurações de otimização de RAM
echo [RAM] Otimização de memória ativada (intervalo: 5 min)
echo [RAM] Garbage collection agressivo: ON
echo.

:: Inicia o JARVIS
echo [START] Iniciando JARVIS...
echo.
python main.py

echo.
echo ========================================================
echo  JARVIS finalizado.
echo ========================================================
pause