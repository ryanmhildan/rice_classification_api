"""
models.py
Definisi tabel basis data menggunakan SQLModel.
Terdapat dua tabel dengan relasi satu-ke-banyak:
  - Lahan          : data master lokasi sawah
  - RiwayatDeteksi : histori hasil deteksi kesiapan panen pada satu lahan

Satu Lahan dapat memiliki banyak RiwayatDeteksi (1 : N).
"""

from datetime import datetime
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship


class Lahan(SQLModel, table=True):
    """Tabel master lahan. Menyimpan identitas dan lokasi setiap sawah."""

    id_lahan: Optional[int] = Field(default=None, primary_key=True)
    nama_lahan: str = Field(index=True)            # contoh: "Sawah Ciparay Blok A"
    latitude: float                                 # titik tengah lahan (WGS84)
    longitude: float                                # titik tengah lahan (WGS84)
    luas_estimasi_ha: Optional[float] = None        # estimasi luas dalam hektar
    created_at: datetime = Field(default_factory=datetime.now)

    # relasi: satu lahan punya banyak riwayat deteksi
    riwayat: List["RiwayatDeteksi"] = Relationship(back_populates="lahan")


class RiwayatDeteksi(SQLModel, table=True):
    """Tabel histori deteksi. Setiap baris adalah satu kali pemrosesan citra."""

    id_deteksi: Optional[int] = Field(default=None, primary_key=True)

    # foreign key yang menghubungkan deteksi ini ke satu lahan
    id_lahan: int = Field(foreign_key="lahan.id_lahan", index=True)

    timestamp: datetime = Field(default_factory=datetime.now)
    verdict: str                                    # "SIAP PANEN" / "BELUM SIAP PANEN"
    verdict_class: int                              # 1 = siap, 0 = belum
    persentase_kematangan: float                    # persentase piksel kuning terhadap padi
    threshold: float                                # ambang batas yang dipakai
    confidence_margin_pp: Optional[float] = None    # jarak ke threshold (percentage points)
    crs: Optional[str] = None                       # contoh "EPSG:32748"
    bounds_wgs84: Optional[str] = None              # disimpan sebagai teks JSON 4 nilai

    # path berkas (file besar tetap di filesystem, di sini hanya alamatnya)
    path_orthophoto: Optional[str] = None
    path_classification: Optional[str] = None
    path_orthophoto_web: Optional[str] = None
    path_overlay: Optional[str] = None
    path_visualisasi: Optional[str] = None

    # relasi balik ke lahan
    lahan: Optional[Lahan] = Relationship(back_populates="riwayat")
