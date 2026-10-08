"""
services/classification.py
==========================
Modul klasifikasi orthophoto via segmentasi HSV 2 kelas.

Refactor dari notebook rice_orthophoto_pipeline.ipynb sel 7-13,
dengan beberapa improvement:
  - Fungsi murni (deterministic, no side-effect)
  - Type hints lengkap
  - Mudah di-test unit
  - Bisa dipanggil dari CLI maupun FastAPI
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from datetime import datetime

import numpy as np
import cv2
import rasterio
from rasterio.plot import reshape_as_image


# ============================================================================
# DEFAULT KONFIGURASI HSV
# ============================================================================
DEFAULT_HSV_CONFIG = {
    # Skala OpenCV: H 0-179, S 0-255, V 0-255
    # hsv_upper_yellow[0]=34 dan hsv_lower_green[0]=35 sengaja dibuat saling
    # lepas (tidak beririsan) di sumbu Hue, supaya cv2.inRange() tidak pernah
    # menandai piksel yang sama sebagai kuning DAN hijau sekaligus.
    "hsv_lower_yellow": [20, 60, 60],
    "hsv_upper_yellow": [34, 255, 255],
    "hsv_lower_green":  [35, 40, 40],
    "hsv_upper_green":  [85, 255, 255],

    # Parameter pra-pemrosesan
    "gaussian_kernel":  5,
    "clahe_clip_limit": 2.0,
    "clahe_tile_size":  8,
    "morph_kernel":     5,
}


class ClassificationError(Exception):
    """Raised ketika klasifikasi gagal."""
    pass


# ============================================================================
# STEP 1: LOAD ORTHOPHOTO
# ============================================================================
def load_orthophoto(ortho_path: Path) -> dict:
    """
    Muat orthophoto GeoTIFF + ekstrak metadata + deteksi mask valid (NoData).

    Returns:
        dict berisi: rgb (ndarray h×w×3), mask_valid (ndarray h×w bool),
        width, height, crs, transform, bounds
    """
    ortho_path = Path(ortho_path)
    if not ortho_path.exists():
        raise ClassificationError(f"Orthophoto tidak ditemukan: {ortho_path}")

    with rasterio.open(ortho_path) as src:
        arr = src.read()
        img_full = reshape_as_image(arr)
        w, h = src.width, src.height
        n_bands = src.count

        # Deteksi mask valid dari alpha channel atau piksel non-hitam
        if n_bands == 4:
            mask_valid = img_full[:, :, 3] > 0
            img_rgb = img_full[:, :, :3]
        elif n_bands >= 3:
            img_rgb = img_full[:, :, :3]
            mask_valid = np.any(img_rgb > 0, axis=2)
        else:
            raise ClassificationError(
                f"Orthophoto hanya punya {n_bands} band, butuh minimal 3 (RGB)."
            )

        return {
            "rgb": img_rgb.astype(np.uint8),
            "mask_valid": mask_valid,
            "width": w,
            "height": h,
            "n_bands": n_bands,
            "crs": src.crs,
            "transform": src.transform,
            "bounds": tuple(src.bounds),
        }


# ============================================================================
# STEP 2: PRA-PEMROSESAN
# ============================================================================
def preprocess(img_rgb: np.ndarray, hsv_config: Optional[dict] = None) -> np.ndarray:
    """
    Gaussian Blur → CLAHE pada V → konversi ke HSV.

    Args:
        img_rgb: ndarray (h, w, 3) RGB uint8
        hsv_config: dict opsi pra-pemrosesan (lihat DEFAULT_HSV_CONFIG)

    Returns:
        ndarray (h, w, 3) HSV uint8 siap untuk segmentasi
    """
    config = {**DEFAULT_HSV_CONFIG, **(hsv_config or {})}

    # OpenCV pakai BGR
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    # Gaussian blur
    k = config["gaussian_kernel"]
    if k % 2 == 0:
        k += 1
    img_blur = cv2.GaussianBlur(img_bgr, (k, k), sigmaX=0)

    # Konversi ke HSV, CLAHE pada V
    img_hsv_pre = cv2.cvtColor(img_blur, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(img_hsv_pre)
    clahe = cv2.createCLAHE(
        clipLimit=config["clahe_clip_limit"],
        tileGridSize=(config["clahe_tile_size"], config["clahe_tile_size"]),
    )
    v_clahe = clahe.apply(v_ch)
    return cv2.merge([h_ch, s_ch, v_clahe])


# ============================================================================
# STEP 3: SEGMENTASI
# ============================================================================
def segment(
    img_hsv: np.ndarray,
    mask_valid: np.ndarray,
    hsv_config: Optional[dict] = None,
) -> dict:
    """
    Segmentasi HSV 2 kelas: kuning (matang) & hijau (belum matang).
    NoData piksel di-exclude dari kedua mask.

    Returns:
        dict berisi: mask_yellow, mask_green (ndarray uint8 dengan nilai 0/255)
    """
    config = {**DEFAULT_HSV_CONFIG, **(hsv_config or {})}

    lower_y = np.array(config["hsv_lower_yellow"], dtype=np.uint8)
    upper_y = np.array(config["hsv_upper_yellow"], dtype=np.uint8)
    lower_g = np.array(config["hsv_lower_green"], dtype=np.uint8)
    upper_g = np.array(config["hsv_upper_green"], dtype=np.uint8)

    mask_y_raw = cv2.inRange(img_hsv, lower_y, upper_y)
    mask_g_raw = cv2.inRange(img_hsv, lower_g, upper_g)

    # Exclude NoData
    mask_valid_u8 = (mask_valid.astype(np.uint8) * 255)
    mask_y_raw = cv2.bitwise_and(mask_y_raw, mask_valid_u8)
    mask_g_raw = cv2.bitwise_and(mask_g_raw, mask_valid_u8)

    # Operasi morfologi: Opening → Closing
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (config["morph_kernel"], config["morph_kernel"]),
    )
    mask_y = cv2.morphologyEx(mask_y_raw, cv2.MORPH_OPEN, kernel)
    mask_y = cv2.morphologyEx(mask_y, cv2.MORPH_CLOSE, kernel)
    mask_g = cv2.morphologyEx(mask_g_raw, cv2.MORPH_OPEN, kernel)
    mask_g = cv2.morphologyEx(mask_g, cv2.MORPH_CLOSE, kernel)

    # Pastikan hasil morfologi tidak merembes keluar area valid
    mask_y = cv2.bitwise_and(mask_y, mask_valid_u8)
    mask_g = cv2.bitwise_and(mask_g, mask_valid_u8)

    # Resolusi irisan pasca-morfologi: rentang Hue kuning & hijau sudah saling
    # lepas sehingga cv2.inRange() dijamin tidak beririsan, tapi operasi
    # Closing bersifat melebarkan (dilasi) sehingga tepi mask kuning dapat
    # melebar ke wilayah mask hijau dan sebaliknya. Piksel yang diperebutkan
    # diselesaikan berdasarkan nilai Hue aslinya (bukan urutan operasi), agar
    # setiap piksel padi terklasifikasi ke dalam tepat satu kelas.
    overlap = cv2.bitwise_and(mask_y, mask_g)
    n_overlap = int(np.sum(overlap > 0))

    if n_overlap > 0:
        hue = img_hsv[:, :, 0]
        belongs_yellow = (overlap > 0) & (hue <= config["hsv_upper_yellow"][0])
        belongs_green = (overlap > 0) & (hue > config["hsv_upper_yellow"][0])
        mask_g[belongs_yellow] = 0
        mask_y[belongs_green] = 0

    if int(np.sum(cv2.bitwise_and(mask_y, mask_g) > 0)) != 0:
        raise ClassificationError(
            "Resolusi irisan mask gagal. Periksa hsv_upper_yellow dan "
            "hsv_lower_green agar tidak tumpang tindih."
        )

    return {"mask_yellow": mask_y, "mask_green": mask_g, "n_overlap_resolved": n_overlap}


# ============================================================================
# STEP 4: VERDICT WHOLE-IMAGE
# ============================================================================
def classify_verdict(
    mask_yellow: np.ndarray,
    mask_green: np.ndarray,
    mask_valid: np.ndarray,
    threshold: float = 0.60,
) -> dict:
    """
    Hitung statistik & tentukan verdict whole-orthophoto.

    Args:
        mask_yellow, mask_green: hasil dari segment()
        mask_valid: mask area valid orthophoto
        threshold: ambang siap panen (0.0 - 1.0), default 0.60 = 60%

    Returns:
        dict statistik & verdict
    """
    if not 0 < threshold < 1:
        raise ClassificationError(
            f"Threshold harus antara 0 dan 1, dapat: {threshold}"
        )

    n_total = int(mask_valid.size)
    n_valid = int(mask_valid.sum())
    n_yellow = int(np.sum(mask_yellow > 0))
    n_green = int(np.sum(mask_green > 0))
    n_rice = n_yellow + n_green

    if n_rice == 0:
        raise ClassificationError(
            "Tidak ada piksel padi terdeteksi. Threshold HSV mungkin tidak cocok."
        )

    yellow_pct = n_yellow / n_rice * 100
    green_pct = n_green / n_rice * 100
    threshold_pct = threshold * 100

    if yellow_pct / 100 >= threshold:
        verdict = "SIAP PANEN"
        verdict_class = 1
    else:
        verdict = "BELUM SIAP PANEN"
        verdict_class = 2

    margin_pp = yellow_pct - threshold_pct

    return {
        "n_pixels_total":       n_total,
        "n_pixels_valid":       n_valid,
        "n_pixels_rice":        n_rice,
        "n_pixels_yellow":      n_yellow,
        "n_pixels_green":       n_green,
        "yellow_pct_of_rice":   round(yellow_pct, 2),
        "green_pct_of_rice":    round(green_pct, 2),
        "valid_pct_of_total":   round(n_valid / n_total * 100, 2),
        "rice_pct_of_valid":    round(n_rice / n_valid * 100, 2) if n_valid > 0 else 0,
        "threshold_used":       threshold,
        "verdict":              verdict,
        "verdict_class":        verdict_class,
        "confidence_margin_pp": round(margin_pp, 2),
    }


# ============================================================================
# STEP 5: EKSPOR GEOTIFF KLASIFIKASI
# ============================================================================
def export_classification_geotiff(
    mask_yellow: np.ndarray,
    mask_green: np.ndarray,
    crs,
    transform,
    output_path: Path,
    verdict_text: str = "",
    yellow_pct: float = 0.0,
) -> Path:
    """
    Tulis raster klasifikasi sebagai GeoTIFF.
    Nilai: 0=NoData/bukan padi, 1=kuning, 2=hijau.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    h, w = mask_yellow.shape
    class_raster = np.zeros((h, w), dtype=np.uint8)
    class_raster[mask_yellow > 0] = 1
    class_raster[mask_green > 0] = 2

    with rasterio.open(
        output_path, "w",
        driver="GTiff",
        height=h, width=w, count=1,
        dtype=class_raster.dtype,
        crs=crs, transform=transform,
        compress="lzw", nodata=0,
    ) as dst:
        dst.write(class_raster, 1)
        dst.update_tags(
            1,
            DESCRIPTION="Klasifikasi kematangan padi 2 kelas",
            VALUE_0="NoData / Bukan Padi",
            VALUE_1="Padi Matang (Kuning)",
            VALUE_2="Padi Belum Matang (Hijau)",
            VERDICT_GLOBAL=verdict_text,
            YELLOW_PCT=f"{yellow_pct:.2f}%",
        )

    return output_path


# ============================================================================
# STEP 5b: EKSPOR ORTHOPHOTO → PNG RGBA (untuk web overlay Leaflet)
# ============================================================================
def export_orthophoto_web_png(
    ortho_path: Path,
    output_path: Path,
    max_size: int = 4000,
) -> tuple:
    """
    Konversi orthophoto GeoTIFF ke PNG RGBA untuk Leaflet ImageOverlay.

    Area NoData dibuat transparan agar basemap OSM tetap kelihatan di
    luar polygon sawah (sama seperti tampilan QGIS).

    Returns:
        (output_path, bounds_wgs84) di mana bounds_wgs84 = [minLon, minLat, maxLon, maxLat]
    """
    from rasterio.warp import transform_bounds
    from rasterio.crs import CRS

    ortho_path = Path(ortho_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(ortho_path) as src:
        arr = src.read()          # shape: (bands, h, w), dtype uint8 atau uint16
        n_bands = src.count

        # Pastikan uint8
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)

        r, g, b = arr[0], arr[1], arr[2]

        # Alpha channel: dari band ke-4 kalau ada, atau deteksi piksel hitam
        if n_bands >= 4:
            a = arr[3]
        else:
            # Piksel (0,0,0) dianggap NoData — buat transparan
            a = np.where((r == 0) & (g == 0) & (b == 0), 0, 255).astype(np.uint8)

        # OpenCV pakai urutan BGRA (bukan RGBA)
        bgra = np.stack([b, g, r, a], axis=-1)   # (h, w, 4)

        h, w = bgra.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            # RGB: INTER_AREA lebih halus untuk downscale
            bgr_down = cv2.resize(bgra[:, :, :3], (new_w, new_h), interpolation=cv2.INTER_AREA)
            # Alpha: INTER_NEAREST agar tepi polygon tidak blur
            a_down   = cv2.resize(bgra[:, :, 3],  (new_w, new_h), interpolation=cv2.INTER_NEAREST)
            bgra = np.dstack([bgr_down, a_down])

        # Hitung bounds dalam WGS84 (Leaflet butuh lat/lon)
        wgs84 = CRS.from_epsg(4326)
        if src.crs.to_epsg() == 4326:
            b_ = src.bounds
            bounds_wgs84 = [b_.left, b_.bottom, b_.right, b_.top]
        else:
            left, bottom, right, top = transform_bounds(src.crs, wgs84, *src.bounds)
            bounds_wgs84 = [left, bottom, right, top]

    cv2.imwrite(str(output_path), bgra)
    return output_path, bounds_wgs84


# ============================================================================
# STEP 5c: EKSPOR KLASIFIKASI → PNG RGBA OVERLAY (untuk web overlay Leaflet)
# ============================================================================
def export_classification_overlay_png(
    mask_yellow: np.ndarray,
    mask_green: np.ndarray,
    output_path: Path,
    max_size: int = 4000,
) -> Path:
    """
    Export overlay klasifikasi sebagai PNG RGBA transparan.

    Nilai piksel:
        0 (bukan padi) → (0,0,0,0)       transparan total
        1 (kuning/matang) → (255,235,59,200)  kuning semi-transparan
        2 (hijau/belum) → (76,175,80,200)     hijau semi-transparan

    Downsample dengan INTER_NEAREST agar batas kelas tidak berbaur.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    h, w = mask_yellow.shape

    # Buat array BGRA (OpenCV) — default semua nol (transparan)
    bgra = np.zeros((h, w, 4), dtype=np.uint8)
    # Kuning: RGB(255,235,59) → BGR(59,235,255), alpha=200
    bgra[mask_yellow > 0] = [59, 235, 255, 200]
    # Hijau: RGB(76,175,80) → BGR(80,175,76), alpha=200
    bgra[mask_green  > 0] = [80, 175,  76, 200]

    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        bgra = cv2.resize(bgra, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    cv2.imwrite(str(output_path), bgra)
    return output_path


# ============================================================================
# STEP 6: EKSPOR PNG VISUALISASI
# ============================================================================
def export_visualization_png(
    img_rgb: np.ndarray,
    mask_yellow: np.ndarray,
    mask_green: np.ndarray,
    stats: dict,
    output_path: Path,
    max_size: int = 2000,
) -> Path:
    """
    Tulis PNG visualisasi (orthophoto + overlay + verdict banner + info box).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    h_orig, w_orig = img_rgb.shape[:2]

    # Downsample untuk visualisasi (orthophoto besar bisa MEMORY OUT)
    if max(h_orig, w_orig) > max_size:
        scale = max_size / max(h_orig, w_orig)
        new_w = int(w_orig * scale)
        new_h = int(h_orig * scale)
        img_disp = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
        my_disp = cv2.resize(mask_yellow, (new_w, new_h),
                             interpolation=cv2.INTER_NEAREST)
        mg_disp = cv2.resize(mask_green, (new_w, new_h),
                             interpolation=cv2.INTER_NEAREST)
    else:
        img_disp = img_rgb
        my_disp = mask_yellow
        mg_disp = mask_green

    fig, ax = plt.subplots(figsize=(15, 11), dpi=200)
    ax.imshow(img_disp)

    overlay = np.zeros((*img_disp.shape[:2], 4), dtype=np.uint8)
    overlay[my_disp > 0] = [255, 235, 59, 130]
    overlay[mg_disp > 0] = [76, 175, 80, 130]
    ax.imshow(overlay)

    verdict = stats["verdict"]
    icon = "+" if verdict == "SIAP PANEN" else "x"
    banner_color = "#2d6a4f" if verdict == "SIAP PANEN" else "#c1121f"
    ax.text(0.02, 0.97, f"  [{icon}]  {verdict}  ",
            transform=ax.transAxes,
            fontsize=18, fontweight="bold", color="white",
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.6",
                      facecolor=banner_color, edgecolor="black", linewidth=1.5))

    info_text = (
        f"Persentase kuning : {stats['yellow_pct_of_rice']:.1f}%\n"
        f"Persentase hijau  : {stats['green_pct_of_rice']:.1f}%\n"
        f"Ambang siap panen : {stats['threshold_used']*100:.0f}%\n"
        f"Margin            : {stats['confidence_margin_pp']:+.1f} pp\n"
        f"Diproses          : {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    ax.text(0.98, 0.03, info_text,
            transform=ax.transAxes,
            fontsize=10, family="monospace", color="black",
            verticalalignment="bottom", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.5",
                      facecolor="white", alpha=0.92, edgecolor="gray"))

    legend_patches = [
        Patch(facecolor=(1.0, 0.92, 0.23, 0.5), edgecolor="black",
              label="Padi MATANG (kuning)"),
        Patch(facecolor=(0.30, 0.69, 0.31, 0.5), edgecolor="black",
              label="Padi BELUM matang (hijau)"),
    ]
    ax.legend(handles=legend_patches, loc="lower left",
              framealpha=0.92, fontsize=10)
    ax.set_title("Peta Kesiapan Panen Padi",
                 fontsize=13, fontweight="bold", pad=10)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return output_path
