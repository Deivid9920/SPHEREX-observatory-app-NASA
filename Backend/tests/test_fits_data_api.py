import json
import hashlib
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints import data as data_endpoint
from app.api.v1.endpoints import sky as sky_endpoint
from app.core.database import Base
from app.services.fits_inventory import FitsInventory
from app.services.fits_processor import FITSProcessor
from app.services.irsa_client import IRSAQueryError


def test_spectral_profile_reports_per_observation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    irsa_service = ModuleType("app.services.irsa_client")
    irsa_service.IRSAClient = object
    irsa_service.IRSAQueryError = IRSAQueryError
    monkeypatch.setitem(sys.modules, "app.services.irsa_client", irsa_service)

    from app.api.v1.endpoints import spectral as spectral_endpoint

    observations = [
        {"obs_id": "valid", "t_min": 60000.0},
        {"obs_id": "download-missing", "t_min": 60001.0},
        {"obs_id": "extract-fails", "t_min": 60002.0},
    ]

    class FakeIRSAClient:
        def query_spherex_observations(self, **kwargs):
            return observations

        def download_cutouts_parallel(self, **kwargs):
            return {"valid": "valid.fits", "extract-fails": "invalid.fits"}

    def extract_profile(filepath: str, ra: float, dec: float):
        if filepath == "invalid.fits":
            raise ValueError("invalid test FITS")
        return {
            "wavelength_um": 1.2,
            "flux_mjy_sr": 3.4,
            "flux_error_mjy_sr": 0.2,
            "flag": 0,
            "is_valid_measurement": True,
        }

    monkeypatch.setattr(spectral_endpoint, "irsa_client", FakeIRSAClient())
    monkeypatch.setattr(
        spectral_endpoint.FITSProcessor,
        "extract_spectral_profile_from_mef",
        staticmethod(extract_profile),
    )

    response = spectral_endpoint.get_spectral_profile(ra=120.0, dec=10.0)

    assert response["status"] == "partial"
    assert response["total_channels_measured"] == 1
    assert [item["obs_id"] for item in response["failed_observations"]] == [
        "download-missing",
        "extract-fails",
    ]


@pytest.fixture
def local_fits_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw"
    fits_path = root / "observation.fits"
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [4, 4]
    wcs.wcs.crval = [120.0, 10.0]
    wcs.wcs.cdelt = [-0.001, 0.001]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    primary = fits.PrimaryHDU()
    image = fits.ImageHDU(
        np.arange(64, dtype=np.float32).reshape((8, 8)),
        header=wcs.to_header(),
        name="IMAGE",
    )
    fits_path.parent.mkdir(parents=True)
    fits.HDUList([primary, image]).writeto(fits_path, checksum=True)

    consumers_path = tmp_path / "consumers.json"
    consumers_path.write_text(
        json.dumps({"observation.fits": ["sky_explorer"]}),
        encoding="utf-8",
    )
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(consumers_path),
    )
    manifest = inventory.build()
    monkeypatch.setattr(data_endpoint, "fits_inventory", inventory)
    monkeypatch.setattr(
        data_endpoint.settings,
        "SPHEREX_PROCESSED_DIR",
        str(tmp_path / "processed"),
    )
    monkeypatch.setattr(
        data_endpoint.settings,
        "SPHEREX_CALIBRATION_DIR",
        str(tmp_path / "calibration"),
    )
    app = FastAPI()
    app.include_router(data_endpoint.router, prefix="/data")
    return TestClient(app), manifest["files"][0], fits_path


@pytest.fixture
def local_results_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    yield override_get_db
    engine.dispose()


def test_fits_data_api_lists_metadata_previews_and_downloads_original(
    local_fits_api,
) -> None:
    client, entry, fits_path = local_fits_api
    inventory = data_endpoint.fits_inventory
    legacy_manifest = json.loads(inventory.manifest_path.read_text(encoding="utf-8"))
    for item in legacy_manifest["files"]:
        item.pop("spatial_wcs", None)
        item.pop("astrometric_validation_status", None)
        for extension in item["extensions"]:
            extension.pop("spatial_wcs", None)
    inventory.manifest_path.write_text(
        json.dumps(legacy_manifest),
        encoding="utf-8",
    )

    listing = client.get("/data/fits?module=sky_explorer")
    metadata = client.get(f"/data/fits/{entry['file_id']}")
    preview = client.get(f"/data/fits/{entry['file_id']}/preview?hdu=1")
    download = client.get(f"/data/fits/{entry['file_id']}/download")

    assert listing.status_code == 200
    assert listing.json()["files"][0]["file_id"] == entry["file_id"]
    assert (
        listing.json()["files"][0]["spatial_wcs"]["structural_status"]
        == "WCS_STRUCTURALLY_VALID"
    )
    assert (
        listing.json()["files"][0]["astrometric_validation_status"]
        == "ASTROMETRY_UNVALIDATED"
    )
    assert client.get("/data/fits?module=spectral_analysis").json()["total"] == 0
    assert client.get("/data/fits?module=object_detection").json()["total"] == 0
    assert client.get("/data/fits?module=discovery_catalog").json()["total"] == 0
    assert metadata.status_code == 200
    assert metadata.json()["extensions"][1]["name"] == "IMAGE"
    assert (
        metadata.json()["spatial_wcs"]["sip_status"]
        == "SIP_CONFIRMED_INACTIVE"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert download.status_code == 200
    assert download.content == fits_path.read_bytes()
    assert download.headers["x-content-sha256"] == entry["sha256"]


def test_spectral_profile_persists_quality_state_and_associated_external_maps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_results_database,
) -> None:
    root = tmp_path / "raw"
    mef_path = root / (
        "level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits"
    )
    spatial_wcs = WCS(naxis=2)
    spatial_wcs.wcs.crpix = [4, 4]
    spatial_wcs.wcs.crval = [120.0, 10.0]
    spatial_wcs.wcs.cdelt = [-0.001, 0.001]
    spatial_wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    image_header = spatial_wcs.to_header()
    image_header["DETECTOR"] = 1
    image_header["DATE-OBS"] = "2025-07-07T00:07:23.351"
    image_header["BAND"] = "B1"
    image_header["BUNIT"] = "MJy/sr"
    image_header["PSF_FWHM"] = 2.0
    image_header["CALLEVEL"] = "2"
    image_header["CAL_VER"] = "1.0"
    spectral_wcs = WCS(naxis=2)
    spectral_wcs.wcs.ctype = ["WAVE", "LINEAR"]
    spectral_wcs.wcs.cunit = ["um", "pix"]
    spectral_wcs.wcs.crpix = [4, 4]
    spectral_wcs.wcs.crval = [1.2, 0.0]
    spectral_wcs.wcs.cdelt = [0.01, 1.0]
    image_header.extend(spectral_wcs.to_header(key="W"))
    image = fits.ImageHDU(
        np.full((8, 8), 3.4, dtype=np.float32),
        header=image_header,
        name="IMAGE",
    )
    variance = fits.ImageHDU(np.full((8, 8), 0.04, dtype=np.float32), name="VARIANCE")
    variance.header["BUNIT"] = "MJy2/sr2"
    flags = fits.ImageHDU(np.zeros((8, 8), dtype=np.int16), name="FLAGS")
    flags.data[3, 3] = 4

    def control_table() -> fits.BinTableHDU:
        values = np.empty((1, 2, 2, 2), dtype=np.float32)
        values[..., 0] = 1.37
        values[..., 1] = 0.041
        table = fits.BinTableHDU.from_columns(
            [
                fits.Column(name="X", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
                fits.Column(name="Y", format="2J", dim="(2)", array=np.array([[1, 8]], dtype=np.int32)),
                fits.Column(name="VALUES", format="8E", dim="(2,2,2)", array=values),
            ],
            name="WCS-WAVE",
        )
        table.header["DETECTOR"] = 1
        return table

    mef_path.parent.mkdir(parents=True)
    fits.HDUList([
        fits.PrimaryHDU(header=fits.Header({"RELEASE": "DR1"})),
        image,
        variance,
        flags,
        control_table(),
    ]).writeto(mef_path, checksum=True)

    calibration_root = tmp_path / "calibration"
    calibration_dir = calibration_root / "spectral_wcs"
    calibration_dir.mkdir(parents=True)
    calibration_path = calibration_dir / "spectral_wcs_D1_spx_cal-swcs-v5-2026-191.fits"
    cwave = fits.ImageHDU(np.full((8, 8), 1.37, dtype=np.float32), name="CWAVE")
    cwave.header["BUNIT"] = "um"
    cwave.header["DETECTOR"] = 1
    cband = fits.ImageHDU(np.full((8, 8), 0.041, dtype=np.float32), name="CBAND")
    cband.header["BUNIT"] = "um"
    cband.header["DETECTOR"] = 1
    fits.HDUList([fits.PrimaryHDU(), cwave, cband, control_table()]).writeto(
        calibration_path,
        checksum=True,
    )
    digest = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    (calibration_dir / "spectral-wcs-manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "products": [{
                "filename": calibration_path.name,
                "release": "DR1",
                "sha256": digest,
                "size_bytes": calibration_path.stat().st_size,
            }],
        }),
        encoding="utf-8",
    )
    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "consumers.json"),
    )
    entry = inventory.build()["files"][0]
    monkeypatch.setattr(data_endpoint, "fits_inventory", inventory)
    monkeypatch.setattr(data_endpoint.settings, "SPHEREX_CALIBRATION_DIR", str(calibration_root))
    app = FastAPI()
    app.include_router(data_endpoint.router, prefix="/data")
    app.dependency_overrides[data_endpoint.get_db] = local_results_database
    client = TestClient(app)
    center = spatial_wcs.pixel_to_world(3.0, 3.0)

    response = client.post(
        f"/data/fits/{entry['file_id']}/spectral-runs"
        f"?ra={center.ra.deg}&dec={center.dec.deg}"
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["calibration_status"] == "verified"
    assert result["measurements"][0]["wavelength_um"] == pytest.approx(1.37)
    assert result["measurements"][0]["bandwidth_um"] == pytest.approx(0.041)
    assert result["pixel_x"] == 3
    assert result["pixel_y"] == 3
    assert result["quality_status"] == "invalid"
    assert result["valid_channel_count"] == 0
    assert result["measurements"][0]["quality_status"] == "invalid"
    assert result["measurements"][0]["flag_names"] == ["SUR_ERROR"]
    assert result["measurements"][0]["flux"] is None
    assert result["wavelength_source"].startswith("Official Spectral WCS")
    assert result["calibration_profile"]["calibrations"]["spectral_wcs"]["selected_product"]["sha256"] == digest
    assert result["calibration_product_ids"] == [
        result["calibration_profile"]["calibrations"]["spectral_wcs"]["selected_product"]["calibration_id"]
    ]
    assert any("absolute photometric calibration" in warning for warning in result["warnings"])
    recovered = client.get(f"/data/scientific-runs/{result['run_id']}")
    assert recovered.status_code == 200
    assert recovered.json()["validation_status"] == "BLOCKED"
    assert recovered.json()["result"]["pixel_x"] == 3
    assert recovered.json()["result"]["measurements"] == result["measurements"]
    assert recovered.json()["result"]["calibration_product_ids"] == result["calibration_product_ids"]


def test_calibration_diagnosis_and_registry_are_exposed(local_fits_api) -> None:
    client, entry, _ = local_fits_api

    diagnosis = client.get(f"/data/fits/{entry['file_id']}/calibration")
    catalog = client.get("/data/calibrations")
    missing = client.get("/data/fits/unknown/calibration")

    assert diagnosis.status_code == 200
    assert diagnosis.json()["file_id"] == entry["file_id"]
    assert diagnosis.json()["overall_calibration_status"] == "partially_verified"
    assert diagnosis.json()["operation_authorizations"]["photometry"]["authorized"] is False
    assert catalog.status_code == 200
    assert "spectral_wcs" in {item["type"] for item in catalog.json()["registered_types"]}
    assert missing.status_code == 404


def test_irsa_api_failure_keeps_local_inventory_available(
    local_fits_api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = local_fits_api

    class FailingIRSAClient:
        def query_spherex_observations(self, **kwargs):
            raise IRSAQueryError("IRSA TAP timed out.")

    async def no_cached_value(key: str):
        return None

    async def discard_cache_value(key: str, value: str, expire_seconds: int):
        return True

    monkeypatch.setattr(sky_endpoint, "irsa_client", FailingIRSAClient())
    monkeypatch.setattr(sky_endpoint.redis_cache, "get", no_cached_value)
    monkeypatch.setattr(sky_endpoint.redis_cache, "set", discard_cache_value)
    client.app.include_router(sky_endpoint.router, prefix="/sky")

    remote = client.get("/sky/observations?ra=212.123&dec=18.456")
    local = client.get("/data/fits?module=sky_explorer")

    assert remote.status_code == 502
    assert "FITS locales siguen disponibles" in remote.json()["detail"]
    assert local.status_code == 200
    assert local.json()["total"] == 1


def test_fits_data_api_reports_not_found_invalid_hdu_and_stale_hash(
    local_fits_api,
) -> None:
    client, entry, fits_path = local_fits_api

    assert client.get("/data/fits/unknown/download").status_code == 404
    assert client.get(f"/data/fits/{entry['file_id']}/preview?hdu=0").status_code == 422
    with fits_path.open("ab") as file:
        file.write(b"changed")
    stale = client.get(f"/data/fits/{entry['file_id']}/download")
    assert stale.status_code == 409


def test_spectral_cube_preview_extraction_and_invalid_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_results_database,
) -> None:
    root = tmp_path / "raw"
    cube_path = root / "cube.fits"
    wcs = WCS(naxis=3)
    wcs.wcs.crpix = [4, 4, 1]
    wcs.wcs.crval = [120.0, 10.0, 1.0]
    wcs.wcs.cdelt = [-0.001, 0.001, 0.1]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN", "WAVE"]
    wcs.wcs.cunit = ["deg", "deg", "um"]
    image = fits.ImageHDU(
        np.arange(3 * 8 * 8, dtype=np.float32).reshape((3, 8, 8)),
        header=wcs.to_header(),
        name="IMAGE",
    )
    image.header["BUNIT"] = "MJy/sr"
    flags = np.zeros((3, 8, 8), dtype=np.int16)
    flags[1, 3, 3] = 64
    channel_flags = fits.ImageHDU(flags, name="FLAGS")
    channel_table = fits.BinTableHDU.from_columns(
        [fits.Column(
            name="WAVELENGTH",
            format="E",
            unit="um",
            array=np.array([1.0, 1.1, 1.2], dtype=np.float32),
        ), fits.Column(
            name="BANDWIDTH",
            format="E",
            unit="um",
            array=np.array([0.1, 0.1, 0.1], dtype=np.float32),
        ), fits.Column(
            name="WL_MIN",
            format="E",
            unit="um",
            array=np.array([0.95, 1.04, 1.15], dtype=np.float32),
        ), fits.Column(
            name="WL_MAX",
            format="E",
            unit="um",
            array=np.array([1.05, 1.16, 1.25], dtype=np.float32),
        )],
        name="SPECTRAL_CHANNELS",
    )
    cube_path.parent.mkdir(parents=True)
    fits.HDUList([fits.PrimaryHDU(), image, channel_flags, channel_table]).writeto(
        cube_path, checksum=True
    )

    inventory = FitsInventory(
        str(root),
        str(tmp_path / "manifest.json"),
        str(tmp_path / "missing-consumers.json"),
    )
    entry = inventory.build()["files"][0]
    monkeypatch.setattr(data_endpoint, "fits_inventory", inventory)
    monkeypatch.setattr(
        data_endpoint.settings,
        "SPHEREX_PROCESSED_DIR",
        str(tmp_path / "processed"),
    )
    monkeypatch.setattr(
        data_endpoint.settings,
        "SPHEREX_CALIBRATION_DIR",
        str(tmp_path / "calibration"),
    )
    app = FastAPI()
    app.include_router(data_endpoint.router, prefix="/data")
    app.dependency_overrides[data_endpoint.get_db] = local_results_database
    client = TestClient(app)

    assert entry["product_type"] == "all_sky_spectral_cube"
    assert entry["consumers"] == ["sky_explorer", "spectral_analysis"]
    preview = client.get(f"/data/fits/{entry['file_id']}/preview?plane=1")
    profile = client.get(
        f"/data/fits/{entry['file_id']}/spectral-profile?ra=120&dec=10"
    )
    outside = client.get(
        f"/data/fits/{entry['file_id']}/spectral-profile?ra=120.1&dec=10"
    )
    invalid = client.get(
        f"/data/fits/{entry['file_id']}/spectral-profile?ra=120&dec=91"
    )

    assert preview.status_code == 200
    assert preview.headers["x-fits-plane"] == "1"
    assert preview.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert profile.status_code == 200, profile.text
    payload = profile.json()
    assert payload["sha256"] == entry["sha256"]
    assert payload["wavelength_source"].startswith("SPECTRAL_CHANNELS")
    assert payload["bandwidth_available"] is True
    assert payload["measurements"][0]["bandwidth_um"] == pytest.approx(0.1)
    assert payload["uncertainty_available"] is False
    assert payload["uncertainty_status"] == "missing"
    assert payload["quality_status"] == "valid_with_warnings"
    assert payload["pixel_x"] == 3
    assert payload["pixel_y"] == 3
    assert payload["calibration_profile"]["calibrations"]["spectral_channels"]["status"] == "partially_verified"
    assert "independently" in payload["calibration_profile"]["calibrations"]["spectral_channels"]["reason"]
    assert [point["wavelength_um"] for point in payload["measurements"]] == pytest.approx([1.0, 1.1, 1.2])
    assert [point["is_valid_measurement"] for point in payload["measurements"]] == [True, False, True]
    assert payload["measurements"][1]["flux"] is None
    assert payload["measurements"][1]["flag_names"] == ["NONFUNC"]
    assert outside.status_code == 404
    assert outside.json()["detail"]["code"] == "COORDINATE_OUTSIDE_IMAGE"
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "INVALID_SKY_COORDINATE"

    created = client.post(
        f"/data/fits/{entry['file_id']}/spectral-runs?ra=120&dec=10"
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    recovered = client.get(f"/data/scientific-runs/{run_id}")
    assert recovered.status_code == 200
    recovered_payload = recovered.json()
    assert recovered_payload["source"]["sha256"] == entry["sha256"]
    assert recovered_payload["source"]["hdu"] == 1
    assert (
        recovered_payload["result"]["coordinate_provenance"]
        == created.json()["coordinate_provenance"]
    )
    assert recovered_payload["result"]["astrometric_validation_status"] == (
        "ASTROMETRY_UNVALIDATED"
    )
    assert (
        recovered_payload["calibration_product_ids"]
        == created.json()["calibration_product_ids"]
    )
    assert len(recovered_payload["calibration_product_ids"]) == 1
    assert recovered_payload["result"]["measurements"] == created.json()["measurements"]
    assert recovered_payload["result_sha256"] == created.json()["result_sha256"]
    assert recovered_payload["result"]["calibration_profile"] == created.json()["calibration_profile"]
    assert recovered_payload["calibration_product_ids"] == created.json()["calibration_product_ids"]

    replay = client.post(f"/data/scientific-runs/{run_id}/replay")
    assert replay.status_code == 200, replay.text
    assert replay.json()["source_sha256"] == entry["sha256"]
    replayed_run = client.get(
        f"/data/scientific-runs/{replay.json()['replay_run_id']}"
    ).json()
    original_result = dict(recovered_payload["result"])
    replay_result = dict(replayed_run["result"])
    original_result.pop("processed_at")
    replay_result.pop("processed_at")
    original_result["coordinate_provenance"].pop("processed_at")
    replay_result["coordinate_provenance"].pop("processed_at")
    assert replay_result == original_result
    assert replay.json()["exact_match"] is True
    assert replay.json()["replay_run_id"] != run_id

    with fits.open(cube_path, mode="readonly") as hdus:
        variance = fits.ImageHDU(
            np.full((3, 8, 8), 4.0, dtype=np.float32),
            name="VARIANCE",
        )
        variance.header["BUNIT"] = "MJy2/sr2"
        variance_path = tmp_path / "cube-with-variance.fits"
        fits.HDUList([
            hdus[0].copy(),
            hdus[1].copy(),
            hdus[2].copy(),
            variance,
            hdus[3].copy(),
        ]).writeto(variance_path, checksum=True)
    measured = FITSProcessor.extract_spectral_profile_from_cube(
        str(variance_path),
        ra=120.0,
        dec=10.0,
    )
    assert measured["uncertainty_available"] is True
    assert measured["measurements"][0]["flux_error"] == pytest.approx(2.0)

    missing_unit_path = tmp_path / "cube-without-wavelength-unit.fits"
    with fits.open(cube_path, mode="readonly") as hdus:
        no_unit_table = fits.BinTableHDU.from_columns(
            [fits.Column(
                name="WAVELENGTH",
                format="E",
                array=np.array([1.0, 1.1, 1.2], dtype=np.float32),
            )],
            name="SPECTRAL_CHANNELS",
        )
        fits.HDUList([
            hdus[0].copy(),
            hdus[1].copy(),
            hdus[2].copy(),
            no_unit_table,
        ]).writeto(missing_unit_path, checksum=True)
    with pytest.raises(ValueError, match="no declara unidad"):
        FITSProcessor.extract_spectral_profile_from_cube(
            str(missing_unit_path),
            ra=120.0,
            dec=10.0,
        )
