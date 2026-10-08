@echo off
REM ============================================================================
REM start_api.bat — Jalankan FastAPI server
REM ============================================================================

echo.
echo ============================================================
echo  START FastAPI — Rice Classification API
echo ============================================================
echo.

REM Aktifkan venv jika ada
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo [v] venv aktif.
) else (
    echo [!] venv tidak ditemukan. Pastikan setup_environment.bat sudah dijalankan.
    pause
    exit /b 1
)

echo.
echo Mulai FastAPI di http://localhost:8000
echo Dokumentasi API otomatis di http://localhost:8000/docs
echo.
echo Tekan Ctrl+C untuk berhenti.
echo.

uvicorn api:app --host 0.0.0.0 --port 8000 --reload
