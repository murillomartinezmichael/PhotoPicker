@echo off
REM ============================================================================
REM build.bat — clean-clone -> running, one command (Windows).
REM
REM WHY THIS EXISTS
REM   Mirror of build.sh for Windows developers. A new contributor clones the
REM   repo and runs `build.bat`. When it finishes, the project is ready.
REM
REM HOW TO CUSTOMIZE
REM   - Edit STACK below to match your project
REM   - Fill in the per-stack sections
REM   - Delete the sections you don't use
REM ============================================================================

setlocal enabledelayedexpansion

REM ---- configure -------------------------------------------------------------
set "STACK=python"
for %%I in (.) do set "PROJECT_NAME=%%~nxI"
REM ----------------------------------------------------------------------------

echo [build] Building %PROJECT_NAME% (stack: %STACK%)

REM ---- ensure .env -----------------------------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo [warn] .env was missing - generated from .env.example. EDIT IT before running.
    ) else (
        echo [warn] No .env or .env.example found.
    )
)

REM ---- stack-specific setup --------------------------------------------------
if /I "%STACK%"=="python" goto :python_setup
if /I "%STACK%"=="dotnet" goto :dotnet_setup
if /I "%STACK%"=="node"   goto :node_setup
if /I "%STACK%"=="go"     goto :go_setup
if /I "%STACK%"=="static" goto :static_setup
echo [fail] Unknown STACK: %STACK%. Use python ^| dotnet ^| node ^| go ^| static
exit /b 1

:python_setup
where python >nul 2>&1 || (echo [fail] python not installed & exit /b 1)
if not exist ".venv" (
    echo [build] Creating virtualenv (.venv)
    python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat
echo [build] Upgrading pip
python -m pip install --quiet --upgrade pip
if exist "requirements.txt" (
    echo [build] Installing requirements.txt
    pip install --quiet -r requirements.txt || exit /b 1
)
if exist "requirements-dev.txt" (
    echo [build] Installing requirements-dev.txt
    pip install --quiet -r requirements-dev.txt || exit /b 1
)
if exist "pyproject.toml" (
    echo [build] Installing project (editable)
    pip install --quiet -e . || exit /b 1
)
goto :migrations

:dotnet_setup
where dotnet >nul 2>&1 || (echo [fail] dotnet not installed & exit /b 1)
echo [build] Restoring NuGet packages
dotnet restore || exit /b 1
echo [build] Building solution (Release)
dotnet build --configuration Release --nologo --verbosity quiet || exit /b 1
goto :migrations

:node_setup
where node >nul 2>&1 || (echo [fail] node not installed & exit /b 1)
if exist "pnpm-lock.yaml" (
    where pnpm >nul 2>&1 || (echo [fail] pnpm not installed & exit /b 1)
    pnpm install --frozen-lockfile || exit /b 1
) else if exist "yarn.lock" (
    where yarn >nul 2>&1 || (echo [fail] yarn not installed & exit /b 1)
    yarn install --frozen-lockfile || exit /b 1
) else (
    where npm >nul 2>&1 || (echo [fail] npm not installed & exit /b 1)
    npm ci || exit /b 1
)
goto :migrations

:go_setup
where go >nul 2>&1 || (echo [fail] go not installed & exit /b 1)
go mod download || exit /b 1
go build ./... || exit /b 1
goto :migrations

:static_setup
echo [build] Static site - no build deps. Skipping install.
goto :migrations

:migrations
if exist "scripts\migrate.bat" (
    echo [build] Running database migrations
    call scripts\migrate.bat up || exit /b 1
)

echo [build] READY. See RUNBOOK.md section 1.4 for how to run.
endlocal
exit /b 0
