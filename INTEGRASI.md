# Panduan Integrasi Database SQLite ke Sistem

## 1. Pasang pustaka
```bash
pip install sqlmodel
```

## 2. Letakkan berkas
Salin keempat berkas ini ke dalam folder `rice_classification_api/`:
- `models.py`
- `database.py`
- `crud.py`
- `routes_riwayat.py`

## 3. Aktifkan di aplikasi utama (`main.py`)
Tambahkan baris berikut:
```python
from database import init_db
from routes_riwayat import router as router_riwayat

app.include_router(router_riwayat)

@app.on_event("startup")
def on_startup():
    init_db()   # membuat rice_harvest.db dan tabelnya bila belum ada
```

## 4. Simpan hasil klasifikasi ke database
Di endpoint yang menghasilkan klasifikasi (misalnya `/classify` atau `/upload-manual`),
setelah variabel `hasil` (dict JSON) terbentuk, tambahkan:
```python
from sqlmodel import Session
from database import engine
from crud import simpan_hasil_deteksi

with Session(engine) as session:
    # nama_lahan opsional. Bila None, lahan dikenali otomatis dari koordinat.
    simpan_hasil_deteksi(session, hasil, nama_lahan=None)
```

## 5. Endpoint baru yang tersedia
- `GET /api/lahan` — daftar semua lahan
- `GET /api/lahan/{id_lahan}` — detail satu lahan
- `GET /api/lahan/{id_lahan}/riwayat` — histori deteksi satu lahan (tren kematangan)
- `GET /api/riwayat` — semua riwayat lintas lahan
- `GET /api/riwayat/{id_deteksi}` — detail satu deteksi

## 6. Melihat isi database
Buka berkas `rice_harvest.db` dengan aplikasi gratis **DB Browser for SQLite**
untuk melihat tabel `lahan` dan `riwayat_deteksi` secara visual.

## Catatan penting
- File besar (GeoTIFF, PNG) TETAP disimpan di filesystem. Database hanya menyimpan
  metadata, hasil, dan path filenya. Ini desain hibrida yang merupakan praktik standar.
- Periksa urutan `bounds_wgs84` pada JSON sistem Anda. Fungsi `hitung_titik_tengah`
  di `crud.py` mengasumsikan urutan [min_lon, min_lat, max_lon, max_lat].
  Bila berbeda, sesuaikan baris tersebut.
