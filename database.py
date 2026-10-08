"""
database.py
Pengaturan koneksi basis data SQLite.

SQLite dipilih karena ringan, tanpa server, dan berupa satu berkas .db saja,
sehingga selaras dengan konsep edge computing yang berjalan mandiri di perangkat lokal.

Letak berkas database dibuat otomatis di FOLDER INDUK (folder SKRIPSI yang memuat
rice_classification_api, rice_orthophoto_pipeline, dan rice-harvest-web). Dengan cara ini,
API dan notebook menulis ke SATU berkas database yang sama, di mana pun keduanya dijalankan.
"""

from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session

# File ini berada di dalam folder rice_classification_api.
#   Path(__file__).resolve().parent        -> folder rice_classification_api
#   Path(__file__).resolve().parent.parent -> folder induk SKRIPSI (memuat ketiga folder)
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "rice_harvest.db"

# Jika struktur folder Anda berbeda dan path otomatis di atas kurang tepat,
# Anda dapat menetapkannya secara manual dengan menghapus tanda komentar baris berikut:
# DB_PATH = Path(r"C:\skripsi\SISTEM\rice_harvest.db")

# as_posix() mengubah backslash Windows menjadi slash agar valid untuk URL SQLite.
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# connect_args diperlukan agar SQLite dapat diakses dari banyak thread FastAPI.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Membuat seluruh tabel bila belum ada. Panggil sekali saat aplikasi start."""
    import models  # noqa: F401  (memastikan definisi tabel terbaca lebih dulu)
    SQLModel.metadata.create_all(engine)
    print(f"Database siap di: {DB_PATH}")


def get_session() -> Session:
    """Dependency FastAPI untuk menyediakan sesi basis data per request."""
    with Session(engine) as session:
        yield session
