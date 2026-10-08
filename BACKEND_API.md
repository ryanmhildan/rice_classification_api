# Backend API Contract

Dokumen kontrak antara backend FastAPI dan frontend Next.js. Tujuan: setiap orang (Anda, rekan se-skripsi, AI assistant) tahu persis bagaimana memanggil backend tanpa harus baca seluruh source code.

## Base URL

```
http://localhost:8000
```

Dokumentasi interaktif tersedia otomatis di `http://localhost:8000/docs` (Swagger UI bawaan FastAPI).

## Konsep Penting

### Pipeline 2-Tahap

Klasifikasi orthophoto dilakukan dalam 2 tahap terpisah karena stitching ODM butuh **30 menit - 3 jam** sedangkan klasifikasi cepat (< 1 menit):

1. **Stitching (long-running, async)**: upload foto → return `job_id` → polling status sampai selesai
2. **Klasifikasi (fast, sync)**: panggil dengan `job_id` (atau path orthophoto) → langsung dapat verdict

Karena 2 tahap terpisah, **threshold bisa diubah-ubah tanpa re-stitch** — sangat efisien untuk analisis sensitivitas.

### Async Job Pattern

Untuk stitching:
```
POST /jobs/stitch        → {job_id, status: "queued"}
GET  /jobs/{job_id}      → {status: "running", progress: 45}    ← polling
GET  /jobs/{job_id}      → {status: "running", progress: 78}    ← polling
GET  /jobs/{job_id}      → {status: "completed", orthophoto_path: "..."}
POST /jobs/{job_id}/classify  → {verdict, stats, files}
```

Polling interval rekomendasi di frontend: **5 detik**.

## Endpoint Reference

### `GET /` — Info API
Mengembalikan info dasar API dan list endpoint.

**Response:**
```json
{
  "name": "Rice Harvest Classification API",
  "version": "1.0.0",
  "docs": "/docs",
  "endpoints": { ... }
}
```

### `GET /health` — Health Check

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-05-24T11:45:30",
  "output_dir_exists": true,
  "active_jobs": 0,
  "total_jobs": 5
}
```

### `GET /nodeodm/status` — Cek NodeODM

**Success Response (200):**
```json
{
  "ok": true,
  "version": "3.5.4",
  "engine": "odm",
  "engine_version": "3.5.4",
  "max_parallel_tasks": 1,
  "task_queue_count": 0
}
```

**Error Response (503):** Jika NodeODM tidak responsif.
```json
{ "detail": "Tidak bisa konek ke NodeODM..." }
```

### `POST /jobs/stitch` — Upload Foto + Mulai Stitching

**Request:** `multipart/form-data`
- `images` — array file (minimum 4 foto JPG)
- `threshold` — float opsional (default 0.60), disimpan untuk klasifikasi nanti

**cURL Example:**
```bash
curl -X POST http://localhost:8000/jobs/stitch \
  -F "images=@foto1.jpg" \
  -F "images=@foto2.jpg" \
  -F "images=@foto3.jpg" \
  -F "images=@foto4.jpg" \
  -F "threshold=0.60"
```

**Next.js fetch example:**
```javascript
const formData = new FormData();
files.forEach(f => formData.append("images", f));
formData.append("threshold", "0.60");

const res = await fetch("http://localhost:8000/jobs/stitch", {
  method: "POST",
  body: formData,
});
const { job_id } = await res.json();
```

**Success Response (200):**
```json
{
  "job_id": "abc123def456",
  "status": "queued",
  "progress": 0,
  "message": "Menunggu di antrian",
  "created_at": "2026-05-24T11:45:30",
  "n_images": 15,
  "orthophoto_path": null,
  "error": null
}
```

### `GET /jobs/{job_id}` — Polling Status Job

**Success Response (200):**
```json
{
  "job_id": "abc123def456",
  "status": "running",       // queued | running | completed | failed
  "progress": 45,            // 0-100
  "message": "Stitching berjalan",
  "created_at": "2026-05-24T11:45:30",
  "n_images": 15,
  "orthophoto_path": null,   // null kecuali status=completed
  "error": null              // string kalau status=failed
}
```

**Saat completed:**
```json
{
  "job_id": "abc123def456",
  "status": "completed",
  "progress": 100,
  "orthophoto_path": "output/orthophoto/abc123def456/rice_paddy_abc123.tif"
}
```

### `POST /jobs/{job_id}/classify` — Klasifikasi Setelah Stitching

Query parameter:
- `threshold` — float (default 0.60)

**Success Response (200):**
```json
{
  "success": true,
  "timestamp": "20260524_114530",
  "job_id": "abc123def456",
  "orthophoto_width": 5432,
  "orthophoto_height": 4321,
  "crs": "EPSG:4326",
  "bounds": [107.615, -6.917, 107.617, -6.915],
  "verdict": "SIAP PANEN",
  "verdict_class": 1,
  "yellow_pct_of_rice": 65.34,
  "green_pct_of_rice": 34.66,
  "confidence_margin_pp": 5.34,
  "threshold_used": 0.60,
  "n_pixels_total": 23456789,
  "n_pixels_valid": 18234567,
  "n_pixels_rice": 15234567,
  "n_pixels_yellow": 9956234,
  "n_pixels_green": 5278333,
  "bounds_wgs84": [107.615, -6.917, 107.617, -6.915],
  "files": {
    "orthophoto":                 "output/orthophoto/abc123def456/rice_paddy.tif",
    "classification":             "output/classification/rice_paddy_class_20260524_114530.tif",
    "orthophoto_web_png":         "output/orthophoto_web/rice_paddy_ortho_web_20260524_114530.png",
    "classification_overlay_png": "output/classification_web/rice_paddy_class_overlay_20260524_114530.png",
    "visualization":              "output/visualization/rice_paddy_map_20260524_114530.png"
  },
  "duration_seconds": 23.45
}
```

### `POST /classify` — Klasifikasi Langsung (Skip Stitching)

Untuk testing atau kalau orthophoto sudah disediakan dari luar.

**Request:** JSON
```json
{
  "orthophoto_path": "data/orthophoto_sample.tif",
  "threshold": 0.60
}
```

Response sama dengan endpoint sebelumnya.

### `GET /files/{kategori}/{nama_file}` — Serve File Output

Untuk Next.js menampilkan PNG visualisasi atau download GeoTIFF.

**Kategori:** `orthophoto`, `classification`, `visualization`, `results`, `orthophoto_web`, `classification_web`

Kategori baru untuk web overlay Leaflet:
- `orthophoto_web` → PNG RGBA (NoData transparan), untuk `L.imageOverlay` orthophoto
- `classification_web` → PNG RGBA (kuning/hijau di atas transparan), untuk `L.imageOverlay` klasifikasi

**Contoh:**
```
http://localhost:8000/files/visualization/rice_paddy_map_20260524_114530.png
http://localhost:8000/files/classification/rice_paddy_class_20260524_114530.tif
```

Penggunaan di Next.js (untuk `<img>` tag):
```jsx
<img src={`http://localhost:8000/files/visualization/${filename}`} />
```

### `GET /results` — List Semua Hasil

Untuk halaman "Riwayat" di frontend.

**Response:**
```json
{
  "count": 5,
  "results": [
    {
      "filename": "rice_paddy_result_20260524_114530.json",
      "timestamp": "20260524_114530",
      "verdict": "SIAP PANEN",
      "yellow_pct": 65.34,
      "threshold": 0.60
    },
    ...
  ]
}
```

## Error Handling

Semua error mengikuti pola FastAPI:

```json
{ "detail": "Pesan error dalam Bahasa Indonesia" }
```

Status codes umum:
- **400** — input tidak valid (foto < 4, ekstensi salah)
- **404** — resource tidak ditemukan (job_id, file)
- **409** — state conflict (mencoba klasifikasi sebelum stitching selesai)
- **422** — klasifikasi gagal (tidak ada piksel padi terdeteksi)
- **500** — error tak terduga (cek logs uvicorn)
- **503** — NodeODM tidak responsif

## CORS

Backend mengizinkan request dari origin berikut:
- `http://localhost:3000`
- `http://localhost:3001`
- `http://127.0.0.1:3000`
- `http://127.0.0.1:3001`

Jika Next.js dijalankan di port lain, edit `api.py` bagian `allow_origins`.

## TypeScript Types (Untuk Frontend)

Berikut tipe TypeScript yang sebaiknya didefinisikan di `lib/types.ts` frontend:

```typescript
export interface JobInfo {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string;
  created_at: string;
  n_images: number;
  orthophoto_path: string | null;
  error: string | null;
}

export interface ClassificationStats {
  n_pixels_total: number;
  n_pixels_valid: number;
  n_pixels_rice: number;
  n_pixels_yellow: number;
  n_pixels_green: number;
  yellow_pct_of_rice: number;
  green_pct_of_rice: number;
  valid_pct_of_total: number;
  rice_pct_of_valid: number;
  threshold_used: number;
  verdict: "SIAP PANEN" | "BELUM SIAP PANEN";
  verdict_class: 1 | 2;
  confidence_margin_pp: number;
}

export interface ClassificationResult extends ClassificationStats {
  success: boolean;
  timestamp: string;
  job_id: string | null;
  orthophoto_width: number;
  orthophoto_height: number;
  crs: string;
  bounds: [number, number, number, number];  // [minx, miny, maxx, maxy]
  files: {
    orthophoto: string;
    classification: string;
    visualization: string;
  };
  duration_seconds: number;
}

export interface ResultListItem {
  filename: string;
  timestamp: string;
  verdict: "SIAP PANEN" | "BELUM SIAP PANEN";
  yellow_pct: number;
  threshold: number;
}
```

## Catatan Pengembangan

1. **In-memory job store** — `JOBS` dict di `api.py` akan hilang saat server restart. Untuk skripsi cukup. Production pakai Redis atau database.
2. **No authentication** — backend tidak punya auth. Aman karena hanya jalan di localhost. Jangan deploy ke publik tanpa tambahan auth.
3. **CORS allow_origins** — terbatas pada localhost. Edit kalau perlu testing dari device lain di LAN.
4. **File size limits** — FastAPI default 16 MB per file. Untuk foto drone besar, edit `uvicorn` config di `start_api.bat`.
