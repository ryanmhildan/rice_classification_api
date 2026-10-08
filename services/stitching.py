"""
services/stitching.py
=====================
Modul stitching foto drone menjadi orthophoto via NodeODM (Docker).
Bertanggung jawab atas semua komunikasi dengan PyODM/NodeODM.

Modul ini dapat dipanggil:
  1. Langsung dari pipeline.py (CLI)
  2. Dari FastAPI endpoint (api.py)
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional
import shutil
import time

from pyodm import Node
from pyodm.exceptions import NodeConnectionError


# Status code dari NodeODM REST API
STATUS_QUEUED = 10
STATUS_RUNNING = 20
STATUS_FAILED = 30
STATUS_COMPLETED = 40
STATUS_CANCELED = 50


class StitchingError(Exception):
    """Raised ketika stitching gagal karena alasan apapun."""
    pass


def cek_nodeodm(host: str = "localhost", port: int = 3000,
                token: str = "") -> dict:
    """
    Cek apakah NodeODM responsif. Kembalikan dict info atau raise StitchingError.

    Returns:
        dict berisi: version, engine, engine_version, max_parallel_tasks, task_queue_count
    """
    try:
        node = Node(host, port, token=token, timeout=10)
        info = node.info()
        return {
            "ok": True,
            "version": info.version,
            "engine": info.engine,
            "engine_version": info.engine_version,
            "max_parallel_tasks": info.max_parallel_tasks,
            "task_queue_count": info.task_queue_count,
        }
    except NodeConnectionError as e:
        raise StitchingError(
            f"Tidak bisa konek ke NodeODM di {host}:{port}.\n"
            f"  Pastikan Docker Desktop jalan dan container NodeODM aktif.\n"
            f"  Jalankan: start_nodeodm.bat (atau docker start nodeodm)\n"
            f"  Detail: {e}"
        )


def stitch(
    image_paths: list[Path],
    output_dir: Path,
    task_name: str = "rice_paddy",
    host: str = "localhost",
    port: int = 3000,
    token: str = "",
    odm_options: Optional[dict] = None,
    max_wait_minutes: int = 120,
    polling_interval: int = 10,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """
    Stitch foto drone jadi orthophoto via NodeODM.

    Args:
        image_paths: list path foto drone (JPG)
        output_dir: folder untuk menyimpan hasil
        task_name: nama task di NodeODM
        host, port, token: koneksi NodeODM
        odm_options: parameter ODM (lihat default di bawah)
        max_wait_minutes: timeout dalam menit
        polling_interval: detik antar polling
        progress_callback: function(progress_pct: int, status: str) -> None
            Dipanggil tiap polling untuk update progress.

    Returns:
        Path ke orthophoto.tif hasil stitching.

    Raises:
        StitchingError: jika gagal.
    """
    if len(image_paths) < 4:
        raise StitchingError(
            f"Minimum 4 foto diperlukan untuk stitching, hanya ada {len(image_paths)}."
        )

    # Default options optimized for RAM 8GB
    if odm_options is None:
        odm_options = {
            "orthophoto-resolution": 5,
            "feature-quality": "medium",
            "fast-orthophoto": True,
            "auto-boundary": True,
            "min-num-features": 8000,
        }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect & submit task
    try:
        node = Node(host, port, token=token)
    except Exception as e:
        raise StitchingError(f"Gagal terhubung ke NodeODM: {e}")

    try:
        task = node.create_task(
            files=[str(p) for p in image_paths],
            options=odm_options,
            name=task_name,
        )
    except Exception as e:
        raise StitchingError(f"Gagal membuat task ODM: {e}")

    # Polling status
    t_start = time.time()
    deadline = t_start + max_wait_minutes * 60
    last_progress = -1

    while True:
        info = task.info()
        status = info.status.value if hasattr(info.status, "value") else info.status
        progress = int(info.progress) if info.progress else 0

        # Callback untuk update UI
        if progress_callback and progress > last_progress:
            status_text = {
                STATUS_QUEUED: "Antrian",
                STATUS_RUNNING: "Stitching berjalan",
            }.get(status, f"Status {status}")
            progress_callback(progress, status_text)
            last_progress = progress

        if status == STATUS_COMPLETED:
            break
        elif status == STATUS_FAILED:
            try:
                log_lines = task.output(line=0)
                log_tail = "\n".join(log_lines[-30:]) if log_lines else "(log kosong)"
            except Exception:
                log_tail = "(tidak bisa baca log)"
            raise StitchingError(
                f"ODM task GAGAL.\n\nLog terakhir:\n{log_tail}\n\n"
                f"Penyebab umum: overlap foto kurang, EXIF GPS tidak ada, "
                f"atau RAM tidak cukup. Coba turunkan feature-quality ke 'low'."
            )
        elif status == STATUS_CANCELED:
            raise StitchingError("ODM task DIBATALKAN.")

        if time.time() > deadline:
            try:
                task.cancel()
            except Exception:
                pass
            raise StitchingError(
                f"Timeout {max_wait_minutes} menit terlampaui. Task dibatalkan."
            )

        time.sleep(polling_interval)

    # Download hasil — dengan retry + fallback manual extract untuk Windows
    task_folder = output_dir / f"task_{task.uuid[:8]}"
    task_folder.mkdir(exist_ok=True)

    download_folder = _download_with_fallback(task, task_folder)

    # Cari orthophoto.tif
    ortho_path = Path(download_folder) / "odm_orthophoto" / "odm_orthophoto.tif"
    if not ortho_path.exists():
        candidates = list(Path(download_folder).rglob("odm_orthophoto.tif"))
        if not candidates:
            raise StitchingError(
                f"orthophoto.tif tidak ditemukan di {download_folder}"
            )
        ortho_path = candidates[0]

    # Copy ke lokasi standar dengan nama yang bersih
    final_path = output_dir / f"{task_name}_orthophoto.tif"
    shutil.copy2(ortho_path, final_path)

    if progress_callback:
        progress_callback(100, "Selesai")

    return final_path


def _download_with_fallback(task, task_folder: Path) -> str:
    """
    Download asset dari NodeODM dengan retry + fallback manual extract.

    Masalah yang di-handle:
        - WinError 32 di Windows: file dipegang oleh Defender/OneDrive saat
          PyODM coba extract ZIP. Race condition antara download selesai
          dan handle ditutup.

    Strategi:
        1. Coba download normal lewat task.download_assets()
        2. Kalau gagal dengan WinError 32, tunggu 5 detik, retry sekali
        3. Kalau masih gagal, cari file ZIP yang sudah ter-download dan
           extract manual dengan zipfile (lebih toleran terhadap locking)
    """
    import zipfile

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            return task.download_assets(str(task_folder))
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            # Deteksi Windows file locking error
            if "winerror 32" in err_str or "being used by another process" in err_str:
                if attempt == 0:
                    time.sleep(5)  # tunggu file handle dilepas
                    continue
            else:
                # Error lain, jangan retry
                break

    # FALLBACK: cari file ZIP yang sudah ter-download lalu extract manual
    zip_files = list(task_folder.rglob("*.zip"))
    if not zip_files:
        raise StitchingError(
            f"Gagal mengunduh hasil ODM dan tidak menemukan ZIP fallback.\n"
            f"  Error asli: {last_err}\n\n"
            f"SOLUSI untuk Windows:\n"
            f"  1. Tambahkan folder proyek ke pengecualian Windows Defender:\n"
            f"     Windows Security → Virus & threat protection → Exclusions\n"
            f"  2. Pindahkan proyek ke folder yang TIDAK di-sync OneDrive\n"
            f"     (hindari Documents/ atau Desktop/ jika OneDrive aktif)\n"
            f"  3. Retry stitching dari awal"
        )

    # Pakai ZIP yang paling besar (= asset utama)
    zip_path = max(zip_files, key=lambda p: p.stat().st_size)
    extract_dir = zip_path.parent

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)
    except Exception as e:
        raise StitchingError(
            f"Download asset awal gagal: {last_err}\n"
            f"Fallback manual extract juga gagal: {e}\n\n"
            f"File ZIP tersedia di: {zip_path}\n"
            f"Anda dapat extract manual menggunakan WinRAR/7zip,\n"
            f"lalu jalankan klasifikasi via POST /classify dengan path orthophoto."
        )

    return str(extract_dir)