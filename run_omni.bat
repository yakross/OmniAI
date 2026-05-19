@echo off
cd /d "%~dp0"
title Servidor OMNI-AI (Cerebro General)
color 0B
echo ==========================================================
echo           SISTEMA DE INICIALIZACION OMNI-AI
echo ==========================================================
echo.

:: Verificar si existe la carpeta del entorno virtual
if exist "venv\Scripts\python.exe" (
    echo [OK] Entorno virtual detectado en 'venv'.
    echo [*] Iniciando servidor FastAPI con el entorno virtual...
    
    :: Iniciar el navegador en segundo plano después de 2 segundos
    start /b "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:8000/ui/"
    
    :: Ejecutar el servidor
    "venv\Scripts\python.exe" server.py
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] El servidor de OMNI-AI se detuvo con codigo de error %errorlevel%.
        pause
    )
) else (
    echo [ERROR] No se detecto el entorno virtual en 'venv'.
    echo [*] Intentando buscar python en el sistema...
    
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        echo [OK] Python de sistema detectado.
        start /b "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:8000/ui/"
        python server.py
        if %errorlevel% neq 0 (
            echo.
            echo [ERROR] El servidor de OMNI-AI se detuvo con codigo de error %errorlevel%.
            pause
        )
    ) else (
        echo [ERROR] Python no esta instalado en el sistema o no esta en el PATH.
        echo [!] Por favor revisa la guia de instalacion en walkthrough_actualizacion.md
        pause
    )
)
