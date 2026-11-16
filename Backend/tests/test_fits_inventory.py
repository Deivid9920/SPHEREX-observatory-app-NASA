import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from app.core.config import BASE_DIR, Settings
from app.services.astrometry import CoordinateOutsideImageError
from app.services.fits_inventory import FitsInventory, InventoryStaleError, inspect_fits
from app.services.fits_processor import FITSProcessor


def write_mef(
    path: Path,
    *,
    release: str = "QR3",
    image_release: str | None = None,
    band: str = "B1",
    crval_ra: float = 120.0,
    date_obs: str = "2024-01-01T00:00:00",
    image_value: float = 10.0,
    include_spectral_wcs: bool = False,
) -> None:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [4, 4]
    wcs.wcs.crval = [crval_ra, 10.0]
    wcs.wcs.cdelt = [-0.001, 0.001]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]

    image_header = wcs.to_header()
    image_header["DATE-OBS"] = date_obs
    image_header["RELEASE"] = image_release or release
    image_header["BAND"] = band
    image_header["BUNIT"] = "MJy/sr"
    image_header["PSF_FWHM"] = 2.0
    image_header["CALLEVEL"] = "2"
    image_header["CAL_VER"] = "1.0"
    if include_spectral_wcs:
        spectral_wcs = WCS(naxis=2)
        spectral_wcs.wcs.ctype = ["WAVE", "LINEAR"]
        spectral_wcs.wcs.cunit = ["um", "pix"]
        spectral_wcs.wcs.crpix = [4, 4]
        spectral_wcs.wcs.crval = [1.2, 0.0]
        spectral_wcs.wcs.cdelt = [0.01, 1.0]
        image_header.extend(spectral_wcs.to_header(key="W"))

    primary = fits.PrimaryHDU()
    primary.header["RELEASE"] = release
    image = fits.ImageHDU(
        np.full((8, 8), image_value, dtype=np.float32),
        header=image_header,
        name="IMAGE",
    )
    variance = fits.ImageHDU(
        np.full((8, 8), 4.0, dtype=np.float32),
        name="VARIANCE",
    )
    variance.header["BUNIT"] = "MJy2/sr2"
    flags = fits.ImageHDU(np.zeros((8, 8), dtype=np.int16), name="FLAGS")
    catalog = fits.BinTableHDU.from_columns(
        [fits.Column(name="SOURCE_ID", format="J", array=np.array([1], dtype=np.int32))],
        name="CATALOG",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([primary, image, variance, flags, catalog]).writeto(path, checksum=True)


def test_settings_resolve_relative_paths_against_backend_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATA_RAW_DIR", raising=False)
    monkeypatch.delenv("DATA_PROCESSED_DIR", raising=False)
    monkeypatch.delenv("SPHEREX_RAW_DIR", raising=False)
    monkeypatch.delenv("SPHEREX_PROCESSED_DIR", raising=False)
    monkeypatch.delenv("SPHEREX_MANIFEST_PATH", raising=False)
    monkeypatch.delenv("SPHEREX_CONSUMERS_PATH", raising=False)
    monkeypatch.delenv("SPHEREX_CALIBRATION_DIR", raising=False)

    settings = Settings()

    assert Path(settings.DATA_RAW_DIR) == (BASE_DIR / "app/data/raw").resolve()
    assert Path(settings.SPHEREX_RAW_DIR) == (BASE_DIR / "app/data/raw/spherex").resolve()
    assert Path(settings.SPHEREX_MANIFEST_PATH) == (BASE_DIR / "app/data/processed/spherex/fits-manifest.json").resolve()
    assert Path(settings.SPHEREX_CALIBRATION_DIR) == (BASE_DIR / "app/data/calibration/spherex").resolve()


def test_inventory_assigns_multiple_consumers_without_copying_file(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    fits_path = root / "shared" / "observation.fits"
    write_mef(fits_path)
    consumer_path = tmp_path / "fits-consumers.json"
    consumer_path.write_text(
        json.dumps({
            "shared/observation.fits": {
                "consumers": ["sky_explorer", "temporal_vision", "object_detection"],
                "source": str(tmp_path / "source"),
            },
        }),
        encoding="utf-8",
    )
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(consumer_path),
    )

    manifest = inventory.build()

    assert manifest["file_count"] == 1
    assert manifest["files"][0]["consumers"] == [
        "object_detection",
        "sky_explorer",
        "temporal_vision",
    ]
    assert manifest["files"][0]["source"] == "[absolute path omitted]"
    assert manifest["files"][0]["compatibility"]["temporal_comparison"]["compatible"]
    assert manifest["files"][0]["has_table_data"]
    assert all(
        extension["checksum_valid"] is True
        and extension["datasum_valid"] is True
        for extension in manifest["files"][0]["extensions"]
    )
    assert str(tmp_path) not in (tmp_path / "manifest.json").read_text(encoding="utf-8")


def test_inventory_derives_consumers_only_from_validated_capabilities(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    write_mef(root / "observation.fits", date_obs="2024-01-01T00:00:00")
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )

    entry = inventory.build()["files"][0]

    assert entry["product_type"] == "spectral_image_mef"
    assert entry["consumers"] == [
        "object_detection",
        "sky_explorer",
        "temporal_vision",
    ]
    assert "discovery_catalog" not in entry["consumers"]


def test_inventory_rejects_consumer_without_a_validated_capability(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    write_mef(root / "observation.fits", date_obs="2024-01-01T00:00:00")
    consumer_path = tmp_path / "fits-consumers.json"
    consumer_path.write_text(
        json.dumps({"observation.fits": ["discovery_catalog"]}),
        encoding="utf-8",
    )
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(consumer_path),
    )

    with pytest.raises(ValueError, match="sin capacidad validada"):
        inventory.build()


def test_conflicting_release_headers_are_not_marked_temporally_compatible(tmp_path: Path) -> None:
    path = tmp_path / "conflicting.fits"
    write_mef(path, release="QR3", image_release="DR1")

    metadata = inspect_fits(path)

    assert metadata["release"] is None
    assert metadata["metadata_presence"]["release"] == "conflicting"
    assert not metadata["compatibility"]["temporal_comparison"]["compatible"]
    assert any("conflicto" in warning for warning in metadata["validation_warnings"])


def test_missing_release_label_alone_does_not_invalidate_temporal_eligibility(
    tmp_path: Path,
) -> None:
    path = tmp_path / "no-release.fits"
    write_mef(path, release="")

    metadata = inspect_fits(path)

    assert metadata["release"] is None
    assert metadata["metadata_presence"]["release"] == "absent"
    assert metadata["compatibility"]["temporal_comparison"]["compatible"]


def test_primary_and_table_hdus_do_not_trigger_false_wcs_warnings(tmp_path: Path) -> None:
    path = tmp_path / "valid_mef.fits"
    write_mef(path)
    metadata = inspect_fits(path)

    assert metadata["validation_status"] in {"valid", "valid_with_warnings"}
    assert not any("more axes" in warning.lower() for warning in metadata["validation_warnings"])
    assert metadata["compatibility"]["sky_preview"]["compatible"]


def test_bad_checksum_disables_scientific_compatibility(tmp_path: Path) -> None:
    path = tmp_path / "damaged.fits"
    write_mef(path)
    with fits.open(path, memmap=False) as hdul:
        image_data_offset = hdul["IMAGE"].fileinfo()["datLoc"]
    with path.open("r+b") as file:
        file.seek(image_data_offset)
        original_byte = file.read(1)
        file.seek(image_data_offset)
        file.write(bytes([original_byte[0] ^ 1]))

    metadata = inspect_fits(path)

    assert metadata["validation_status"] == "corrupt_or_unreadable"
    assert not metadata["compatibility"]["temporal_comparison"]["compatible"]
    assert not metadata["compatibility"]["spectral_profile"]["compatible"]


def test_temporal_pipeline_preserves_variance_for_identical_wcs(tmp_path: Path) -> None:
    first = tmp_path / "first.fits"
    second = tmp_path / "second.fits"
    write_mef(first, date_obs="2024-01-01T00:00:00")
    write_mef(second, date_obs="2024-01-02T00:00:00", image_value=12.0)

    result = FITSProcessor.align_and_cutout_pair(
        str(first),
        str(second),
        ra=120.0,
        dec=10.0,
        cutout_size_px=150,
        subtract_background=False,
    )

    assert result["image_t1"].shape == (150, 150)
    assert result["variance_t1"].shape == (150, 150)
    valid_variance = result["variance_t1"][np.isfinite(result["variance_t1"])]
    np.testing.assert_array_equal(valid_variance, np.full(64, 4.0))


def test_temporal_pipeline_rejects_different_grids_and_bands(tmp_path: Path) -> None:
    first = tmp_path / "first.fits"
    shifted = tmp_path / "shifted.fits"
    other_band = tmp_path / "other-band.fits"
    write_mef(first)
    write_mef(shifted, crval_ra=120.01)
    write_mef(other_band, band="B2", date_obs="2024-01-02T00:00:00")

    with np.testing.assert_raises_regex(ValueError, "WCS"):
        FITSProcessor.align_and_cutout_pair(
            str(first), str(shifted), 120.0, 10.0, subtract_background=False
        )
    with np.testing.assert_raises_regex(ValueError, "bandas"):
        FITSProcessor.align_and_cutout_pair(
            str(first), str(other_band), 120.0, 10.0, subtract_background=False
        )


def test_inventory_marks_duplicate_bytes_instead_of_mislabeling_them(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    original = root / "original.fits"
    duplicate = root / "copy.fits"
    write_mef(original)
    shutil.copyfile(original, duplicate)
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )

    entries = inventory.build()["files"]

    assert len(entries) == 2
    assert sum(entry["duplicate_of"] is not None for entry in entries) == 1


def test_inventory_rejects_files_changed_after_manifest_generation(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    path = root / "observation.fits"
    write_mef(path)
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )
    entry = inventory.build()["files"][0]
    with path.open("ab") as file:
        file.write(b"changed")

    with np.testing.assert_raises_regex(InventoryStaleError, "manifiesto"):
        inventory.get_path(entry)


def test_inventory_recognizes_gzip_fits_files(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    write_mef(root / "observation.fits.gz")
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )

    manifest = inventory.build()

    assert manifest["file_count"] == 1
    assert manifest["files"][0]["validation_status"] in ("valid", "valid_with_warnings")


def test_table_only_file_is_catalogued_without_scientific_image_claims(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    path = root / "sources.fits"
    path.parent.mkdir(parents=True)
    table = fits.BinTableHDU.from_columns([
        fits.Column(name="SOURCE_ID", format="J", array=np.array([1], dtype=np.int32)),
        fits.Column(name="RA", format="D", array=np.array([120.0])),
    ])
    fits.HDUList([fits.PrimaryHDU(), table]).writeto(path, checksum=True)
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )

    entry = inventory.build()["files"][0]

    assert entry["has_table_data"]
    assert not entry["compatibility"]["sky_preview"]["compatible"]
    assert not entry["compatibility"]["temporal_comparison"]["compatible"]


def test_real_fits_extracts_spectral_profile_and_rejects_outside_image_coordinates() -> None:
    real_file = (
        Path(__file__).resolve().parents[1]
        / "app/data/raw/spherex/AstroVision AI/level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits"
    )
    if not real_file.is_file():
        pytest.skip("Local SPHEREx MEF is unavailable; real-data verification is environment-specific.")

    valid = FITSProcessor.extract_spectral_profile_from_mef(
        str(real_file),
        148.19538616879197,
        -60.237471707056955,
    )
    assert valid["is_valid_measurement"] is True
    assert valid["wavelength_um"] > 0.0
    assert valid["flux_mjy_sr"] > 0.0

    with pytest.raises(CoordinateOutsideImageError):
        FITSProcessor.extract_spectral_profile_from_mef(
            str(real_file), 155.0, -60.28
        )


def test_mef_profile_preserves_flux_when_uncertainty_is_missing_or_invalid(
    tmp_path: Path,
) -> None:
    for value, expected_status in ((np.nan, "nonfinite"), (0.0, "nonpositive"), (-1.0, "nonpositive")):
        source = tmp_path / f"variance-{expected_status}-{value}.fits"
        write_mef(source, include_spectral_wcs=True)
        with fits.open(source, mode="update") as hdus:
            hdus["VARIANCE"].data[3, 3] = value

        point = FITSProcessor.extract_spectral_profile_from_mef(
            str(source), 120.0, 10.0
        )
        assert point["is_valid_measurement"] is True
        assert point["quality_status"] == "valid_with_warnings"
        assert point["flux"] == pytest.approx(10.0)
        assert point["flux_error"] is None
        assert point["uncertainty_available"] is False
        assert point["uncertainty_status"] == expected_status

    source = tmp_path / "missing-variance.fits"
    write_mef(source, include_spectral_wcs=True)
    missing_variance = tmp_path / "missing-variance-extension.fits"
    with fits.open(source) as hdus:
        fits.HDUList([
            hdu.copy() for hdu in hdus if hdu.name != "VARIANCE"
        ]).writeto(missing_variance)
    point_without_variance = FITSProcessor.extract_spectral_profile_from_mef(
        str(missing_variance), 120.0, 10.0
    )
    assert point_without_variance["is_valid_measurement"] is True
    assert point_without_variance["flux"] == pytest.approx(10.0)
    assert point_without_variance["flux_error"] is None
    assert point_without_variance["uncertainty_status"] == "missing"
    assert point_without_variance["uncertainty_unit"] is None

    invalid_flag = tmp_path / "invalid-flag.fits"
    write_mef(invalid_flag, include_spectral_wcs=True)
    with fits.open(invalid_flag, mode="update") as hdus:
        hdus["FLAGS"].data[3, 3] = 64

    invalid_point = FITSProcessor.extract_spectral_profile_from_mef(
        str(invalid_flag), 120.0, 10.0
    )
    assert invalid_point["is_valid_measurement"] is False
    assert invalid_point["flux"] is None
    assert invalid_point["flux_error"] is None
    assert invalid_point["measurement_status"] == "invalid"
    assert invalid_point["quality_status"] == "invalid"
    assert invalid_point["flag_bits"] == [6]
    assert invalid_point["flag_names"] == ["NONFUNC"]


def test_spherex_flag_bitmask_decoding_uses_documented_bits() -> None:
    source_and_transient = FITSProcessor.decode_flag_value(2097152 | 1)
    assert source_and_transient["flag_names"] == ["TRANSIENT", "SOURCE"]
    assert source_and_transient["quality_status"] == "valid_with_warnings"

    overflow = FITSProcessor.decode_flag_value(2)
    assert overflow["flag_names"] == ["OVERFLOW"]
    assert overflow["quality_status"] == "valid_with_warnings"

    sur_error = FITSProcessor.decode_flag_value(4)
    assert sur_error["flag_names"] == ["SUR_ERROR"]
    assert sur_error["quality_status"] == "invalid"

    unknown = FITSProcessor.decode_flag_value(1 << 31)
    assert unknown["unknown_flag_bits"] == [31]
    assert unknown["quality_status"] == "unknown"

    flags = np.array([0, 4, 2097152, 2097153, 1 << 31], dtype=np.int64)
    assert FITSProcessor.flags_usable_mask(flags).tolist() == [
        True, False, True, True, False
    ]


def test_mef_profile_uses_direct_spectral_wcs_pixel_maps(tmp_path: Path) -> None:
    source = tmp_path / "source.fits"
    calibration = tmp_path / "spectral_wcs_D1_spx_cal-swcs-v5-2026-191.fits"
    write_mef(source, include_spectral_wcs=True)
    cwave = fits.ImageHDU(np.full((8, 8), 1.37, dtype=np.float32), name="CWAVE")
    cwave.header["BUNIT"] = "um"
    cband = fits.ImageHDU(np.full((8, 8), 0.041, dtype=np.float32), name="CBAND")
    cband.header["BUNIT"] = "um"
    fits.HDUList([fits.PrimaryHDU(), cwave, cband]).writeto(calibration, checksum=True)

    point = FITSProcessor.extract_spectral_profile_from_mef(
        str(source),
        120.0,
        10.0,
        spectral_wcs_filepath=str(calibration),
    )

    assert point["wavelength_um"] == pytest.approx(1.37)
    assert point["bandwidth_um"] == pytest.approx(0.041)
    assert point["wavelength_source"] == "Official Spectral WCS CWAVE/CBAND direct pixel lookup"
    assert point["flux"] == pytest.approx(10.0)
