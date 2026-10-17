@echo off
rem OIT uninstaller launcher: double-click this file.
rem It asks for administrator rights (needed to re-enable network adapters).
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0uninstall.py" & exit /b 0)
where pyw >nul 2>nul && (start "" pyw -3 "%~dp0uninstall.py" & exit /b 0)
where python >nul 2>nul && (python "%~dp0uninstall.py" & exit /b 0)
where py >nul 2>nul && (py -3 "%~dp0uninstall.py" & exit /b 0)
echo Python was not found. Install Python 3.10+ or run: python uninstall.py
pause
