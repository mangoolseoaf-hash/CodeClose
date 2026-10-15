@echo off
setlocal
title CodeClose by xL1F3 Software
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 goto no_node

set "CODECLOSE_PY="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "CODECLOSE_PY=%%i"
if not defined CODECLOSE_PY for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "CODECLOSE_PY=%%i"
if not defined CODECLOSE_PY goto no_py

if exist "node_modules\electron\dist\electron.exe" goto run
echo.
echo  Instalando componentes por primera vez. Solo ocurre una vez...
echo.
call npm install --no-audit --no-fund
if errorlevel 1 goto no_npm

:run
start "" "%~dp0node_modules\electron\dist\electron.exe" "%~dp0"
exit /b 0

:no_node
echo.
echo  [!] Falta Node.js. Instalalo desde https://nodejs.org y vuelve a ejecutar start.bat
echo.
pause
exit /b 1

:no_py
echo.
echo  [!] Falta Python 3. Instalalo desde https://python.org (marca "Add to PATH") y vuelve a ejecutar start.bat
echo.
pause
exit /b 1

:no_npm
echo.
echo  [!] No se pudieron instalar los componentes. Revisa tu conexion a internet.
echo.
pause
exit /b 1
