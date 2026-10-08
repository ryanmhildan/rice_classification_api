"""
sample_test.py
==============
Verifikasi instalasi backend.

Jalankan:
    python sample_test.py
"""
import sys
import importlib


REQUIRED = [
    ("cv2",       "opencv-python"),
    ("numpy",     "numpy"),
    ("PIL",       "Pillow"),
    ("rasterio",  "rasterio"),
    ("shapely",   "shapely"),
    ("pyproj",    "pyproj"),
    ("pyodm",     "pyodm"),
    ("fastapi",   "fastapi"),
    ("uvicorn",   "uvicorn"),
    ("pydantic",  "pydantic"),
    ("matplotlib", "matplotlib"),
    ("pandas",    "pandas"),
    ("skimage",   "scikit-image"),
    ("exifread",  "exifread"),
    ("tqdm",      "tqdm"),
]


def main():
    print("=" * 60)
    print("  Sample Test — Backend Rice Classification API")
    print(f"  Python {sys.version.split()[0]} | {sys.platform}")
    print("=" * 60)

    gagal = []
    for mod, pkg in REQUIRED:
        try:
            m = importlib.import_module(mod)
            v = getattr(m, "__version__", "(?)")
            print(f"  [v] {pkg:<22} {v}")
        except ImportError as e:
            print(f"  [X] {pkg:<22} GAGAL — {e}")
            gagal.append(pkg)

    # Test services bisa diimport
    print()
    print("[Cek services module...]")
    try:
        from services import stitching, classification
        print("  [v] services.stitching loaded")
        print("  [v] services.classification loaded")
    except Exception as e:
        print(f"  [X] Tidak bisa load services: {e}")
        gagal.append("services")

    print()
    if not gagal:
        print("  [v] SEMUA SIAP. Backend dapat dijalankan dengan start_api.bat")
        return 0
    else:
        print(f"  [X] {len(gagal)} pustaka GAGAL: {', '.join(gagal)}")
        print("  Solusi: pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
