"""
Smoke test komprehensif untuk FastAPI backend.
Test semua endpoint kecuali yang butuh NodeODM (POST /jobs/stitch).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

API_URL = "http://127.0.0.1:8000"
PROC = None


def start_server():
    global PROC
    PROC = subprocess.Popen(
        ["uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Tunggu server siap
    for _ in range(20):
        try:
            r = requests.get(f"{API_URL}/health", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def stop_server():
    global PROC
    if PROC:
        PROC.terminate()
        PROC.wait(timeout=5)


def test(name, fn):
    """Run a test and print result."""
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
        return False


def t_root():
    r = requests.get(f"{API_URL}/")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "Rice Harvest Classification API"
    assert "endpoints" in d


def t_health():
    r = requests.get(f"{API_URL}/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["output_dir_exists"] is True


def t_nodeodm_status_expected_fail():
    """NodeODM tidak jalan di env smoke test → harus 503."""
    r = requests.get(f"{API_URL}/nodeodm/status")
    assert r.status_code == 503, f"Expected 503, got {r.status_code}"
    assert "detail" in r.json()


def t_classify_ok():
    """Klasifikasi orthophoto dummy → harus success."""
    r = requests.post(
        f"{API_URL}/classify",
        json={"orthophoto_path": "data/orthophoto_dummy.tif", "threshold": 0.60},
    )
    assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
    d = r.json()
    assert d["success"] is True
    assert d["verdict"] in ("SIAP PANEN", "BELUM SIAP PANEN")
    assert "files" in d
    assert "visualization" in d["files"]


def t_classify_missing_file():
    """File tidak ada → 404."""
    r = requests.post(
        f"{API_URL}/classify",
        json={"orthophoto_path": "data/nope.tif", "threshold": 0.60},
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"


def t_classify_invalid_threshold():
    """Threshold di luar range → 422 (Pydantic validation)."""
    r = requests.post(
        f"{API_URL}/classify",
        json={"orthophoto_path": "data/orthophoto_dummy.tif", "threshold": 1.5},
    )
    assert r.status_code == 422


def t_files_serve():
    """File yang ada → 200."""
    # Cari file PNG terbaru
    viz_dir = Path("output/visualization")
    files = sorted(viz_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert len(files) > 0, "Tidak ada file PNG di output/visualization untuk dites"
    filename = files[0].name
    r = requests.get(f"{API_URL}/files/visualization/{filename}")
    assert r.status_code == 200, f"Status {r.status_code}, filename={filename}"
    assert r.headers["content-type"].startswith("image/")


def t_files_invalid_category():
    """Kategori tidak valid → 400."""
    r = requests.get(f"{API_URL}/files/wrong/foo.png")
    assert r.status_code == 400


def t_files_not_found():
    """File tidak ada → 404."""
    r = requests.get(f"{API_URL}/files/visualization/tidak_ada.png")
    assert r.status_code == 404


def t_results_list():
    r = requests.get(f"{API_URL}/results")
    assert r.status_code == 200
    d = r.json()
    assert "count" in d
    assert "results" in d
    assert isinstance(d["results"], list)


def t_job_not_found():
    """Polling job yang tidak ada → 404."""
    r = requests.get(f"{API_URL}/jobs/notexist")
    assert r.status_code == 404


def t_job_classify_not_ready():
    """Klasifikasi job yang tidak ada → 404."""
    r = requests.post(f"{API_URL}/jobs/notexist/classify")
    assert r.status_code == 404


# ============================================================================
# Main
# ============================================================================
def main():
    print("=" * 60)
    print(" Smoke Test — FastAPI Backend")
    print("=" * 60)
    print("Starting uvicorn...")
    if not start_server():
        print("FATAL: server tidak responsif")
        return 1

    try:
        print()
        print("Endpoints:")
        tests = [
            ("GET /",                       t_root),
            ("GET /health",                 t_health),
            ("GET /nodeodm/status (503)",   t_nodeodm_status_expected_fail),
            ("POST /classify (success)",    t_classify_ok),
            ("POST /classify (404)",        t_classify_missing_file),
            ("POST /classify (422)",        t_classify_invalid_threshold),
            ("GET /files/viz/*",            t_files_serve),
            ("GET /files/wrong (400)",      t_files_invalid_category),
            ("GET /files/viz/no (404)",     t_files_not_found),
            ("GET /results",                t_results_list),
            ("GET /jobs/notexist (404)",    t_job_not_found),
            ("POST /jobs/notexist/classify",t_job_classify_not_ready),
        ]
        passed = 0
        for name, fn in tests:
            if test(name, fn):
                passed += 1

        print()
        print("=" * 60)
        print(f" Result: {passed}/{len(tests)} tests passed")
        print("=" * 60)
        return 0 if passed == len(tests) else 1

    finally:
        stop_server()


if __name__ == "__main__":
    sys.exit(main())
