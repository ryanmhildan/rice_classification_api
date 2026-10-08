"""
crud.py
Fungsi-fungsi untuk membaca dan menulis data ke basis data.
CRUD = Create, Read, Update, Delete.

Inti dari modul ini adalah:
  - get_or_create_lahan : mencari lahan terdekat, atau membuat lahan baru
  - simpan_hasil_deteksi: menyimpan satu hasil klasifikasi ke tabel riwayat
"""

import json
import math
from typing import Optional, List

from sqlmodel import Session, select

from models import Lahan, RiwayatDeteksi


def haversine_meter(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Menghitung jarak dua titik koordinat (dalam meter) memakai rumus Haversine."""
    R = 6_371_000  # jari-jari bumi dalam meter
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def hitung_titik_tengah(bounds_wgs84: list) -> tuple:
    """
    Menghitung titik tengah (latitude, longitude) dari bounds.
    Asumsi urutan bounds adalah [min_lon, min_lat, max_lon, max_lat].
    Sesuaikan bila urutan pada JSON sistem Anda berbeda.
    """
    min_lon, min_lat, max_lon, max_lat = bounds_wgs84
    lat_tengah = (min_lat + max_lat) / 2
    lon_tengah = (min_lon + max_lon) / 2
    return lat_tengah, lon_tengah


def get_or_create_lahan(
    session: Session,
    latitude: float,
    longitude: float,
    nama_lahan: Optional[str] = None,
    radius_m: float = 50.0,
    luas_estimasi_ha: Optional[float] = None,
) -> Lahan:
    """
    Mencari lahan yang sudah ada dalam radius tertentu dari titik koordinat.
    Bila ditemukan, lahan tersebut dipakai ulang sehingga deteksi baru menjadi
    bagian dari histori lahan yang sama. Bila tidak ada, lahan baru dibuat.
    """
    daftar_lahan = session.exec(select(Lahan)).all()
    for lahan in daftar_lahan:
        jarak = haversine_meter(latitude, longitude, lahan.latitude, lahan.longitude)
        if jarak <= radius_m:
            return lahan  # pakai lahan yang sudah ada

    # tidak ada lahan terdekat, buat lahan baru
    if nama_lahan is None:
        nama_lahan = f"Lahan {latitude:.5f}, {longitude:.5f}"
    lahan_baru = Lahan(
        nama_lahan=nama_lahan,
        latitude=latitude,
        longitude=longitude,
        luas_estimasi_ha=luas_estimasi_ha,
    )
    session.add(lahan_baru)
    session.commit()
    session.refresh(lahan_baru)
    return lahan_baru


def simpan_hasil_deteksi(
    session: Session,
    hasil: dict,
    nama_lahan: Optional[str] = None,
) -> RiwayatDeteksi:
    """
    Menyimpan satu hasil klasifikasi ke tabel riwayat_deteksi.
    Parameter 'hasil' adalah dict JSON keluaran modul klasifikasi
    (struktur sama dengan berkas JSON per hasil).
    """
    bounds = hasil.get("bounds_wgs84")
    if bounds and len(bounds) == 4:
        lat_tengah, lon_tengah = hitung_titik_tengah(bounds)
    else:
        # fallback bila bounds tidak tersedia
        lat_tengah, lon_tengah = 0.0, 0.0

    lahan = get_or_create_lahan(
        session,
        latitude=lat_tengah,
        longitude=lon_tengah,
        nama_lahan=nama_lahan,
    )

    files = hasil.get("files", {})
    deteksi = RiwayatDeteksi(
        id_lahan=lahan.id_lahan,
        verdict=hasil.get("verdict", ""),
        verdict_class=hasil.get("verdict_class", 0),
        persentase_kematangan=hasil.get("yellow_pct_of_rice", 0.0),
        threshold=hasil.get("threshold_used", 0.0),
        confidence_margin_pp=hasil.get("confidence_margin_pp"),
        crs=hasil.get("crs"),
        bounds_wgs84=json.dumps(bounds) if bounds else None,
        path_orthophoto=files.get("orthophoto"),
        path_classification=files.get("classification"),
        path_orthophoto_web=files.get("orthophoto_web_png"),
        path_overlay=files.get("classification_overlay_png"),
        path_visualisasi=files.get("visualization"),
    )
    session.add(deteksi)
    session.commit()
    session.refresh(deteksi)
    return deteksi


def ambil_riwayat_lahan(session: Session, id_lahan: int) -> List[RiwayatDeteksi]:
    """Mengambil seluruh riwayat deteksi satu lahan, diurutkan dari yang terbaru."""
    query = (
        select(RiwayatDeteksi)
        .where(RiwayatDeteksi.id_lahan == id_lahan)
        .order_by(RiwayatDeteksi.timestamp.desc())
    )
    return session.exec(query).all()
