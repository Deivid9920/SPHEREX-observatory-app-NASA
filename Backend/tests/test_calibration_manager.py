from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from app.services.calibration_manager import CalibrationManager
from app.services.fits_inventory import FitsInventory


MEF_NAME = "level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits"


def _write_mef(path: Path, release: str | None = None) -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [4, 4]
    wcs.wcs.crval = [120.0, 10.0]
    wcs.wcs.cdelt = [-0.001, 0.001]
    wcs.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    image_header = wcs.to_header(relax=True)
    image_header["DETECTOR"] = 1
    image_header["BUNIT"] = "MJy/sr"
    image_header["DATE-OBS"] = "2025-07-07T00:07:23.351"
    image_header["A_ORDER"] = 2
    image_header["B_ORDER"] = 2
    image_header["A_2_0"] = 1e-8
    image_header["B_0_2"] = -1e-8
    image = fits.ImageHDU(np.ones((8, 8), dtype=np.float32), header=image_header, name="IMAGE")
    variance = fits.ImageHDU(np.ones((8, 8), dtype=np.float32), name="VARIANCE")
    variance.header["BUNIT"] = "MJy2/sr2"
    flags = fits.ImageHDU(np.zeros((8, 8), dtype=np.int16), name="FLAGS")
    zone_index = np.arange(441, dtype=np.int32)
    epsf = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="BINX", format="J", array=zone_index % 21),
            fits.Column(name="BINY", format="J", array=zone_index // 21),
            fits.Column(name="XCENTER", format="E", unit="pixel", array=(zone_index % 21) * (7.0 / 20.0)),
            fits.Column(name="YCENTER", format="E", unit="pixel", array=(zone_index // 21) * (7.0 / 20.0)),
            fits.Column(name="CWAVE", format="E", unit="um", array=np.full(441, 1.2, dtype=np.float32)),
            fits.Column(name="CBAND", format="E", unit="um", array=np.full(441, 0.03, dtype=np.float32)),
            fits.Column(
                name="EPSF",
                format="1089D",
                dim="(33,33)",
                array=np.full((441, 1089), 1.0 / 1089.0, dtype=np.float64),
            ),
        ],
        name="EPSF",
    )
    epsf.header["DETECTOR"] = 1
    wave_table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="X", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
            fits.Column(name="Y", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
            fits.Column(
                name="VALUES",
                format="8E",
                dim="(2,2,2)",
                array=np.array(
                    [[
                        [[1.2, 0.03], [1.2, 0.03]],
                        [[1.2, 0.03], [1.2, 0.03]],
                    ]],
                    dtype=np.float32,
                ),
            ),
        ],
        name="WCS-WAVE",
    )
    wave_table.header["DETECTOR"] = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    primary = fits.PrimaryHDU()
    if release:
        primary.header["RELEASE"] = release
    fits.HDUList([
        primary,
        image,
        flags,
        variance,
        epsf,
        wave_table,
    ]).writeto(path, checksum=True)


def _build_inventory(
    root: Path,
    release: str | None = None,
) -> tuple[FitsInventory, dict, Path]:
    path = root / "science" / MEF_NAME
    _write_mef(path, release)
    inventory = FitsInventory(
        str(root),
        str(root.parent / "manifest.json"),
        str(root.parent / "consumers.json"),
    )
    entry = inventory.build()["files"][0]
    return inventory, entry, path


def _write_spectral_wcs(
    root: Path,
    detector: int = 1,
    header_detector: int | None = None,
    release_directory: str | None = None,
) -> Path:
    header_detector = detector if header_detector is None else header_detector
    path = root
    if release_directory:
        path = path / release_directory
    path = path / "calibration" / f"spectral_wcs_D{detector}_spx_cal-swcs-v5-2026-191.fits"
    cwave = fits.ImageHDU(np.full((8, 8), 1.2, dtype=np.float32), name="CWAVE")
    cwave.header["BUNIT"] = "um"
    cwave.header["DETECTOR"] = header_detector
    cband = fits.ImageHDU(np.full((8, 8), 0.03, dtype=np.float32), name="CBAND")
    cband.header["BUNIT"] = "um"
    cband.header["DETECTOR"] = header_detector
    wave_table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="X", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
            fits.Column(name="Y", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
            fits.Column(
                name="VALUES",
                format="8E",
                dim="(2,2,2)",
                array=np.array(
                    [[
                        [[1.2, 0.03], [1.2, 0.03]],
                        [[1.2, 0.03], [1.2, 0.03]],
                    ]],
                    dtype=np.float32,
                ),
            ),
        ],
        name="WCS-WAVE",
    )
    wave_table.header["DETECTOR"] = header_detector
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([fits.PrimaryHDU(), cwave, cband, wave_table]).writeto(path, checksum=True)
    return path


def test_missing_spectral_wcs_is_blocked_without_reusing_epsf_values(tmp_path: Path) -> None:
    inventory, entry, path = _build_inventory(tmp_path / "raw")

    diagnosis = CalibrationManager(inventory).assess(entry, path)

    assert diagnosis["calibrations"]["spectral_wcs"]["status"] == "missing"
    assert diagnosis["calibrations"]["epsf"]["status"] == "partially_verified"
    assert diagnosis["operation_authorizations"]["display_image"]["authorized"] is True
    assert diagnosis["operation_authorizations"]["science_grade_mef_spectral_analysis"]["authorized"] is False
    assert diagnosis["operation_authorizations"]["photometry"]["authorized"] is False
    assert diagnosis["photometric"]["corrections_applied"] == []
    epsf = next(item for item in diagnosis["embedded_components"] if item["name"] == "EPSF")
    assert epsf["note"].startswith("CWAVE/CBAND here are values per ePSF zone")
    assert epsf["zone_count"] == 441
    assert epsf["epsf_dimensions"] == [33, 33]
    assert epsf["zone_bin_grid_valid"] is True
    assert epsf["zone_centers_within_image"] is True
    assert epsf["calibration_status"] == "partially_verified"


def test_spectral_wcs_requires_exact_identity_and_structural_compatibility(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    inventory, entry, path = _build_inventory(root, release="DR1")
    calibration_path = _write_spectral_wcs(root, release_directory="dr1")

    diagnosis = CalibrationManager(inventory).assess(entry, path)

    assert diagnosis["calibrations"]["spectral_wcs"]["status"] == "verified"
    assert diagnosis["calibrations"]["spectral_wcs"]["calibration_ids"]
    candidate = diagnosis["calibrations"]["spectral_wcs"]["calibration_ids"][0]
    assert candidate.startswith("cal-")
    assert calibration_path.is_file()
    assert diagnosis["operation_authorizations"]["science_grade_mef_spectral_analysis"]["authorized"] is True


def test_ambiguous_spectral_wcs_matches_are_not_selected(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    inventory, entry, path = _build_inventory(root)
    original = _write_spectral_wcs(root)
    duplicate = root / "second-copy" / original.name
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(original.read_bytes())

    diagnosis = CalibrationManager(inventory).assess(entry, path)

    assert diagnosis["calibrations"]["spectral_wcs"]["status"] == "unverified"
    assert diagnosis["calibrations"]["spectral_wcs"]["calibration_ids"] == []
    assert "ambiguous" in diagnosis["calibrations"]["spectral_wcs"]["reason"]


def test_spectral_wcs_with_wrong_detector_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    inventory, entry, path = _build_inventory(root)
    _write_spectral_wcs(root, header_detector=2)

    diagnosis = CalibrationManager(inventory).assess(entry, path)

    assert diagnosis["calibrations"]["spectral_wcs"]["status"] == "incompatible"
    assert diagnosis["calibrations"]["spectral_wcs"]["calibration_ids"] == []


def test_registry_exposes_embedded_products_and_documented_types(tmp_path: Path) -> None:
    inventory, _, _ = _build_inventory(tmp_path / "raw")

    catalog = CalibrationManager(inventory).catalog()

    types = {item["type"] for item in catalog["registered_types"]}
    assert {"spectral_wcs", "absolute_gain_matrix", "epsf", "solid_angle_pixel_map"} <= types
    assert {item["name"] for item in catalog["local_embedded_components"]} == {"EPSF", "WCS-WAVE"}
    assert catalog["standalone_calibration_products"] == []
