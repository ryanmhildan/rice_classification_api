@echo off
REM ============================================================================
REM setup_environment.bat — Setup Backend FastAPI
REM ============================================================================
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  SETUP BACKEND — Rice Classification API
echo ============================================================
echo.

REM ---- LANGKAH 1: Cek Python ----
echo [1/5] Memeriksa Python...
where python >nul 2>&1
if errorlevel 1 (
    echo [X] ERROR: Python tidak ditemukan.
    echo Install Python 3.10+ dari https://www.python.org/downloads/
    pause & exit /b 1
)
python --version

REM ---- LANGKAH 2: Validasi versi Python ----
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [X] Versi Python di bawah 3.10. Sistem butuh Python 3.10+.
    pause & exit /b 1
)
echo [v] Versi Python cocok.
echo.

REM ---- LANGKAH 3: Buat venv ----
echo [2/5] Membuat virtual environment...
if exist venv (
    echo [!] venv sudah ada, lewati pembuatan.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [X] Gagal membuat venv.
        pause & exit /b 1
    )
    echo [v] venv dibuat.
)
echo.

REM ---- LANGKAH 4: Aktifkan venv + install ----
echo [3/5] Aktifkan venv dan upgrade pip...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

echo.
echo [4/5] Install library dari requirements.txt
echo       (Tahap ini bisa makan waktu 5-15 menit)
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Sebagian library gagal terpasang.
    echo Solusi umum:
    echo   - Install Microsoft C++ Build Tools jika rasterio gagal:
    echo     https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo   - Coba ulang: pip install -r requirements.txt
    pause & exit /b 1
)
echo [v] Library siap.
echo.

REM ---- LANGKAH 5: Verifikasi ----
echo [5/5] Verifikasi dengan sample_test.py
python sample_test.py
if errorlevel 1 (
    pause & exit /b 1
)

echo.
echo ============================================================
echo  SETUP SELESAI
echo ============================================================
echo.
echo Langkah berikutnya:
echo   1. Pastikan Docker Desktop berjalan dan NodeODM container aktif
echo      (jalankan start_nodeodm.bat dari folder rice_orthophoto_pipeline)
echo   2. Jalankan: start_api.bat
echo   3. Buka http://localhost:8000/docs di browser
echo.
pause
endlocal
