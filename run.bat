@echo off
setlocal
set PY=%PYTHON%
if "%PY%"=="" set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

if "%1"=="" goto :usage
if /I "%1"=="cull" goto :cull
if /I "%1"=="pick" goto :pick
goto :unknown

:cull
shift
"%PY%" -c "from photopicker.cli import cull_main; cull_main()" %*
goto :eof

:pick
shift
"%PY%" -c "from photopicker.cli import main; main()" --folder %*
goto :eof

:usage
echo PhotoPicker — cull a shoot to the best N in a local web UI.
echo.
echo   run.bat cull ^<folder^> [--top 30] [--prompt "..."] [--output DIR]
echo       Point at a shoot folder, get the top N in the browser.
echo       K keep, X reject, U undo, arrows nav, Enter focus, E export, ? help
echo.
echo   run.bat pick ^<folder^> --profile ^<aries^|big7^|default^|aries-gallery^>
echo       Themed pick ^(categorized^) for portfolio galleries.
echo.
echo Examples:
echo   run.bat cull C:\Users\Michael\photos\aries_shoot --top 30
echo   run.bat cull C:\Users\Michael\photos\shoot --top 30 --prompt "best portfolio deck photos"
echo   run.bat pick C:\Users\Michael\photos\aries_shoot --profile aries-gallery --output C:\site\img
goto :eof

:unknown
echo Unknown subcommand: %1
echo Use: run.bat {cull^|pick}
exit /b 1
