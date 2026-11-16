#!/usr/bin/env python3
"""Reproduce the local WCS audit and optional independent catalog probe."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
import astropy.units as u
from astropy.wcs import WCS


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
RAW_ROOT = BACKEND_ROOT / "app" / "data" / "raw" / "spherex"
MANIFEST_PATH = (
    BACKEND_ROOT / "app" / "data" / "processed" / "spherex" / "fits-manifest.json"
)
DEFAULT_OUTPUT = BACKEND_ROOT / "reports" / "evidence" / "phase454-astrometry-audit.json"
SIP_COEFFICIENT = re.compile(r"^(A|B|AP|BP)_(\d+)_(\d+)$")
sys.path.insert(0, str(BACKEND_ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _header_metadata(path: Path, expected_sha: str | None) -> dict[str, Any]:
    with fits.open(path, mode="readonly", memmap=True) as hdus:
        image_index = hdus.index_of("IMAGE")
        image = hdus["IMAGE"]
        header = image.header
        data = image.data
        if data is None:
            raise ValueError(f"{path.name}: IMAGE extension has no data.")
        actual_sha = _sha256(path)
        full_wcs = WCS(header, fobj=hdus, relax=True)
        celestial = full_wcs.celestial

        coefficients: dict[str, list[tuple[str, float]]] = {
            family: [] for family in ("A", "B", "AP", "BP")
        }
        for key, value in header.items():
            match = SIP_COEFFICIENT.match(key)
            if match:
                coefficients[match.group(1)].append((key, float(value)))

        sip_families: dict[str, Any] = {}
        for family in ("A", "B", "AP", "BP"):
            order_key = f"{family}_ORDER"
            order = header.get(order_key)
            rows = coefficients[family]
            invalid = [key for key, value in rows if not math.isfinite(value)]
            expected_terms = (
                {
                    (i, j)
                    for i in range(int(order) + 1)
                    for j in range(int(order) + 1 - i)
                    if i + j >= 2
                }
                if order is not None
                else set()
            )
            actual_terms = {
                tuple(map(int, key[len(family) + 1 :].split("_")))
                for key, _ in rows
            }
            sip_families[family] = {
                "order": order,
                "coefficient_count": len(rows),
                "finite_coefficient_count": len(rows) - len(invalid),
                "nonzero_constant_or_linear_terms": [
                    {
                        "key": key,
                        "value": value,
                    }
                    for key, value in rows
                    if sum(
                        map(int, key[len(family) + 1 :].split("_"))
                    ) < 2 and value != 0.0
                ],
                "missing_terms_within_order": [
                    list(term) for term in sorted(expected_terms - actual_terms)
                ],
                "terms_above_declared_order": [
                    list(term)
                    for term in sorted(
                        term for term in actual_terms
                        if term[0] + term[1] > int(order)
                    )
                ] if order is not None else [],
                "non_finite_keys": invalid,
            }

        shape = tuple(int(axis) for axis in data.shape)
        if data.ndim == 2:
            ny, nx = shape
            grid = np.array(
                [
                    [x, y]
                    for y in np.linspace(0.0, ny - 1.0, 5)
                    for x in np.linspace(0.0, nx - 1.0, 5)
                ],
                dtype=float,
            )
            sky = celestial.pixel_to_world(grid[:, 0], grid[:, 1])
            recovered = np.column_stack(
                celestial.world_to_pixel(sky)
            )
            round_trip = np.linalg.norm(recovered - grid, axis=1)
        else:
            ny, nx = shape[-2:]
            grid = np.array(
                [
                    [0.0, 0.0],
                    [(nx - 1.0) / 2.0, (ny - 1.0) / 2.0],
                    [nx - 1.0, ny - 1.0],
                ],
                dtype=float,
            )
            sky = celestial.pixel_to_world(grid[:, 0], grid[:, 1])
            recovered = np.column_stack(
                celestial.world_to_pixel(sky)
            )
            round_trip = np.linalg.norm(recovered - grid, axis=1)

        no_sip = celestial.deepcopy()
        no_sip.sip = None
        no_sip_sky = no_sip.pixel_to_world(grid[:, 0], grid[:, 1])
        sip_sky = celestial.pixel_to_world(grid[:, 0], grid[:, 1])
        sip_delta_arcsec = no_sip_sky.separation(sip_sky).arcsec

        alternate_wcs: dict[str, Any] | None = None
        if "CTYPE1W" in header or "CTYPE2W" in header:
            alt = WCS(header, fobj=hdus, relax=True, key="W")
            alternate_wcs = {
                "ctype": list(alt.wcs.ctype),
                "sip_coefficients_attached": alt.sip is not None,
                "ctype_declares_sip": all(
                    "-SIP" in str(axis).upper() for axis in alt.wcs.ctype
                ),
                "interpretation": (
                    "Astropy attaches the primary SIP coefficients to this "
                    "alternate WAVE-TAB WCS despite its CTYPE lacking -SIP."
                    if alt.sip is not None
                    and not all("-SIP" in str(axis).upper() for axis in alt.wcs.ctype)
                    else None
                ),
            }

        filename_metadata = re.search(
            r"_l2b-v(?P<version>[^-]+)-(?P<year>\d{4})-(?P<day>\d{3})\.fits$",
            path.name,
        )
        return {
            "filename": path.name,
            "relative_path": path.relative_to(RAW_ROOT).as_posix(),
            "sha256": actual_sha,
            "manifest_sha256": expected_sha,
            "sha256_matches_manifest": (
                actual_sha.lower() == expected_sha.lower()
                if expected_sha
                else None
            ),
            "image_hdu_index": int(image_index),
            "image_hdu_name": image.name,
            "shape_numpy_order": list(shape),
            "naxis": int(header.get("NAXIS", 0)),
            "naxis1": header.get("NAXIS1"),
            "naxis2": header.get("NAXIS2"),
            "naxis3": header.get("NAXIS3"),
            "detector": header.get("DETECTOR", header.get("DET_ID")),
            "observation_id": header.get(
                "OBSID", header.get("OBS_ID", header.get("OBSID1"))
            ),
            "processing_version": (
                filename_metadata.group("version") if filename_metadata else None
            ),
            "processing_date_filename": (
                f"{filename_metadata.group('year')}-{filename_metadata.group('day')}"
                if filename_metadata
                else None
            ),
            "processing_date_header": header.get("DATE"),
            "date_obs": header.get("DATE-OBS"),
            "mjd_obs": header.get("MJD-OBS"),
            "release_keywords": {
                key: header.get(key)
                for key in ("OBSCOLL", "OBS_COLL", "COLLECT", "RELEASE", "DATAREL", "DR")
                if key in header
            },
            "wcs": {
                "wcsaxes": full_wcs.wcs.naxis,
                "wcsaxes_header": header.get("WCSAXES"),
                "ctype": list(celestial.wcs.ctype),
                "cunit": [str(unit) for unit in celestial.wcs.cunit],
                "crpix": celestial.wcs.crpix.tolist(),
                "crval": celestial.wcs.crval.tolist(),
                "cd": (
                    celestial.wcs.cd.tolist()
                    if celestial.wcs.has_cd()
                    else None
                ),
                "pc": (
                    celestial.wcs.get_pc().tolist()
                    if celestial.wcs.has_pc()
                    else None
                ),
                "cdelt": celestial.wcs.cdelt.tolist(),
                "radesys": celestial.wcs.radesys,
                "equinox": (
                    float(celestial.wcs.equinox)
                    if _finite(celestial.wcs.equinox)
                    else None
                ),
                "lonpole": (
                    float(celestial.wcs.lonpole)
                    if _finite(celestial.wcs.lonpole)
                    else None
                ),
                "latpole": (
                    float(celestial.wcs.latpole)
                    if _finite(celestial.wcs.latpole)
                    else None
                ),
                "axis_correlation_matrix": full_wcs.axis_correlation_matrix.tolist(),
            },
            "finast": header.get("FINAST"),
            "sip": {
                "active_in_primary_celestial_wcs": celestial.sip is not None,
                "families": sip_families,
            },
            "alternate_wcs_w": alternate_wcs,
            "round_trip": {
                "sample_points": len(grid),
                "max_error_pixels": float(np.max(round_trip)),
                "p95_error_pixels": float(np.percentile(round_trip, 95)),
            },
            "sip_vs_no_sip_diagnostic_arcsec": {
                "median": float(np.median(sip_delta_arcsec)),
                "p95": float(np.percentile(sip_delta_arcsec, 95)),
                "maximum": float(np.max(sip_delta_arcsec)),
                "is_accuracy_validation": False,
            },
        }


def _catalog_probe(first_mef: dict[str, Any], path: Path) -> dict[str, Any]:
    from astroquery.ipac.irsa import Irsa
    from pyvo.dal import TAPService

    Irsa.TIMEOUT = 90
    Irsa.ROW_LIMIT = 2000
    with fits.open(path, mode="readonly", memmap=True) as hdus:
        header = hdus["IMAGE"].header
        center = SkyCoord(
            float(header["CRVAL1"]) * u.deg,
            float(header["CRVAL2"]) * u.deg,
            frame="icrs",
        )
        observation_mjd = float(header["MJD-OBS"])

    result: dict[str, Any] = {
        "status": "querying",
        "query_time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_product": first_mef["filename"],
        "target_center_icrs_deg": [float(center.ra.deg), float(center.dec.deg)],
        "observation_mjd": observation_mjd,
        "catwise2020_position_epoch_mjd": 57170.0,
        "catwise2020_epoch_source": "Marocco et al. 2021, arXiv:2012.13084, Section II",
        "catwise_tile_corrections_applied": False,
        "catwise_correction_caveat": (
            "The paper reports tile-level CatWISE2020 offsets relative to Gaia DR2. "
            "They were not applied because that would introduce Gaia-derived "
            "corrections into this independent-catalog pilot."
        ),
        "catalogs": {},
        "metadata": {},
        "pilot_crossmatch": None,
        "is_astrometric_validation": False,
    }

    try:
        tap = TAPService("https://irsa.ipac.caltech.edu/TAP")
        metadata = tap.run_sync(
            "SELECT column_name, unit, description FROM TAP_SCHEMA.columns "
            "WHERE table_name = 'catwise_2020' AND column_name IN "
            "('ra','dec','meanobsmjd','pmra','pmdec','sigpmra','sigpmdec',"
            "'sigra','sigdec','w1snr','w2snr','rchi2_pm','cc_flags')",
            maxrec=100,
        ).to_table()
        result["metadata"] = {
            str(row["column_name"]): {
                "unit": str(row["unit"]),
                "description": str(row["description"]),
            }
            for row in metadata
        }
    except Exception as exc:
        result["metadata"] = {
            "status": "query_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    query_specs = (
        ("2MASS_PSC", "fp_psc", 0.25),
        ("CatWISE2020", "catwise_2020", 0.1),
    )
    for label, catalog, radius_deg in query_specs:
        try:
            table = Irsa.query_region(
                center,
                catalog=catalog,
                spatial="Cone",
                radius=radius_deg * u.deg,
            )
            row_count = len(table)
            result["catalogs"][label] = {
                "catalog_table": catalog,
                "radius_deg": radius_deg,
                "rows_returned": row_count,
                "row_limit": Irsa.ROW_LIMIT,
                "row_limit_reached": row_count >= Irsa.ROW_LIMIT,
                "columns": list(table.colnames),
                "position_epoch_fields_available": (
                    "meanobsmjd" in table.colnames
                ),
                "proper_motion_fields_available": all(
                    key in table.colnames for key in ("pmra", "pmdec")
                ),
            }
            if label == "CatWISE2020":
                result["pilot_crossmatch"] = _pilot_crossmatch(
                    table, path, center, observation_mjd
                )
        except Exception as exc:
            result["catalogs"][label] = {
                "catalog_table": catalog,
                "radius_deg": radius_deg,
                "status": "query_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    result["status"] = (
        "catalogs_queried"
        if any("rows_returned" in item for item in result["catalogs"].values())
        else "catalog_query_blocked"
    )
    return result


def _pilot_crossmatch(
    table: Any, path: Path, center: SkyCoord, observation_mjd: float
) -> dict[str, Any]:
    from scipy.spatial import cKDTree
    from app.services.astrometry import build_spatial_wcs
    from app.services.fits_processor import FITSProcessor
    from app.services.temporal_engine import TemporalEngine

    numeric_fields = (
        "ra", "dec", "pmra", "pmdec", "sigpmra", "sigpmdec",
        "sigra", "sigdec", "w1snr", "w2snr", "rchi2_pm",
    )
    usable = np.ones(len(table), dtype=bool)
    for field in numeric_fields:
        values = np.asarray(table[field], dtype=float)
        usable &= np.isfinite(values)
    usable &= np.asarray(table["w1snr"], dtype=float) > 10
    usable &= np.asarray(table["w2snr"], dtype=float) > 5
    usable &= np.asarray(table["sigra"], dtype=float) < 1
    usable &= np.asarray(table["sigdec"], dtype=float) < 1
    usable &= np.asarray(table["sigpmra"], dtype=float) < 0.1
    usable &= np.asarray(table["sigpmdec"], dtype=float) < 0.1
    usable &= np.asarray(table["rchi2_pm"], dtype=float) < 5
    usable &= np.asarray([
        str(value).strip() == "0000" for value in table["cc_flags"]
    ])
    quality_table = table[usable]

    with fits.open(path, mode="readonly", memmap=True) as hdus:
        image_hdu = hdus["IMAGE"]
        image = np.asarray(image_hdu.data, dtype=np.float32)
        valid = np.isfinite(image)
        if "FLAGS" in hdus:
            valid &= FITSProcessor.flags_usable_mask(hdus["FLAGS"].data)
        if "VARIANCE" in hdus:
            variance = hdus["VARIANCE"].data
            valid &= np.isfinite(variance) & (variance > 0)
        spatial_wcs = build_spatial_wcs(image_hdu.header, fobj=hdus)
        valid_image = np.where(valid, image, np.nan)
        detections = TemporalEngine.detect_sources_in_epoch(
            valid_image,
            spatial_wcs.wcs,
            threshold_sigma=5.0,
        )

    if len(quality_table) == 0:
        return {
            "quality_reference_rows": 0,
            "detections_from_unvalidated_global_threshold": len(detections),
            "candidate_pairs_within_8_pixels": 0,
            "accepted_astrometric_associations": 0,
            "excluded_from_residual_metrics": 0,
        }

    reference = SkyCoord(
        ra=np.asarray(quality_table["ra"], dtype=float) * u.deg,
        dec=np.asarray(quality_table["dec"], dtype=float) * u.deg,
        pm_ra_cosdec=(
            np.asarray(quality_table["pmra"], dtype=float) * u.arcsec / u.yr
        ),
        pm_dec=np.asarray(quality_table["pmdec"], dtype=float) * u.arcsec / u.yr,
        obstime=Time(57170.0, format="mjd", scale="utc"),
        frame="icrs",
    )
    propagated = reference.apply_space_motion(
        new_obstime=Time(observation_mjd, format="mjd", scale="utc")
    )
    with fits.open(path, mode="readonly", memmap=True) as hdus:
        spatial_wcs = build_spatial_wcs(hdus["IMAGE"].header, fobj=hdus)
        x_ref, y_ref = spatial_wcs.wcs.world_to_pixel(propagated)
        height, width = hdus["IMAGE"].data.shape
    ref_pixels = np.column_stack((x_ref, y_ref))
    inside = (
        np.isfinite(ref_pixels).all(axis=1)
        & (x_ref >= 0)
        & (x_ref < width)
        & (y_ref >= 0)
        & (y_ref < height)
    )
    ref_pixels = ref_pixels[inside]
    detections_xy = np.array(
        [[item["x"], item["y"]] for item in detections],
        dtype=float,
    )
    pairs = 0
    if len(ref_pixels) and len(detections_xy):
        detection_tree = cKDTree(detections_xy)
        reference_tree = cKDTree(ref_pixels)
        ref_distances, ref_indices = detection_tree.query(
            ref_pixels, k=2, distance_upper_bound=8.0
        )
        _, detection_ref_indices = reference_tree.query(
            detections_xy, k=1, distance_upper_bound=8.0
        )
        for index, (distance, detection_index) in enumerate(
            zip(ref_distances[:, 0], ref_indices[:, 0])
        ):
            if (
                np.isfinite(distance)
                and detection_index < len(detections_xy)
                and detection_ref_indices[detection_index] == index
                and ref_distances[index, 1] > distance * 1.5
            ):
                pairs += 1

    return {
        "quality_filter": {
            "w1snr_gt": 10,
            "w2snr_gt": 5,
            "position_uncertainty_arcsec_lt": 1,
            "proper_motion_uncertainty_arcsec_per_year_lt": 0.1,
            "rchi2_pm_lt": 5,
            "cc_flags": "0000",
        },
        "catalog_rows_received": len(table),
        "quality_reference_rows": len(quality_table),
        "quality_references_projected_inside_image": int(np.count_nonzero(inside)),
        "detections_from_unvalidated_global_threshold": len(detections),
        "candidate_pairs_within_8_pixels": pairs,
        "accepted_astrometric_associations": 0,
        "excluded_from_residual_metrics": pairs,
        "exclusion_reason": (
            "Pilot covers only a 0.1-degree-radius central cone; the selected "
            "single-image detector has no demonstrated false-positive rate, "
            "centroid uncertainty, or injection/recovery calibration. These "
            "mutual-nearest pairs are candidate associations only."
        ),
        "proper_motion_propagation": (
            "CatWISE2020 ICRS coordinate epoch MJD 57170 to SPHEREx MJD-OBS "
            "using pmra/pmdec in arcsec/yr, with pmra interpreted as the "
            "alpha-star component. No radial velocity or distance was applied."
        ),
        "position_epoch_mjd": 57170.0,
        "catalog_tile_corrections_applied": False,
        "correction_note": (
            "CatWISE2020 paper documents Gaia DR2-derived tile offset corrections; "
            "not applied in this independent-catalog pilot."
        ),
        "spatial_coverage": "central cone only; edges and corners not sampled",
        "is_astrometric_validation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-probe",
        action="store_true",
        help="Query IRSA 2MASS PSC and CatWISE2020 for a bounded pilot region.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the machine-readable audit evidence.",
    )
    args = parser.parse_args()

    if not MANIFEST_PATH.is_file():
        print(f"Manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        return 2
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected_hashes = {
        item["relative_path"]: item["sha256"]
        for item in manifest.get("files", [])
        if item.get("relative_path") and item.get("sha256")
    }

    products = []
    for path in sorted(RAW_ROOT.rglob("*.fits")):
        relative = path.relative_to(RAW_ROOT).as_posix()
        product = _header_metadata(path, expected_hashes.get(relative))
        products.append(product)

    if len(products) != 10:
        print(
            f"Expected ten FITS products, found {len(products)} under {RAW_ROOT}.",
            file=sys.stderr,
        )
        return 2

    mefs = [product for product in products if product["naxis"] == 2]
    cubes = [product for product in products if product["naxis"] == 3]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_WITH_LIMITATIONS",
        "manifest_path": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256(MANIFEST_PATH),
        "manifest_entries": len(expected_hashes),
        "products_found": len(products),
        "mefs_found": len(mefs),
        "cubes_found": len(cubes),
        "hash_mismatches": [
            product["relative_path"]
            for product in products
            if product["sha256_matches_manifest"] is False
            or product["sha256_matches_manifest"] is None
        ],
        "products": products,
        "catalog_probe": None,
        "scientific_limitations": [
            "Internal round-trip checks do not establish absolute astrometric accuracy.",
            "The primary celestial MEF CTYPE declares TAN-SIP; the alternate WAVE-TAB WCS lacks a SIP suffix while Astropy detects inherited SIP coefficients.",
            "No celestial WCS or FITS original is modified by this audit.",
        ],
    }

    if args.catalog_probe:
        first = next(
            product for product in mefs
            if "level2_" in product["filename"]
        )
        first_path = RAW_ROOT / first["relative_path"]
        try:
            payload["catalog_probe"] = _catalog_probe(first, first_path)
        except Exception as exc:
            payload["catalog_probe"] = {
                "status": "catalog_probe_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "is_astrometric_validation": False,
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "products": len(products),
        "mefs": len(mefs),
        "cubes": len(cubes),
        "hash_mismatches": payload["hash_mismatches"],
        "catalog_probe_status": (
            payload["catalog_probe"].get("status")
            if payload["catalog_probe"]
            else "not_requested"
        ),
    }, indent=2))
    return 0 if not payload["hash_mismatches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
