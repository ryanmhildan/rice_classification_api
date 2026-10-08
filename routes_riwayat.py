"""
routes_riwayat.py
Kumpulan endpoint FastAPI untuk mengakses data lahan dan histori deteksi.

Cara memasang di aplikasi utama (main.py):

    from routes_riwayat import router as router_riwayat
    app.include_router(router_riwayat)

Pastikan pula init_db() dipanggil saat startup, contoh:

    from database import init_db
    @app.on_event("startup")
    def on_startup():
        init_db()
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session
from models import Lahan, RiwayatDeteksi
from crud import ambil_riwayat_lahan

router = APIRouter(prefix="/api", tags=["riwayat"])


@router.get("/lahan", response_model=List[Lahan])
def daftar_lahan(session: Session = Depends(get_session)):
    """Menampilkan seluruh lahan yang terdaftar."""
    return session.exec(select(Lahan)).all()


@router.get("/lahan/{id_lahan}", response_model=Lahan)
def detail_lahan(id_lahan: int, session: Session = Depends(get_session)):
    """Menampilkan satu lahan berdasarkan id."""
    lahan = session.get(Lahan, id_lahan)
    if not lahan:
        raise HTTPException(status_code=404, detail="Lahan tidak ditemukan")
    return lahan


@router.get("/lahan/{id_lahan}/riwayat", response_model=List[RiwayatDeteksi])
def riwayat_per_lahan(id_lahan: int, session: Session = Depends(get_session)):
    """Menampilkan histori deteksi satu lahan, terbaru lebih dulu.
    Endpoint inilah yang memperlihatkan tren kematangan sebuah sawah dari waktu ke waktu."""
    lahan = session.get(Lahan, id_lahan)
    if not lahan:
        raise HTTPException(status_code=404, detail="Lahan tidak ditemukan")
    return ambil_riwayat_lahan(session, id_lahan)


@router.get("/riwayat", response_model=List[RiwayatDeteksi])
def semua_riwayat(limit: int = 100, session: Session = Depends(get_session)):
    """Menampilkan seluruh riwayat deteksi lintas lahan, dibatasi sejumlah limit."""
    query = select(RiwayatDeteksi).order_by(RiwayatDeteksi.timestamp.desc()).limit(limit)
    return session.exec(query).all()


@router.get("/riwayat/{id_deteksi}", response_model=RiwayatDeteksi)
def detail_riwayat(id_deteksi: int, session: Session = Depends(get_session)):
    """Menampilkan satu hasil deteksi berdasarkan id."""
    deteksi = session.get(RiwayatDeteksi, id_deteksi)
    if not deteksi:
        raise HTTPException(status_code=404, detail="Riwayat tidak ditemukan")
    return deteksi
