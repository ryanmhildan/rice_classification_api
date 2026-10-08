# Rice Harvest Classification API

Backend FastAPI untuk sistem deteksi kesiapan panen padi berbasis segmentasi warna HSV pada orthophoto hasil pemetaan drone.

Bagian dari skripsi: **"Deteksi dan Pemetaan Kesiapan Panen Padi Menggunakan Citra Drone Berbasis Edge Computing dan Sistem Informasi Geografis (SIG)"**
Ryan Muhammad Hildan — Teknik Informatika UNIKOM 2026

---

## Arsitektur Sistem

```
[Drone] → [Foto JPG] → [NodeODM Docker :3000] → [Orthophoto GeoTIFF]
                                ↕ PyODM
                       [FastAPI Backend :8000]   ← repo ini
                                ↕ HTTP REST
                       [Next.js Frontend :3001]
```

Sistem berjalan **sepenuhnya offline** (edge computing) di laptop Ground Control Station. Tidak ada ketergantungan cloud.

---

## Fitur

- Upload batch foto drone → submit job stitching ke NodeODM secara async
- Polling status job stitching (queued → running → completed/failed)
- Segmentasi warna HSV: piksel **kuning** (matang) vs **hijau** (belum matang)
- Pra-pemrosesan: Gaussian Blur + CLAHE + konversi RGB→HSV
- Verdict otomatis: **SIAP PANEN** (≥ 60% kuning) atau **BELUM SIAP PANEN** (< 60%)
- Export output: GeoTIFF klasifikasi, PNG overlay Leaflet, PNG visualisasi, JSON statistik
- Endpoint serve file langsung ke frontend
- Riwayat semua hasil klasifikasi via `GET /results`
- Swagger UI tersedia di `/docs`

---

## Pipeline

```
Foto drone (JPG + EXIF GPS)
        ↓  upload & submit ke NodeODM
Orthophoto.tif (georeferensi WGS84)
        ↓  Gaussian Blur + CLAHE + RGB→HSV
HSV array
        ↓  thresholding kuning & hijau
Mask piksel matang / belum matang
        ↓  hitung rasio
Verdict + statistik piksel
        ↓  export
GeoTIFF klasifikasi + PNG visualisasi + JSON statistik
```

---

## Prasyarat

| Software | Versi | Keterangan |
|---|---|---|
| Python | 3.10+ | Direkomendasikan 3.12 |
| Docker Desktop | terbaru | Untuk NodeODM |
| NodeODM | image `opendronemap/nodeodm` | Stitching engine |

---

## Instalasi

**1. Clone repo dan masuk ke folder:**
```cmd
git clone <repo-url>
cd rice_classification_api
```

**2. Setup virtual environment dan install dependencies:**
```cmd
setup_environment.bat
```

Atau manual:
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

> Catatan Windows: `rasterio` membutuhkan Microsoft C++ Build Tools. Install dari [visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) jika instalasi gagal.

**3. Jalankan NodeODM (pertama kali):**
```cmd
docker run -d -p 3000:3000 --name nodeodm opendronemap/nodeodm
```

Selanjutnya cukup:
```cmd
docker start nodeodm
```

**4. Jalankan API:**
```cmd
start_api.bat
```

**5. Verifikasi:**
- NodeODM: buka `http://localhost:3000`
- Backend API: buka `http://localhost:8000/docs`

---

## Struktur Folder

```
rice_classification_api/
├── api.py                    # FastAPI app — 9 endpoint
├── pipeline.py               # CLI orchestrator (alternatif ke API)
├── services/
│   ├── stitching.py          # Wrapper PyODM untuk NodeODM
│   └── classification.py     # Segmentasi HSV + ekspor output
├── requirements.txt
├── setup_environment.bat
├── start_api.bat
├── sample_test.py            # Verifikasi instalasi
├── smoke_test_api.py         # Test 9 endpoint end-to-end
├── BACKEND_API.md            # Kontrak API (source of truth)
├── data/
│   └── drone_images/         # Input foto drone
└── output/
    ├── uploads/              # Foto per job (temp)
    ├── orthophoto/           # Hasil stitching (.tif)
    ├── orthophoto_web/       # PNG RGBA untuk Leaflet overlay
    ├── classification/       # GeoTIFF hasil klasifikasi
    ├── classification_web/   # PNG overlay klasifikasi untuk Leaflet
    ├── visualization/        # PNG composite (untuk dokumentasi)
    └── results/              # JSON ringkasan per run
```

---

## Endpoint API

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/` | Info API |
| `GET` | `/health` | Health check |
| `GET` | `/nodeodm/status` | Cek koneksi NodeODM |
| `POST` | `/jobs/stitch` | Upload foto + mulai stitching (async) |
| `GET` | `/jobs/{job_id}` | Polling status job |
| `POST` | `/jobs/{job_id}/classify` | Klasifikasi setelah stitching selesai |
| `POST` | `/classify` | Klasifikasi orthophoto langsung (skip stitching) |
| `GET` | `/files/{kategori}/{nama}` | Serve file output |
| `GET` | `/results` | List semua hasil |

Dokumentasi lengkap dengan contoh request/response: lihat [BACKEND_API.md](BACKEND_API.md) atau Swagger UI di `http://localhost:8000/docs`.

### Contoh: upload foto dan klasifikasi

```bash
# 1. Upload foto (minimum 4 file JPG)
curl -X POST http://localhost:8000/jobs/stitch \
  -F "images=@foto1.jpg" \
  -F "images=@foto2.jpg" \
  -F "images=@foto3.jpg" \
  -F "images=@foto4.jpg"

# Response: { "job_id": "abc123", "status": "queued", ... }

# 2. Polling sampai status = "completed" (stitching ~30 menit - 3 jam)
curl http://localhost:8000/jobs/abc123

# 3. Klasifikasi setelah selesai
curl -X POST "http://localhost:8000/jobs/abc123/classify?threshold=0.60"

# Response: { "verdict": "SIAP PANEN", "yellow_pct_of_rice": 65.34, ... }
```

---

## Parameter Teknis

Parameter HSV dan ODM telah dikalibrasi untuk kondisi lahan padi dan tidak boleh diubah sembarangan:

| Parameter | Nilai | Keterangan |
|---|---|---|
| `hsv_lower_yellow` | `[20, 60, 60]` | Batas bawah warna kuning (matang) |
| `hsv_upper_yellow` | `[40, 255, 255]` | Batas atas warna kuning |
| `hsv_lower_green` | `[35, 40, 40]` | Batas bawah warna hijau (belum matang) |
| `hsv_upper_green` | `[85, 255, 255]` | Batas atas warna hijau |
| `threshold_default` | `0.60` | Persentase kuning minimum untuk SIAP PANEN |
| `gaussian_kernel` | `5` | Kernel Gaussian Blur |
| `clahe_clip_limit` | `2.0` | CLAHE contrast limit |
| `orthophoto_resolution` | `5 cm/px` | Resolusi target ODM |

---

## CLI Usage

```bash
# Aktifkan venv
venv\Scripts\activate.bat

# Cek koneksi NodeODM
python pipeline.py check-nodeodm

# Klasifikasi orthophoto yang sudah ada
python pipeline.py classify --ortho data/sample.tif --output output

# Pipeline lengkap dari folder foto drone
python pipeline.py full --images data/drone_images --output output

# Output JSON saja
python pipeline.py classify --ortho ortho.tif --output out --json-only
```

---

## Testing

```bash
# Verifikasi instalasi (tanpa NodeODM)
python sample_test.py

# Smoke test semua endpoint (NodeODM + API harus jalan)
python smoke_test_api.py
```

---

## Output yang Dihasilkan

Setiap run klasifikasi menghasilkan 5 file di folder `output/`:

| File | Format | Kegunaan |
|---|---|---|
| `orthophoto/*.tif` | GeoTIFF WGS84 | Buka di QGIS untuk validasi |
| `classification/*.tif` | GeoTIFF 1-band | Peta klasifikasi georeferensi |
| `orthophoto_web/*.png` | PNG RGBA | Overlay orthophoto di Leaflet |
| `classification_web/*.png` | PNG RGBA | Overlay klasifikasi di Leaflet |
| `visualization/*.png` | PNG RGB | Gambar komposit untuk dokumentasi |
| `results/*.json` | JSON | Statistik lengkap (verdict, piksel, bounds) |

---

## Troubleshooting

| Error | Penyebab | Solusi |
|---|---|---|
| `Cannot connect to NodeODM` | Docker belum jalan | Jalankan Docker Desktop → `docker start nodeodm` |
| `ModuleNotFoundError: services` | Folder aktif salah | `cd rice_classification_api` |
| `rasterio` install gagal | MSVC Build Tools belum ada | Install Microsoft C++ Build Tools |
| ODM gagal: fitur kurang | Foto kurang overlap | Pastikan overlap drone 70–80% |
| WinError 32 saat stitching | OneDrive file locking | Pindahkan proyek dari `Documents/` ke `C:\skripsi\` |
| `413 Payload Too Large` | File terlalu besar | Edit `start_api.bat`: tambah `--limit-max-requests` |

---

## Dependensi Utama

| Library | Versi | Fungsi |
|---|---|---|
| FastAPI | 0.115.0 | Web framework async |
| OpenCV | 4.10.0 | Segmentasi HSV |
| Rasterio | 1.3.11 | Baca/tulis GeoTIFF georeferensi |
| PyODM | 1.5.10 | Client NodeODM untuk stitching |
| NumPy | 1.26.4 | Operasi array piksel |
| Pydantic | 2.9.2 | Validasi request/response |

---

## Lisensi

Proyek ini dibuat untuk keperluan skripsi akademis. Tidak untuk distribusi komersial.
