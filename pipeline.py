"""
pipeline.py
===========
CLI wrapper untuk menjalankan seluruh pipeline dari command line.

Penggunaan:
    # Pipeline lengkap (stitching + klasifikasi):
    python pipeline.py full --images data/drone_images --output output

    # Hanya klasifikasi (orthophoto sudah ada):
    python pipeline.py classify --ortho output/orthophoto.tif --output output

    # Cek status NodeODM:
    python pipeline.py check-nodeodm

    # Output JSON ke stdout (untuk dikonsumsi subprocess):
    python pipeline.py full --images data/drone_images --output output --json-only

Output JSON:
    {
        "success": true,
        "verdict": "SIAP PANEN" | "BELUM SIAP PANEN",
        "stats": { ... },
        "files": {
            "orthophoto": "path/to/file.tif",
            "classification": "path/to/file.tif",
            "visualization": "path/to/file.png",
            "result_json": "path/to/result.json"
        },
        "duration_seconds": 123.4
    }

Exit code:
    0 = sukses
    1 = error
"""
from __future__ import annotations
import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime

from services import stitching, classification


# ============================================================================
# Helper: cetak JSON ke stdout dengan format konsisten
# ============================================================================
def output_result(result: dict, json_only: bool = False):
    """Cetak hasil. Jika json_only=True, hanya JSON yang dicetak (untuk subprocess)."""
    if json_only:
        # Pakai sys.stdout.write agar tidak ada \n di akhir yang ganggu parser
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=None))
        sys.stdout.flush()
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def output_error(message: str, json_only: bool = False, exit_code: int = 1):
    """Cetak error dalam format JSON & exit."""
    result = {
        "success": False,
        "error": message,
    }
    output_result(result, json_only)
    sys.exit(exit_code)


# ============================================================================
# Command: check-nodeodm
# ============================================================================
def cmd_check_nodeodm(args):
    try:
        info = stitching.cek_nodeodm(args.host, args.port, args.token)
        result = {"success": True, "nodeodm": info}
        output_result(result, args.json_only)
        return 0
    except stitching.StitchingError as e:
        output_error(str(e), args.json_only)


# ============================================================================
# Command: classify (orthophoto sudah ada)
# ============================================================================
def cmd_classify(args):
    t_start = time.time()
    ortho_path = Path(args.ortho)
    output_dir = Path(args.output)

    if not ortho_path.exists():
        output_error(f"Orthophoto tidak ditemukan: {ortho_path}", args.json_only)

    try:
        # Step 1: Load
        if not args.json_only:
            print(f"[1/5] Memuat orthophoto: {ortho_path.name}", file=sys.stderr)
        ortho_data = classification.load_orthophoto(ortho_path)

        # Step 2: Pra-pemrosesan
        if not args.json_only:
            print("[2/5] Pra-pemrosesan (Gaussian + CLAHE → HSV)", file=sys.stderr)
        img_hsv = classification.preprocess(ortho_data["rgb"])

        # Step 3: Segmentasi
        if not args.json_only:
            print("[3/5] Segmentasi HSV 2 kelas", file=sys.stderr)
        masks = classification.segment(img_hsv, ortho_data["mask_valid"])

        # Step 4: Verdict
        if not args.json_only:
            print(f"[4/5] Klasifikasi (threshold={args.threshold})", file=sys.stderr)
        stats = classification.classify_verdict(
            masks["mask_yellow"], masks["mask_green"],
            ortho_data["mask_valid"], threshold=args.threshold,
        )

        # Step 5: Ekspor file
        if not args.json_only:
            print("[5/5] Ekspor GeoTIFF & PNG", file=sys.stderr)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = ortho_path.stem

        class_tif = output_dir / "classification" / f"{stem}_class_{timestamp}.tif"
        classification.export_classification_geotiff(
            masks["mask_yellow"], masks["mask_green"],
            ortho_data["crs"], ortho_data["transform"],
            class_tif,
            verdict_text=stats["verdict"],
            yellow_pct=stats["yellow_pct_of_rice"],
        )

        png_path = output_dir / "visualization" / f"{stem}_map_{timestamp}.png"
        classification.export_visualization_png(
            ortho_data["rgb"], masks["mask_yellow"], masks["mask_green"],
            stats, png_path,
        )

        # Result JSON
        result_json = output_dir / "results" / f"{stem}_result_{timestamp}.json"
        result_json.parent.mkdir(parents=True, exist_ok=True)
        full_result = {
            "timestamp":         timestamp,
            "orthophoto_file":   str(ortho_path),
            "orthophoto_width":  ortho_data["width"],
            "orthophoto_height": ortho_data["height"],
            "crs":               str(ortho_data["crs"]),
            "bounds":            list(ortho_data["bounds"]),
            **stats,
        }
        with open(result_json, "w", encoding="utf-8") as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)

        # Final output
        duration = time.time() - t_start
        result = {
            "success": True,
            "verdict": stats["verdict"],
            "stats": stats,
            "metadata": {
                "orthophoto_width":  ortho_data["width"],
                "orthophoto_height": ortho_data["height"],
                "crs":               str(ortho_data["crs"]),
                "bounds":            list(ortho_data["bounds"]),
            },
            "files": {
                "orthophoto":     str(ortho_path),
                "classification": str(class_tif),
                "visualization":  str(png_path),
                "result_json":    str(result_json),
            },
            "duration_seconds": round(duration, 2),
        }
        output_result(result, args.json_only)
        return 0

    except classification.ClassificationError as e:
        output_error(f"Klasifikasi gagal: {e}", args.json_only)
    except Exception as e:
        if not args.json_only:
            traceback.print_exc(file=sys.stderr)
        output_error(f"Error tak terduga: {e}", args.json_only)


# ============================================================================
# Command: full (stitching + klasifikasi)
# ============================================================================
def cmd_full(args):
    t_start = time.time()
    images_dir = Path(args.images)
    output_dir = Path(args.output)

    if not images_dir.exists():
        output_error(f"Folder foto tidak ditemukan: {images_dir}", args.json_only)

    # Scan foto
    ext_valid = {".jpg", ".jpeg", ".JPG", ".JPEG"}
    image_paths = sorted(p for p in images_dir.iterdir()
                         if p.suffix in ext_valid and p.is_file())

    if len(image_paths) < 4:
        output_error(
            f"Hanya {len(image_paths)} foto ditemukan. Minimum 4 untuk stitching.",
            args.json_only
        )

    if not args.json_only:
        print(f"Ditemukan {len(image_paths)} foto drone", file=sys.stderr)

    try:
        # STITCHING
        def on_progress(pct, status):
            if not args.json_only:
                print(f"  [ODM {pct:3d}%] {status}", file=sys.stderr)

        if not args.json_only:
            print("[STITCHING] Submit ke NodeODM...", file=sys.stderr)

        ortho_path = stitching.stitch(
            image_paths=image_paths,
            output_dir=output_dir / "orthophoto",
            task_name="rice_paddy",
            host=args.host,
            port=args.port,
            token=args.token,
            progress_callback=on_progress,
        )

        if not args.json_only:
            print(f"[STITCHING] Selesai: {ortho_path}", file=sys.stderr)

        # KLASIFIKASI: panggil ulang dengan ortho_path
        args.ortho = str(ortho_path)
        return cmd_classify(args)

    except stitching.StitchingError as e:
        output_error(f"Stitching gagal: {e}", args.json_only)
    except Exception as e:
        if not args.json_only:
            traceback.print_exc(file=sys.stderr)
        output_error(f"Error tak terduga: {e}", args.json_only)


# ============================================================================
# Main: argparse
# ============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Pipeline deteksi kesiapan panen padi (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  Cek NodeODM:
      python pipeline.py check-nodeodm

  Pipeline lengkap dari foto drone:
      python pipeline.py full --images data/drone_images --output output

  Hanya klasifikasi (orthophoto sudah ada):
      python pipeline.py classify --ortho output/orthophoto.tif --output output

  Dengan threshold custom (default 0.60 = 60%):
      python pipeline.py classify --ortho ortho.tif --output out --threshold 0.55

  Output JSON only (untuk subprocess):
      python pipeline.py full --images data --output out --json-only
        """,
    )
    parser.add_argument("--json-only", action="store_true",
                        help="Hanya cetak JSON ke stdout (untuk subprocess)")
    parser.add_argument("--host", default="localhost", help="NodeODM host")
    parser.add_argument("--port", type=int, default=3000, help="NodeODM port")
    parser.add_argument("--token", default="", help="NodeODM token (kosong default)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check-nodeodm
    sp1 = subparsers.add_parser("check-nodeodm", help="Cek status NodeODM")
    sp1.add_argument("--json-only", action="store_true",
                     help="Hanya cetak JSON ke stdout")
    sp1.set_defaults(func=cmd_check_nodeodm)

    # classify
    sp2 = subparsers.add_parser("classify",
                                help="Klasifikasi orthophoto yang sudah ada")
    sp2.add_argument("--ortho", required=True, help="Path ke orthophoto.tif")
    sp2.add_argument("--output", default="output", help="Folder output")
    sp2.add_argument("--threshold", type=float, default=0.60,
                     help="Threshold siap panen (0.0-1.0, default 0.60)")
    sp2.add_argument("--json-only", action="store_true",
                     help="Hanya cetak JSON ke stdout")
    sp2.set_defaults(func=cmd_classify)

    # full pipeline
    sp3 = subparsers.add_parser("full",
                                help="Pipeline lengkap: stitching + klasifikasi")
    sp3.add_argument("--images", required=True, help="Folder berisi foto drone")
    sp3.add_argument("--output", default="output", help="Folder output")
    sp3.add_argument("--threshold", type=float, default=0.60,
                     help="Threshold siap panen (default 0.60)")
    sp3.add_argument("--json-only", action="store_true",
                     help="Hanya cetak JSON ke stdout")
    sp3.set_defaults(func=cmd_full)

    args = parser.parse_args()
    # Merge flag dari parent parser dan subparser
    if hasattr(args, "json_only"):
        pass  # sudah di-set oleh argparse
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
