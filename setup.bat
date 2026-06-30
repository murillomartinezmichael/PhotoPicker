@echo off
REM PhotoPicker — Python library install (Windows).
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo [ERROR] Python not on PATH. ^& pause ^& exit /b 1)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating venv...
    python -m venv .venv || exit /b 1
) else (
    echo [1/3] venv exists
)

echo [2/3] Installing in editable mode...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
call ".venv\Scripts\python.exe" -m pip install -e ".[dev]" 2>nul || call ".venv\Scripts\python.exe" -m pip install -e . || (echo [ERROR] install failed ^& pause ^& exit /b 1)

echo [3/3] Smoke tests...
if exist tests (
    call ".venv\Scripts\python.exe" -m pytest -q || echo [WARN] Tests failed.
)

echo.
echo Library installed in editable mode. Import it in another project's venv.
endlocal
