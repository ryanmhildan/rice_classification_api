# CLAUDE.md — Backend Rice Classification API

> Project context untuk Claude Code & AI assistant. Dibaca otomatis di awal setiap sesi.

## 1. Tentang Proyek Ini

Backend FastAPI untuk skripsi **Sistem Deteksi Kesiapan Panen Padi Menggunakan Citra Drone Berbasis Edge Computing dan SIG** oleh **Ryan Muhammad Hildan (NIM 10122475)** — UNIKOM 2026.

Backend ini adalah **bagian 2 dari 3** arsitektur sistem skripsi:

```
[1] Next.js Frontend (port 3001)
        ↕ HTTP
[2] FastAPI Backend (port 8000)   ← FOLDER INI
        ↕ PyODM
[3] NodeODM Docker (port 3000)
```

Tugas backend: terima request dari Next.js → orchestrate stitching ODM + klasifikasi HSV → return verdict.

## 2. Filosofi Arsitektur

1. **Separation of concerns** — Backend hanya proses gambar, tidak punya UI. Frontend hanya UI, tidak proses gambar.
2. **Stateless API** — Semua state stitching disimpan di memory `JOBS` dict (cukup untuk skripsi).
3. **Re-use 100%** dari notebook — Logika klasifikasi di `services/classification.py` identical dengan notebook lama. Refactor jadi pure functions tanpa mengubah algoritma.
4. **Edge computing offline** — Tidak ada call ke cloud manapun. NodeODM di localhost via Docker. Semua processing lokal.

## 3. Struktur Folder

```
rice_classification_api/
├── api.py                       ← FastAPI app (endpoint definitions)
├── pipeline.py                  ← CLI wrapper untuk testing/subprocess
├── services/                    ← Business logic (independen dari framework)
│   ├── __init__.py
│   ├── stitching.py             ← Wrap PyODM untuk komunikasi NodeODM
│   └── classification.py        ← Klasifikasi HSV (refactor dari notebook)
├── requirements.txt
├── setup_environment.bat        ← Setup venv + install requirements
├── start_api.bat                ← Jalankan uvicorn
├── sample_test.py               ← Verifikasi instalasi
├── BACKEND_API.md               ← Kontrak API untuk frontend
├── CLAUDE.md                    ← Dokumen ini
├── data/
│   └── drone_images/            ← Input dari rekan se-skripsi (autonomous drone)
└── output/
    ├── uploads/<job_id>/        ← Foto drone upload per job
    ├── orthophoto/<job_id>/     ← Output stitching ODM
    ├── classification/          ← GeoTIFF klasifikasi
    ├── visualization/           ← PNG peta verdict (DPI 300)
    └── results/                 ← JSON ringkasan
```

## 4. Pipeline Stages

| Stage | Module | Function | Input | Output |
|---|---|---|---|---|
| 1. Validate | api.py | `submit_stitch_job()` | UploadFile[] | job_id |
| 2. Stitch | services/stitching.py | `stitch()` | Path[] | orthophoto.tif |
| 3. Load | services/classification.py | `load_orthophoto()` | Path | dict {rgb, mask_valid, crs, ...} |
| 4. Preprocess | services/classification.py | `preprocess()` | rgb array | hsv array |
| 5. Segment | services/classification.py | `segment()` | hsv, mask_valid | {mask_yellow, mask_green} |
| 6. Verdict | services/classification.py | `classify_verdict()` | masks, threshold | dict stats |
| 7. Export GeoTIFF | services/classification.py | `export_classification_geotiff()` | masks, crs | path |
| 8. Export PNG | services/classification.py | `export_visualization_png()` | rgb, masks, stats | path |

## 5. Parameter Teknis (TIDAK BOLEH Diubah Tanpa Konfirmasi User)

```python
# HSV thresholds (skala OpenCV)
# hsv_upper_yellow[0]=34 dan hsv_lower_green[0]=35 sengaja saling lepas
# (tidak beririsan) di sumbu Hue — lihat services/classification.py::segment()
# untuk resolusi irisan pasca-morfologi yang menangani sisa tumpang tindih
# akibat operasi Closing (dilasi).
hsv_lower_yellow = [20, 60, 60]    # H, S, V
hsv_upper_yellow = [34, 255, 255]
hsv_lower_green  = [35, 40, 40]
hsv_upper_green  = [85, 255, 255]

# Pra-pemrosesan
gaussian_kernel  = 5
clahe_clip_limit = 2.0
clahe_tile_size  = 8
morph_kernel     = 5

# Klasifikasi
threshold_default = 0.60   # 60% kuning → SIAP PANEN

# NodeODM
host = "localhost"
port = 3000
odm_options = {
    "orthophoto-resolution": 5,      # cm/px
    "feature-quality": "medium",     # low/medium/high/ultra
    "fast-orthophoto": True,         # skip 3D model
    "auto-boundary": True,
    "min-num-features": 8000,
}
```

Nilai-nilai ini sudah dipilih dengan justifikasi spesifik (lihat naskah BAB 3 user). Jangan ubah secara unilateral.

## 6. Gaya Kode

1. **Komentar inline dalam Bahasa Indonesia.** Nama variabel tetap Inggris (`mature_pixels`, bukan `piksel_matang`).
2. **Pesan log & error dalam Bahasa Indonesia** dengan emoji status sebisa mungkin (✅ ❌ ⚠️).
3. **Type hints lengkap.** Pakai `from __future__ import annotations` agar bisa pakai `list[Path]` dan sebagainya di Python 3.10+.
4. **Try-except pada setiap operasi I/O & network.** Pesan error harus jelas penyebab + solusi.
5. **Pure functions** di `services/`. Side-effect (file write, print) hanya di `api.py` dan `pipeline.py`.
6. **Reproducibility:** versi library terkunci di `requirements.txt`.

## 7. Cara Menjalankan

### Pertama Kali
```bash
# 1. Install dependencies
setup_environment.bat

# 2. Pastikan Docker Desktop jalan & NodeODM container aktif
# (lihat folder rice_orthophoto_pipeline untuk start_nodeodm.bat)

# 3. Jalankan API
start_api.bat

# 4. Cek API jalan
# Buka http://localhost:8000/docs di browser
```

### Selanjutnya
```bash
start_api.bat   # cukup ini saja
```

## 8. Testing Manual

### Via CLI (tanpa Next.js)
```bash
# Aktifkan venv dulu
venv\Scripts\activate.bat

# Cek NodeODM
python pipeline.py check-nodeodm

# Klasifikasi orthophoto yang sudah ada
python pipeline.py classify --ortho data/sample_orthophoto.tif --output output

# Pipeline lengkap dari foto drone
python pipeline.py full --images data/drone_images --output output

# Output JSON only (untuk parsing)
python pipeline.py classify --ortho ortho.tif --output out --json-only
```

### Via cURL (test endpoint HTTP)
```bash
# Health
curl http://localhost:8000/health

# Upload + stitch
curl -X POST http://localhost:8000/jobs/stitch \
  -F "images=@foto1.jpg" -F "images=@foto2.jpg" \
  -F "images=@foto3.jpg" -F "images=@foto4.jpg"

# Polling
curl http://localhost:8000/jobs/abc123def456
```

### Via Swagger UI
Buka `http://localhost:8000/docs` — semua endpoint bisa di-test interaktif dari browser.

## 9. Known Issues & Solutions

| Issue | Penyebab | Solusi |
|---|---|---|
| `Cannot connect to NodeODM` | Docker belum jalan / container belum start | Jalankan Docker Desktop, lalu `docker start nodeodm` |
| `ModuleNotFoundError: services` | Dijalankan dari folder yang salah | `cd` ke folder rice_classification_api dulu |
| Upload gagal `413 Payload Too Large` | File terlalu besar | Edit uvicorn config: `--limit-max-requests 1000` di start_api.bat |
| CORS error di browser console | Origin Next.js belum di whitelist | Edit `allow_origins` di api.py |
| `rasterio` install gagal di Windows | Butuh MSVC Build Tools | Install Microsoft C++ Build Tools |
| ODM gagal: feature kurang | Foto kurang overlap atau resolusi rendah | Pastikan overlap drone 70-80%, atau set `feature-quality: "low"` |

## 10. Roadmap Pengembangan

| Status | Fitur | Priority |
|---|---|---|
| ✅ | Stitching async + polling | P0 |
| ✅ | Klasifikasi HSV 2 kelas | P0 |
| ✅ | Export GeoTIFF + PNG + JSON | P0 |
| ✅ | CORS untuk Next.js | P0 |
| ⏳ | Halaman riwayat (GET /results) | P1 |
| ⏳ | Slider threshold di frontend (re-classify tanpa re-stitch) | P1 |
| 🔮 | WebSocket untuk real-time progress | P2 (opsional) |
| 🔮 | Database persistence (SQLite) | P2 (opsional) |
| 🔮 | Auth via token sederhana | P3 (kalau perlu) |

## 11. Catatan Akademis (Untuk Sidang)

### Justifikasi Pilihan FastAPI

Kalau penguji tanya "kenapa FastAPI bukan Flask?":

> "FastAPI dipilih karena: (1) dukungan async/await native untuk job stitching yang lama, (2) auto-generated OpenAPI/Swagger documentation memudahkan komunikasi dengan frontend yang dikerjakan terpisah, (3) Pydantic validation otomatis untuk request/response yang mengurangi bug runtime, (4) performa Starlette di belakangnya cocok untuk file upload besar dari foto drone."

### Justifikasi Pemisahan Frontend-Backend

> "Pemisahan frontend (Next.js) dan backend (FastAPI) mengikuti prinsip separation of concerns. Backend Python dapat memanfaatkan ekosistem image processing matang (OpenCV, rasterio, PyODM) yang tidak tersedia di JavaScript. Frontend Next.js fokus pada UI modern berbasis React dengan integrasi peta interaktif Leaflet. Komunikasi via HTTP REST localhost — sesuai paradigma edge computing tanpa cloud."

### Yang Bisa Ditanya Penguji Tentang Backend

1. **"Apa beda async job vs sync job?"** — Stitching butuh 30 menit - 3 jam, browser akan timeout. Solusinya: spawn background task, return job_id, frontend polling status. Klasifikasi cepat (< 1 menit), boleh sync.

2. **"Kenapa pakai in-memory JOBS dict?"** — Untuk skripsi cukup. Limitations: hilang saat restart, tidak bisa scale multi-process. Production solution: Redis atau database.

3. **"Bagaimana handle file besar dari upload?"** — FastAPI menggunakan streaming via `python-multipart`. File tidak loaded ke memory penuh, langsung ditulis ke disk per chunk.

4. **"Kenapa CORS perlu?"** — Browser block request lintas-origin by default (security). Next.js (port 3001) → FastAPI (port 8000) = lintas-origin. Whitelist origin localhost di middleware.

## 12. Catatan untuk Rekan Se-skripsi (Drone Autopilot)

Rekan mengerjakan autonomous drone yang akan output foto ke folder. **Kontrak data yang disepakati:**

```
Rekan output foto → data/drone_images/*.jpg
        ↓
Sistem ini scan folder + upload ke FastAPI
```

Atau alternatif kalau real-time:

```
Rekan POST foto → http://localhost:8000/jobs/stitch
```

Format foto:
- JPG dengan EXIF GPS aktif
- Minimum 4 foto, recommended 20-100
- Overlap 70-80% antar foto
- Resolusi: bebas, tapi semakin besar = semakin lama stitching

## 13. Sumber Eksternal

- **OpenDroneMap**: https://www.opendronemap.org/
- **NodeODM API docs**: https://docs.opendronemap.org/api/
- **PyODM**: https://github.com/OpenDroneMap/PyODM
- **FastAPI**: https://fastapi.tiangolo.com/
- **Rasterio**: https://rasterio.readthedocs.io/
- **OpenCV-Python**: https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html
