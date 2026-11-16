from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import astropy.units as u
from astropy.io import fits
from astropy.wcs import WCS

from app.services.fits_inventory import FitsInventory


OFFICIAL_PRODUCTS: Tuple[Dict[str, str], ...] = (
    {
        "type": "spectral_wcs",
        "filename": "spectral_wcs_D[Detector]_spx_cal-wcs-v[Version]-[Processing Date].fits",
        "purpose": "CWAVE/CBAND maps for scientific spectral analysis of Spectral Image MEFs.",
        "application": "Additional analysis calibration; the embedded WCS-WAVE table is for visualization.",
    },
    {
        "type": "absolute_gain_matrix",
        "filename": "abs_gain_matrix_D[Detector]_spx_cal-agm-v[Version]-[Processing Date].fits",
        "purpose": "Pipeline gain calibration in (MJy/sr)/(e-/s).",
        "application": "Do not reapply to delivered Level 2 IMAGE values already expressed in MJy/sr.",
    },
    {
        "type": "epsf",
        "filename": "epsf_D[Detector]_spx_cal-epsf-v[Version]-[Processing Date].fits",
        "purpose": "Spatially sampled, oversampled effective point-spread functions.",
        "application": "Needed for calibrated PSF fitting; not applied by current source detector.",
    },
    {
        "type": "dark_current",
        "filename": "dark_D[Detector]_spx_cal-drk-v[Version]-[Processing Date].fits",
        "purpose": "Detector dark-current calibration.",
        "application": "Pipeline calibration; no second correction is applied to Level 2 products.",
    },
    {
        "type": "dichroic",
        "filename": "dichroic_D[Detector]_spx_base-[Processing Date].fits",
        "purpose": "Dichroic-affected pixel map.",
        "application": "Pipeline/quality context; not applied as a post-processing flux correction.",
    },
    {
        "type": "electronic_gain_factors",
        "filename": "gain_factors_spx_base-[Processing Date].yaml",
        "purpose": "Per-detector electronic gain provenance and factors.",
        "application": "Pipeline calibration; not applied to delivered Level 2 products.",
    },
    {
        "type": "nonlinearity_parameters",
        "filename": "nonlinear_pars_D[Detector]_spx_base-[Processing Date].fits",
        "purpose": "Detector nonlinearity calibration parameters.",
        "application": "Pipeline calibration; not applied again to delivered Level 2 products.",
    },
    {
        "type": "nonfunctional_pixels",
        "filename": "nonfunc_v[Version]_D[Detector]_spx_base-[Processing Date].fits",
        "purpose": "Map of permanently nonfunctional detector pixels.",
        "application": "Additional quality context; current operations use the product FLAGS extension.",
    },
    {
        "type": "read_noise_parameters",
        "filename": "readnoise_pars_D[Detector]_spx_base-[Processing Date].fits",
        "purpose": "Detector read-noise parameters.",
        "application": "Pipeline/noise-model context; current detection does not claim calibrated significance.",
    },
    {
        "type": "sip",
        "filename": "sip_D[Detector]_spx_cal-sip-v[Version]-[Processing Date].fits",
        "purpose": "Simple Imaging Polynomial distortion coefficients.",
        "application": "The SIP coefficients already present in an image header are used by its WCS; do not apply twice.",
    },
    {
        "type": "solid_angle_pixel_map",
        "filename": "solid_angle_pixel_map_D[Detector]_spx_cal-sapm-v[Version]-[Processing Date].fits",
        "purpose": "Per-pixel solid angle in square arcseconds.",
        "application": "Required for justified surface-brightness-to-per-pixel-flux conversion; no such conversion is performed.",
    },
    {
        "type": "spectral_channels",
        "filename": "spectral_channels_spx_cal-sch-v[Version]-[Processing Date].fits",
        "purpose": "Detector-pixel spectral-channel assignment map and channel summaries.",
        "application": "Not a substitute for calibrated per-pixel wavelength; All-Sky Cubes use their own SPECTRAL_CHANNELS table.",
    },
    {
        "type": "flux_corrections",
        "filename": "l3_flux_corrections_D[Detector]_spx_cal-flxc-v[Version]-[Processing Date].fits",
        "purpose": "Per-pixel factors for combining QR2 and QR3 data.",
        "application": "Only for the documented cross-release use case; never applied without verified releases.",
    },
)

OFFICIAL_DATA_PRODUCTS_URL = (
    "https://irsa.ipac.caltech.edu/spherex-archive-documentation/"
    "spherex-data-products/"
)
OFFICIAL_DATA_ACCESS_URL = (
    "https://irsa.ipac.caltech.edu/spherex-archive-documentation/"
    "spherex-data-access/"
)

_MEF_SIGNATURE = re.compile(
    r"^level2_.+D(?P<detector>[1-6])_spx_l2b-v(?P<version>[^-]+)-"
    r"(?P<processing_date>\d{4}-\d{3})\.fits$",
    re.IGNORECASE,
)
_SIP_COEFFICIENT = re.compile(r"^(?:A|B|AP|BP)_\d+_\d+$")
_CALIBRATION_FILENAME_PATTERNS = {
    "spectral_wcs": re.compile(r"^spectral_wcs_D[1-6]_spx_cal-s?wcs-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "absolute_gain_matrix": re.compile(r"^abs_gain_matrix_D[1-6]_spx_cal-agm-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "epsf": re.compile(r"^epsf_D[1-6]_spx_cal-epsf-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "dark_current": re.compile(r"^dark_D[1-6]_spx_cal-drk-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "dichroic": re.compile(r"^dichroic_D[1-6]_spx_base-\d{4}-\d{3}\.fits$", re.I),
    "electronic_gain_factors": re.compile(r"^gain_factors_spx_base-\d{4}-\d{3}\.yaml$", re.I),
    "nonlinearity_parameters": re.compile(r"^nonlinear_pars_D[1-6]_spx_base-\d{4}-\d{3}\.fits$", re.I),
    "nonfunctional_pixels": re.compile(r"^nonfunc(?:_v\d+)?_D[1-6]_spx_base-\d{4}-\d{3}\.fits$", re.I),
    "read_noise_parameters": re.compile(r"^readnoise_pars_D[1-6]_spx_base-\d{4}-\d{3}\.fits$", re.I),
    "sip": re.compile(r"^sip_D[1-6]_spx_cal-sip-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "solid_angle_pixel_map": re.compile(r"^solid_angle_pixel_map_D[1-6]_spx_cal-sapm-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "spectral_channels": re.compile(r"^spectral_channels_spx_cal-sch-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
    "flux_corrections": re.compile(r"^l3_flux_corrections_D[1-6]_spx_cal-flxc-v[^-]+-\d{4}-\d{3}\.fits$", re.I),
}


def _stable_id(*parts: str) -> str:
    canonical = "\0".join(parts).encode("utf-8")
    return "cal-" + hashlib.sha256(canonical).hexdigest()[:24]


def _header_detector(hdul: fits.HDUList) -> Optional[int]:
    values = set()
    for hdu in hdul:
        value = hdu.header.get("DETECTOR", hdu.header.get("DET_ID"))
        if value is not None:
            try:
                values.add(int(value))
            except (TypeError, ValueError):
                return None
    return next(iter(values)) if len(values) == 1 else None


def _has_sip(header: fits.Header) -> bool:
    return "A_ORDER" in header and "B_ORDER" in header and any(
        _SIP_COEFFICIENT.match(key) for key in header
    )


def _release_from_path(path: Path, root: Path) -> Optional[str]:
    releases = {
        part.upper()
        for part in path.relative_to(root).parts
        if part.lower() in {"dr1", "qr2", "qr3"}
    }
    return next(iter(releases)) if len(releases) == 1 else None


class CalibrationManager:
    """Central, evidence-backed calibration assessment for local FITS products."""

    def __init__(
        self,
        inventory: FitsInventory,
        calibration_root: Optional[Path] = None,
    ):
        self.inventory = inventory
        self.calibration_root = (
            Path(calibration_root).resolve()
            if calibration_root is not None
            else inventory.root
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _load_provenance(self) -> Dict[str, Dict[str, Any]]:
        manifest_path = self.calibration_root / "spectral-wcs-manifest.json"
        if not manifest_path.is_file():
            manifest_path = (
                self.calibration_root
                / "spectral_wcs"
                / "spectral-wcs-manifest.json"
            )
        if not manifest_path.is_file():
            return {}
        with manifest_path.open("r", encoding="utf-8") as file:
            manifest = json.load(file)
        products = manifest.get("products") if isinstance(manifest, dict) else None
        if not isinstance(products, list):
            raise ValueError("The Spectral WCS download manifest has no products list.")
        provenance = {}
        for product in products:
            if (
                not isinstance(product, dict)
                or not isinstance(product.get("filename"), str)
                or product["filename"] in provenance
            ):
                raise ValueError("The Spectral WCS download manifest has an invalid or duplicate filename.")
            provenance[product["filename"]] = product
        return provenance

    def catalog(self) -> Dict[str, Any]:
        manifest = self.inventory.load()
        components: List[Dict[str, Any]] = []
        standalone: List[Dict[str, Any]] = []
        entries_by_path = {
            entry.get("relative_path"): entry
            for entry in manifest.get("files", [])
        }
        provenance_by_filename = self._load_provenance()
        component_types = {
            "EPSF": "epsf_embedded",
            "WCS-WAVE": "spectral_wcs_visualization_table",
            "SPECTRAL_CHANNELS": "cube_spectral_channels",
        }
        for entry in manifest.get("files", []):
            for extension in entry.get("extensions", []):
                name = str(extension.get("name") or "").upper()
                if name not in component_types:
                    continue
                header = {
                    card.get("keyword"): card.get("value")
                    for card in extension.get("header_cards", [])
                }
                columns = [
                    header.get(f"TTYPE{index}")
                    for index in range(1, int(header.get("TFIELDS", 0)) + 1)
                    if header.get(f"TTYPE{index}")
                ]
                components.append({
                    "calibration_id": _stable_id(
                        str(entry.get("sha256") or ""),
                        str(extension.get("index")),
                        name,
                    ),
                    "type": component_types[name],
                    "name": name,
                    "source_file_id": entry.get("file_id"),
                    "source_relative_path": entry.get("relative_path"),
                    "source_sha256": entry.get("sha256"),
                    "hdu": extension.get("index"),
                    "dimensions": extension.get("shape"),
                    "columns": columns,
                    "integrity_status": "source_sha256_recorded",
                    "calibration_status": "partially_verified",
                    "note": (
                        "Embedded component; product release/provenance is not verified."
                    ),
                })
        for path in self.calibration_root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            product_type = next(
                (
                    name
                    for name, pattern in _CALIBRATION_FILENAME_PATTERNS.items()
                    if pattern.fullmatch(path.name)
                ),
                None,
            )
            if product_type is None:
                continue
            relative_path = path.relative_to(self.calibration_root).as_posix()
            entry = entries_by_path.get(relative_path)
            provenance = provenance_by_filename.get(path.name, {})
            try:
                if entry is not None:
                    self.inventory.get_path(entry)
                    sha256 = entry.get("sha256")
                    integrity_status = "sha256_verified_against_manifest"
                else:
                    sha256 = self._sha256_file(path)
                    expected_sha256 = provenance.get("sha256")
                    integrity_status = (
                        "sha256_verified_against_download_manifest"
                        if expected_sha256 and sha256 == expected_sha256
                        else "sha256_mismatch"
                        if expected_sha256
                        else "sha256_recorded"
                    )
            except (OSError, ValueError):
                sha256 = None
                integrity_status = "verification_failed"
            signature = re.search(
                r"-v(?P<version>[^-]+)-(?P<date>\d{4}-\d{3})\.fits$",
                path.name,
                re.IGNORECASE,
            )
            detector_match = re.search(r"_D(?P<detector>[1-6])_", path.name, re.IGNORECASE)
            product = {
                "calibration_id": _stable_id(relative_path, str(sha256 or "")),
                "type": product_type,
                "name": path.name,
                "relative_path": relative_path,
                "sha256": sha256,
                "format": path.suffix.lstrip(".").lower(),
                "detector": int(detector_match.group("detector")) if detector_match else None,
                "version": signature.group("version") if signature else None,
                "processing_date": signature.group("date") if signature else None,
                "release": (
                    provenance.get("release")
                    or _release_from_path(path, self.calibration_root)
                ),
                "source_urls": [OFFICIAL_DATA_PRODUCTS_URL, OFFICIAL_DATA_ACCESS_URL],
                "source_url": provenance.get("source_url"),
                "source_key": provenance.get("source_key"),
                "source_etag": provenance.get("source_etag"),
                "source_last_modified": provenance.get("source_last_modified"),
                "size_bytes": path.stat().st_size,
                "integrity_status": integrity_status,
                "calibration_status": "unverified",
                "association_method": "official filename pattern only; product-specific validation is still required",
            }
            if product_type == "spectral_wcs" and sha256:
                try:
                    with fits.open(path, mode="readonly", memmap=True, lazy_load_hdus=False) as hdul:
                        if "CWAVE" in hdul and hdul["CWAVE"].data is not None:
                            detector = int(detector_match.group("detector")) if detector_match else None
                            if detector is not None:
                                validation = self._inspect_spectral_wcs(
                                    path,
                                    detector,
                                    tuple(hdul["CWAVE"].data.shape),
                                    {
                                        "detector": detector,
                                        "version": signature.group("version") if signature else "",
                                        "processing_date": signature.group("date") if signature else "",
                                        "release": None,
                                    },
                                    self.calibration_root,
                                    hdul["WCS-WAVE"] if "WCS-WAVE" in hdul else None,
                                    provenance,
                                )
                                product.update({
                                    "calibration_status": validation["calibration_status"],
                                    "integrity_status": validation["integrity_status"],
                                    "dimensions": validation.get("dimensions"),
                                    "units": validation.get("units"),
                                    "wcs_wave_comparison": validation.get("wcs_wave_comparison"),
                                    "association_method": validation.get("association_method"),
                                    "validation_reason": validation["association_reason"],
                                })
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    product["validation_reason"] = (
                        f"Spectral WCS structure could not be validated: {type(exc).__name__}."
                    )
            standalone.append(product)
        available_types = {item["type"] for item in standalone}
        embedded_names = {
            item["name"] for item in components
        }
        registry = []
        for item in OFFICIAL_PRODUCTS:
            row = dict(item)
            if item["type"] in available_types:
                product_statuses = {
                    product.get("calibration_status")
                    for product in standalone
                    if product["type"] == item["type"]
                }
                row["local_availability"] = (
                    "standalone_product_verified"
                    if product_statuses == {"verified"}
                    else "standalone_product_partially_verified"
                    if product_statuses.issubset({"verified", "partially_verified"})
                    else "standalone_product_found_unverified"
                )
            elif item["type"] == "epsf" and "EPSF" in embedded_names:
                row["local_availability"] = "embedded_in_science_product"
            elif item["type"] == "spectral_wcs" and "WCS-WAVE" in embedded_names:
                row["local_availability"] = "visualization_table_only"
            else:
                row["local_availability"] = "not_found_locally"
            registry.append(row)
        return {
            "schema_version": 1,
            "registered_types": registry,
            "local_embedded_components": components,
            "standalone_calibration_products": standalone,
            "source_urls": [
                OFFICIAL_DATA_PRODUCTS_URL,
                OFFICIAL_DATA_ACCESS_URL,
                "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/spherex_spectral_calibrations.html",
            ],
        }

    def assess(self, entry: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
        path = source_path.resolve()
        if not path.is_relative_to(self.inventory.root) or not path.is_file():
            raise ValueError("The FITS path is outside the configured local inventory.")

        with fits.open(path, mode="readonly", memmap=True, lazy_load_hdus=False) as hdul:
            if "IMAGE" not in hdul or hdul["IMAGE"].data is None:
                raise ValueError("The inventory product has no readable IMAGE HDU.")
            image_hdu = hdul["IMAGE"]
            image = image_hdu.data
            detector = _header_detector(hdul)
            signature_match = _MEF_SIGNATURE.match(path.name)
            signature = (
                {
                    "detector": int(signature_match.group("detector")),
                    "version": signature_match.group("version"),
                    "processing_date": signature_match.group("processing_date"),
                    "release": entry.get("release"),
                }
                if signature_match
                else None
            )
            signature_warning = None
            if signature and detector is not None and signature["detector"] != detector:
                signature_warning = (
                    "Filename detector and FITS DETECTOR metadata disagree; "
                    "no external calibration will be associated."
                )
                signature = None

            spatial = self._assess_spatial_wcs(hdul, image_hdu)
            photometric = self._assess_photometric_units(hdul, image_hdu)
            embedded = self._embedded_components(
                hdul,
                str(entry.get("sha256") or ""),
                image.shape[-2:],
            )
            cube_spectral = (
                self._assess_cube_spectral_channels(hdul, image)
                if image.ndim == 3
                else None
            )
            spectral_wcs = (
                self._associate_spectral_wcs(
                    signature,
                    detector,
                    image.shape[-2:],
                    hdul["WCS-WAVE"] if "WCS-WAVE" in hdul else None,
                )
                if image.ndim == 2
                else {"status": "not_applicable", "reason": (
                    "Detector Spectral WCS products apply to Spectral Image MEFs; "
                    "the All-Sky Cube has its own channel table."
                ), "candidates": [], "selected_calibration_id": None}
            )
            has_variance = "VARIANCE" in hdul
            has_flags = "FLAGS" in hdul
            image_ndim = image.ndim
            is_mef = image_ndim == 2 and str(entry.get("product_type")) == "spectral_image_mef"
            is_cube = image_ndim == 3 and str(entry.get("product_type")) == "all_sky_spectral_cube"

        epsf_component = next(
            (item for item in embedded if item["type"] == "epsf_embedded"),
            None,
        )
        sip_in_header = spatial["sip_present"]
        spectral_table_component = next(
            (item for item in embedded if item["type"] == "cube_spectral_channels"),
            None,
        )
        calibration_states = {
            "spectral_wcs": {
                "status": spectral_wcs["status"],
                "reason": spectral_wcs["reason"],
                "calibration_ids": (
                    [spectral_wcs["selected_calibration_id"]]
                    if spectral_wcs["selected_calibration_id"]
                    else []
                ),
                "selected_product": spectral_wcs.get("selected_product"),
                "wcs_wave_comparison": spectral_wcs.get("wcs_wave_comparison"),
            },
            "absolute_gain_matrix": {
                "status": "not_applicable",
                "reason": (
                    "No gain correction is applied here: Level 2 IMAGE declares MJy/sr, "
                    "which the official product documentation identifies as calibrated surface brightness. "
                    "Release and pipeline history are not independently verified."
                ),
                "calibration_ids": [],
            },
            "epsf": {
                "status": (
                    "partially_verified" if epsf_component else "missing"
                ),
                "reason": (
                    "The MEF embeds a spatial ePSF table, but it is not consumed by the detector "
                    "and release/provenance is unverified."
                    if epsf_component
                    else "No embedded or locally associated ePSF product is available."
                ),
                "calibration_ids": (
                    [epsf_component["calibration_id"]] if epsf_component else []
                ),
            },
            "dark_current": {
                "status": "not_applicable",
                "reason": "Dark-current correction is upstream pipeline calibration, not reapplied to Level 2 data.",
                "calibration_ids": [],
            },
            "dichroic": {
                "status": "not_applicable",
                "reason": "No post-Level-2 dichroic correction is performed.",
                "calibration_ids": [],
            },
            "electronic_gain_factors": {
                "status": "not_applicable",
                "reason": "Electronic gain factors are an upstream pipeline calibration.",
                "calibration_ids": [],
            },
            "nonlinearity_parameters": {
                "status": "not_applicable",
                "reason": "Nonlinearity correction is not reapplied to delivered Level 2 values.",
                "calibration_ids": [],
            },
            "nonfunctional_pixels": {
                "status": "not_applicable" if has_flags else "missing",
                "reason": (
                    "Current quality handling uses the product FLAGS extension; no separate "
                    "nonfunctional-pixel map is applied."
                    if has_flags
                    else "Neither FLAGS nor a separate nonfunctional-pixel map is available."
                ),
                "calibration_ids": [],
            },
            "read_noise_parameters": {
                "status": "not_applicable",
                "reason": "The current detector does not estimate a read-noise-calibrated significance.",
                "calibration_ids": [],
            },
            "sip": {
                "status": "partially_verified" if sip_in_header else "unverified",
                "reason": (
                    "SIP coefficients are embedded in IMAGE and are used by the WCS transform; "
                    "no second distortion correction is applied."
                    if sip_in_header
                    else "No complete SIP coefficient set was identified in the IMAGE header."
                ),
                "calibration_ids": [],
            },
            "solid_angle_pixel_map": {
                "status": "missing",
                "reason": "No map is locally associated; surface brightness is not converted to Jy/pixel.",
                "calibration_ids": [],
            },
            "spectral_channels": {
                "status": (
                    cube_spectral["status"]
                    if cube_spectral
                    else "not_applicable"
                ),
                "reason": (
                    cube_spectral["reason"]
                    if cube_spectral
                    else "The MEF spectral axis is spatially varying and requires its Spectral WCS calibration maps."
                ),
                "calibration_ids": [],
            },
            "flux_corrections": {
                "status": "not_applicable",
                "reason": (
                    "No cross-release QR2/QR3 combination is being performed; release is not verified."
                ),
                "calibration_ids": [],
            },
        }
        # A cube's embedded channel table is a data component, not the detector-pixel
        # Spectral Channels calibration product.
        if cube_spectral and spectral_table_component:
            calibration_states["spectral_channels"]["calibration_ids"] = [
                spectral_table_component["calibration_id"]
            ]

        spectral_profile_status = (
            cube_spectral["status"]
            if is_cube and cube_spectral
            else spectral_wcs["status"]
            if is_mef
            else "not_applicable"
        )
        uncertainty_status = (
            "partially_verified"
            if has_variance and is_mef
            else "missing"
            if not has_variance
            else "unverified"
        )
        provenance_status = "partially_verified" if entry.get("sha256") else "unverified"
        warnings = list(entry.get("validation_warnings") or [])
        if not entry.get("release"):
            warnings.append("Product release is not identified in FITS metadata.")
        if signature_warning:
            warnings.append(signature_warning)
        if is_mef and spectral_wcs["status"] in ("missing", "unverified"):
            warnings.append(
                "MEF WCS-WAVE supports visualization; the official CWAVE/CBAND Spectral WCS "
                "calibration required for science-grade spectral analysis is not associated."
            )
        if is_mef and spectral_wcs["status"] == "partially_verified":
            warnings.append(
                "CWAVE/CBAND were associated by detector and pixel-grid agreement with the embedded WCS-WAVE; "
                "the local MEF release is not explicitly identified, so release provenance remains partial."
            )
        if is_cube and not has_variance:
            warnings.append("The All-Sky Cube has no VARIANCE extension; statistical significance is unavailable.")

        return {
            "file_id": entry["file_id"],
            "filename": entry["filename"],
            "relative_path": entry["relative_path"],
            "sha256": entry.get("sha256"),
            "release": entry.get("release"),
            "release_status": "verified" if entry.get("release") else "unverified",
            "product_signature": signature,
            "detector": detector,
            "calibrations": calibration_states,
            "embedded_components": embedded,
            "spatial_wcs_status": spatial["status"],
            "spatial_wcs": spatial,
            "spectral_wcs_status": spectral_profile_status,
            "photometric_status": photometric["status"],
            "photometric": photometric,
            "psf_status": calibration_states["epsf"]["status"],
            "uncertainty_status": uncertainty_status,
            "provenance_status": provenance_status,
            "overall_calibration_status": "partially_verified",
            "operation_authorizations": {
                "display_image": {
                    "authorized": bool(
                        entry.get("compatibility", {}).get("sky_preview", {}).get("compatible")
                    ),
                    "status": "partially_verified",
                    "reason": "Display uses the source FITS image and embedded spatial WCS; it does not apply additional calibration.",
                },
                "spectral_sample": {
                    "authorized": bool(
                        entry.get("compatibility", {}).get("spectral_profile", {}).get("compatible")
                    ),
                    "status": "partially_verified",
                    "reason": (
                        "MEF samples use associated CWAVE/CBAND maps when pixel-grid equivalence is validated; "
                        "otherwise they remain preliminary WCS-W samples. The cube uses its native channel table."
                    ),
                },
                "science_grade_mef_spectral_analysis": {
                    "authorized": bool(
                        is_mef
                        and spectral_wcs["status"] in ("verified", "partially_verified")
                        and spectral_wcs.get("selected_product")
                    ),
                    "status": spectral_wcs["status"],
                    "reason": spectral_wcs["reason"],
                },
                "photometry": {
                    "authorized": False,
                    "status": "blocked",
                    "reason": "No calibrated PSF-fitting/photometry implementation has been validated.",
                },
                "source_detection": {
                    "authorized": bool(
                        entry.get("compatibility", {}).get("source_detection", {}).get("compatible")
                    ),
                    "status": "partially_verified",
                    "reason": "Experimental single-image detection only; not calibrated photometry or significance.",
                },
                "surface_brightness_to_pixel_flux": {
                    "authorized": False,
                    "status": calibration_states["solid_angle_pixel_map"]["status"],
                    "reason": calibration_states["solid_angle_pixel_map"]["reason"],
                },
                "significance": {
                    "authorized": False,
                    "status": uncertainty_status,
                    "reason": "No validated statistical noise/significance model is implemented for this operation.",
                },
                "temporal_comparison": {
                    "authorized": False,
                    "status": "not_applicable",
                    "reason": "Temporal comparison is outside this calibration phase and remains disabled.",
                },
            },
            "calibration_product_ids_used": (
                [spectral_wcs["selected_calibration_id"]]
                if is_mef and spectral_wcs.get("selected_calibration_id")
                else [spectral_table_component["calibration_id"]]
                if is_cube and spectral_table_component
                else []
            ),
            "warnings": list(dict.fromkeys(warnings)),
            "no_corrections_applied": True,
            "calibration_policy": (
                "No upstream correction was reapplied. Level 2 IMAGE values are used as delivered; "
                "Spectral WCS is used only after pixel-grid correspondence is validated."
            ),
            "source_urls": [OFFICIAL_DATA_PRODUCTS_URL, OFFICIAL_DATA_ACCESS_URL],
        }

    @staticmethod
    def _assess_spatial_wcs(
        hdul: fits.HDUList,
        image_hdu: Any,
    ) -> Dict[str, Any]:
        data = image_hdu.data
        if data is None or data.ndim < 2:
            return {
                "status": "unverified",
                "sip_present": False,
                "round_trip_max_error_px": None,
                "absolute_astrometry_validated": False,
                "reason": "IMAGE has no two-dimensional celestial plane.",
            }
        header = image_hdu.header
        sip_present = _has_sip(header)
        wcs = WCS(header, fobj=hdul, relax=True).celestial
        if not wcs.has_celestial:
            return {
                "status": "unverified",
                "sip_present": sip_present,
                "round_trip_max_error_px": None,
                "absolute_astrometry_validated": False,
                "reason": "IMAGE has no interpretable celestial WCS.",
            }
        height, width = data.shape[-2:]
        pixels = np.asarray([
            [0.0, 0.0],
            [(width - 1.0) / 2.0, (height - 1.0) / 2.0],
            [width - 1.0, 0.0],
            [0.0, height - 1.0],
            [width - 1.0, height - 1.0],
        ])
        sky = wcs.all_pix2world(pixels, 0)
        recovered = wcs.all_world2pix(sky, 0)
        errors = np.linalg.norm(recovered - pixels, axis=1)
        max_error = float(np.max(errors))
        finite = bool(np.all(np.isfinite(sky)) and np.all(np.isfinite(errors)))
        return {
            "status": "partially_verified" if finite and max_error < 1e-3 else "unverified",
            "sip_present": sip_present,
            "round_trip_max_error_px": max_error if finite else None,
            "absolute_astrometry_validated": False,
            "reason": (
                "Internal pixel/sky round-trip only; no external astrometric reference was tested. "
                "Embedded SIP is used by Astropy and is not reapplied."
            ),
        }

    @staticmethod
    def _assess_photometric_units(
        hdul: fits.HDUList,
        image_hdu: Any,
    ) -> Dict[str, Any]:
        image_bunit = image_hdu.header.get("BUNIT")
        try:
            image_unit = u.Unit(image_bunit, format="fits")
        except (TypeError, ValueError):
            return {
                "status": "unverified",
                "image_unit": image_bunit,
                "variance_unit": None,
                "variance_matches_image": False,
                "corrections_applied": [],
                "reason": "IMAGE BUNIT is missing or cannot be parsed; no unit conversion was attempted.",
            }
        expected = u.MJy / u.sr
        if not image_unit.is_equivalent(expected):
            return {
                "status": "unverified",
                "image_unit": str(image_unit),
                "variance_unit": None,
                "variance_matches_image": False,
                "corrections_applied": [],
                "reason": "IMAGE is not in surface-brightness units compatible with MJy/sr.",
            }
        variance_unit_text = None
        variance_matches = False
        if "VARIANCE" in hdul and hdul["VARIANCE"].header.get("BUNIT"):
            variance_unit_text = str(hdul["VARIANCE"].header["BUNIT"])
            try:
                variance_unit = u.Unit(variance_unit_text, format="fits")
                variance_matches = variance_unit.is_equivalent(image_unit ** 2)
            except ValueError:
                variance_matches = False
        return {
            "status": "partially_verified",
            "image_unit": str(image_unit),
            "variance_unit": variance_unit_text,
            "variance_matches_image": variance_matches,
            "corrections_applied": [],
            "reason": (
                "BUNIT is compatible with MJy/sr and official Level 2 documentation describes IMAGE "
                "as calibrated surface brightness. The local release/pipeline history is not verified; "
                "no gain, flux, solid-angle, or other correction was applied."
            ),
        }

    @staticmethod
    def _embedded_components(
        hdul: fits.HDUList,
        source_sha256: str,
        image_shape: Tuple[int, ...],
    ) -> List[Dict[str, Any]]:
        components: List[Dict[str, Any]] = []
        for index, hdu in enumerate(hdul):
            name = str(hdu.header.get("EXTNAME", "")).upper()
            if name not in {"EPSF", "WCS-WAVE", "SPECTRAL_CHANNELS"}:
                continue
            columns = list(hdu.columns.names or []) if isinstance(
                hdu, (fits.BinTableHDU, fits.TableHDU)
            ) else []
            component: Dict[str, Any] = {
                "calibration_id": _stable_id(source_sha256, str(index), name),
                "type": {
                    "EPSF": "epsf_embedded",
                    "WCS-WAVE": "spectral_wcs_visualization_table",
                    "SPECTRAL_CHANNELS": "cube_spectral_channels",
                }[name],
                "name": name,
                "hdu": index,
                "dimensions": list(hdu.data.shape) if hdu.data is not None else None,
                "columns": columns,
                "detector": _header_detector(hdul),
                "calibration_status": "partially_verified",
            }
            if name == "EPSF":
                fields_required = {
                    "BINX", "BINY", "XCENTER", "YCENTER", "CWAVE", "CBAND", "EPSF",
                }
                rows = hdu.data
                detector = _header_detector(hdul)
                expected_grid = (
                    [11, 41]
                    if detector == 3
                    else [21, 21]
                    if detector in {1, 2, 4, 5, 6}
                    else None
                )
                epsf_values = (
                    np.asarray(rows["EPSF"])
                    if rows is not None and "EPSF" in columns
                    else np.empty((0,))
                )
                epsf_dimensions = (
                    list(epsf_values.shape[1:])
                    if epsf_values.ndim > 1
                    else None
                )
                centers_valid = False
                centers_in_bounds = False
                if rows is not None and {"XCENTER", "YCENTER"} <= set(columns):
                    centers = np.column_stack((rows["XCENTER"], rows["YCENTER"]))
                    centers_valid = bool(
                        np.all(np.isfinite(centers))
                        and np.unique(centers, axis=0).shape[0] == len(rows)
                    )
                    ny, nx = image_shape
                    centers_in_bounds = bool(
                        centers_valid
                        and np.all((0 <= centers[:, 0]) & (centers[:, 0] < nx))
                        and np.all((0 <= centers[:, 1]) & (centers[:, 1] < ny))
                    )
                bins_valid = False
                if rows is not None and {"BINX", "BINY"} <= set(columns) and expected_grid:
                    bins = np.column_stack((rows["BINX"], rows["BINY"]))
                    expected_bins = {
                        (x, y)
                        for y in range(expected_grid[1])
                        for x in range(expected_grid[0])
                    }
                    bins_valid = bool(
                        np.all(np.isfinite(bins))
                        and np.all(bins == np.floor(bins))
                        and {tuple(map(int, pair)) for pair in bins} == expected_bins
                    )
                wavelength_units_valid = True
                for field in ("CWAVE", "CBAND"):
                    if field not in columns or not hdu.columns[field].unit:
                        wavelength_units_valid = False
                        break
                    try:
                        wavelength_units_valid &= u.Unit(
                            hdu.columns[field].unit
                        ).is_equivalent(u.um)
                    except ValueError:
                        wavelength_units_valid = False
                expected_zone_count = (
                    expected_grid[0] * expected_grid[1]
                    if expected_grid
                    else None
                )
                structure_valid = bool(
                    rows is not None
                    and fields_required <= set(columns)
                    and expected_zone_count == len(rows)
                    and epsf_dimensions == [33, 33]
                    and centers_valid
                    and centers_in_bounds
                    and bins_valid
                    and wavelength_units_valid
                    and epsf_values.size > 0
                    and np.all(np.isfinite(epsf_values))
                )
                component["zone_count"] = len(rows) if rows is not None else 0
                component["expected_zone_grid"] = expected_grid
                component["expected_zone_count"] = expected_zone_count
                component["zone_centers_unique_and_finite"] = centers_valid
                component["zone_centers_within_image"] = centers_in_bounds
                component["zone_bin_grid_valid"] = bins_valid
                component["epsf_dimensions"] = epsf_dimensions
                component["epsf_values_finite"] = bool(
                    epsf_values.size > 0 and np.all(np.isfinite(epsf_values))
                )
                component["cwave_unit"] = hdu.columns["CWAVE"].unit if "CWAVE" in columns else None
                component["cband_unit"] = hdu.columns["CBAND"].unit if "CBAND" in columns else None
                component["calibration_status"] = (
                    "partially_verified" if structure_valid else "incompatible"
                )
                component["note"] = (
                    "CWAVE/CBAND here are values per ePSF zone, not the 2040x2040 "
                    "Spectral WCS calibration maps."
                )
            elif name == "WCS-WAVE":
                component["note"] = "Retained for visualization; not substituted for science CWAVE/CBAND maps."
            else:
                component["channel_count"] = len(hdu.data) if hdu.data is not None else 0
                component["units"] = {
                    column.name: column.unit
                    for column in hdu.columns
                    if column.name in {"WAVELENGTH", "WL_MIN", "WL_MAX", "BANDWIDTH"}
                }
                component["note"] = "Cube's native channel table; not a detector-pixel Spectral Channels map."
            components.append(component)
        return components

    @staticmethod
    def _assess_cube_spectral_channels(
        hdul: fits.HDUList,
        image: np.ndarray,
    ) -> Dict[str, Any]:
        if "SPECTRAL_CHANNELS" not in hdul:
            return {"status": "missing", "reason": "The cube has no SPECTRAL_CHANNELS table."}
        table_hdu = hdul["SPECTRAL_CHANNELS"]
        table = table_hdu.data
        names = set(table.names or []) if table is not None else set()
        if image.ndim != 3 or table is None or "WAVELENGTH" not in names:
            return {"status": "incompatible", "reason": "Cube axis or wavelength table structure is incompatible."}
        count = image.shape[0]
        if len(table) != count:
            return {
                "status": "incompatible",
                "reason": f"Channel rows ({len(table)}) do not match cube channel axis ({count}).",
            }
        wavelength_column = table_hdu.columns["WAVELENGTH"]
        if not wavelength_column.unit:
            return {"status": "unverified", "reason": "WAVELENGTH has no declared unit."}
        wavelength_unit = u.Unit(wavelength_column.unit)
        wavelengths = (
            np.asarray(table["WAVELENGTH"], dtype=np.float64) * wavelength_unit
        ).to_value(u.um, equivalencies=u.spectral())
        if not np.all(np.isfinite(wavelengths)) or np.any(wavelengths <= 0):
            return {"status": "incompatible", "reason": "Channel wavelengths contain invalid values."}

        bandwidths = None
        if "BANDWIDTH" in names:
            width_column = table_hdu.columns["BANDWIDTH"]
            if not width_column.unit:
                return {"status": "unverified", "reason": "BANDWIDTH has no declared unit."}
            width_unit = u.Unit(width_column.unit)
            bandwidths = (
                np.asarray(table["BANDWIDTH"], dtype=np.float64) * width_unit
            ).to_value(u.um, equivalencies=u.spectral())
            if not np.all(np.isfinite(bandwidths)) or np.any(bandwidths <= 0):
                return {"status": "incompatible", "reason": "Channel bandwidths contain invalid values."}

        wcs = WCS(hdul["IMAGE"].header, fobj=hdul, relax=True)
        spectral_axes = [
            i for i, physical_type in enumerate(wcs.world_axis_physical_types or [])
            if physical_type == "em.wl"
        ]
        if len(spectral_axes) != 1 or wcs.pixel_n_dim != 3:
            return {"status": "incompatible", "reason": "The cube WCS does not identify one spectral wavelength axis."}
        world_axis = spectral_axes[0]
        pixel_axes = np.flatnonzero(wcs.axis_correlation_matrix[world_axis])
        if pixel_axes.size != 1:
            return {"status": "incompatible", "reason": "The spectral WCS axis is not separable."}
        spectral_pixel_axis = int(pixel_axes[0])
        if wcs.pixel_n_dim - 1 - spectral_pixel_axis != 0:
            return {"status": "incompatible", "reason": "The WCS spectral axis does not map to the leading array axis."}
        spatial_pixel_axes = sorted({
            int(pixel_axis)
            for spatial_world_axis in (wcs.wcs.lng, wcs.wcs.lat)
            for pixel_axis in np.flatnonzero(wcs.axis_correlation_matrix[spatial_world_axis])
            if int(pixel_axis) != spectral_pixel_axis
        })
        if spatial_pixel_axes != [0, 1]:
            return {"status": "incompatible", "reason": "The celestial and spectral WCS axes are ambiguous."}
        pixels = np.zeros((count, 3), dtype=np.float64)
        pixels[:, spatial_pixel_axes[0]] = (image.shape[-1] - 1.0) / 2.0
        pixels[:, spatial_pixel_axes[1]] = (image.shape[-2] - 1.0) / 2.0
        pixels[:, spectral_pixel_axis] = np.arange(count, dtype=np.float64)
        wcs_values = wcs.all_pix2world(pixels, 0)[:, world_axis]
        wcs_unit = u.Unit(wcs.world_axis_units[world_axis])
        wcs_wavelengths = (wcs_values * wcs_unit).to_value(u.um, equivalencies=u.spectral())
        if not np.allclose(wcs_wavelengths, wavelengths, rtol=1e-5, atol=1e-7):
            return {"status": "incompatible", "reason": "SPECTRAL_CHANNELS wavelengths disagree with the cube WCS."}
        max_wavelength_delta_um = float(np.max(np.abs(wcs_wavelengths - wavelengths)))
        edge_bounds_available = False
        if ("WL_MIN" in names) != ("WL_MAX" in names):
            return {
                "status": "unverified",
                "reason": "Only one of WL_MIN/WL_MAX is present; channel edges cannot be checked.",
            }
        if "WL_MIN" in names and "WL_MAX" in names:
            lower_column = table_hdu.columns["WL_MIN"]
            upper_column = table_hdu.columns["WL_MAX"]
            if not lower_column.unit or not upper_column.unit:
                return {"status": "unverified", "reason": "WL_MIN/WL_MAX lack declared units."}
            lower = (
                np.asarray(table["WL_MIN"], dtype=np.float64)
                * u.Unit(lower_column.unit)
            ).to_value(u.um, equivalencies=u.spectral())
            upper = (
                np.asarray(table["WL_MAX"], dtype=np.float64)
                * u.Unit(upper_column.unit)
            ).to_value(u.um, equivalencies=u.spectral())
            if (
                not np.all(np.isfinite(lower))
                or not np.all(np.isfinite(upper))
                or np.any(lower >= upper)
                or np.any((wavelengths < lower) | (wavelengths > upper))
            ):
                return {
                    "status": "incompatible",
                    "reason": "Channel centers are not finite and bounded by ordered WL_MIN/WL_MAX edges.",
                }
            edge_bounds_available = True
        return {
            "status": "partially_verified",
            "reason": (
                "Native channel centers agree with the cube WCS; declared edge bounds and BANDWIDTH "
                "were validated independently without assuming BANDWIDTH equals WL_MAX - WL_MIN. "
                "Release/provenance and absolute calibration are not independently verified."
            ),
            "channel_count": int(count),
            "wavelength_unit": "um",
            "bandwidth_available": bandwidths is not None,
            "bandwidth_unit": "um" if bandwidths is not None else None,
            "edge_bounds_available": edge_bounds_available,
            "max_wcs_wavelength_delta_um": max_wavelength_delta_um,
        }

    def _associate_spectral_wcs(
        self,
        signature: Optional[Dict[str, Any]],
        detector: Optional[int],
        image_shape: Tuple[int, ...],
        source_wcs_wave: Optional[Any],
    ) -> Dict[str, Any]:
        if signature is None or detector is None:
            return {
                "status": "unverified",
                "reason": "Detector/version/processing-date identity is incomplete; no Spectral WCS association was attempted.",
                "candidates": [],
                "selected_calibration_id": None,
                "selected_product": None,
                "wcs_wave_comparison": None,
            }
        if signature["detector"] != detector:
            return {
                "status": "incompatible",
                "reason": "MEF filename and DETECTOR header disagree.",
                "candidates": [],
                "selected_calibration_id": None,
                "selected_product": None,
                "wcs_wave_comparison": None,
            }
        paths = sorted(
            path
            for path in self.calibration_root.rglob("spectral_wcs_D*_spx_cal-swcs-*.fits")
            if path.is_file()
            and not path.is_symlink()
            and _CALIBRATION_FILENAME_PATTERNS["spectral_wcs"].fullmatch(path.name)
            and re.search(r"_D([1-6])_", path.name, re.IGNORECASE)
            and int(re.search(r"_D([1-6])_", path.name, re.IGNORECASE).group(1)) == detector
        )
        provenance_by_filename = self._load_provenance()
        candidates = [
            self._inspect_spectral_wcs(
                path,
                detector,
                image_shape,
                signature,
                self.calibration_root,
                source_wcs_wave,
                provenance_by_filename.get(path.name, {}),
            )
            for path in paths
        ]
        compatible = [
            item for item in candidates
            if item["calibration_status"] in ("verified", "partially_verified")
        ]
        if len(compatible) > 1:
            return {
                "status": "unverified",
                "reason": "Multiple structurally compatible local calibration files match; association is ambiguous.",
                "candidates": candidates,
                "selected_calibration_id": None,
                "selected_product": None,
                "wcs_wave_comparison": None,
            }
        if len(compatible) == 1:
            selected = compatible[0]
            return {
                "status": selected["calibration_status"],
                "reason": selected["association_reason"],
                "candidates": candidates,
                "selected_calibration_id": selected["calibration_id"],
                "selected_product": selected,
                "wcs_wave_comparison": selected.get("wcs_wave_comparison"),
            }
        if candidates:
            return {
                "status": (
                    "incompatible"
                    if any(item["calibration_status"] == "incompatible" for item in candidates)
                    else "unverified"
                ),
                "reason": "A filename candidate exists but its detector, arrays, units, or integrity do not verify.",
                "candidates": candidates,
                "selected_calibration_id": None,
                "selected_product": None,
                "wcs_wave_comparison": None,
            }
        return {
            "status": "missing",
            "reason": (
                f"No official local Spectral WCS product for detector {detector} was found. "
                "Calibration version/date are not assumed to be the same namespace as the L2B version/date."
            ),
            "candidates": [],
            "selected_calibration_id": None,
            "selected_product": None,
            "wcs_wave_comparison": None,
        }

    def _inspect_spectral_wcs(
        self,
        path: Path,
        expected_detector: int,
        image_shape: Tuple[int, ...],
        signature: Dict[str, Any],
        inventory_root: Path,
        source_wcs_wave: Optional[Any],
        provenance: Dict[str, Any],
    ) -> Dict[str, Any]:
        relative_path = path.relative_to(inventory_root).as_posix()
        try:
            sha256 = self._sha256_file(path)
        except OSError as exc:
            return {
                "calibration_id": _stable_id(relative_path, ""),
                "filename": path.name,
                "relative_path": relative_path,
                "calibration_status": "unverified",
                "integrity_status": "verification_failed",
                "association_reason": f"Calibration file could not be hashed: {type(exc).__name__}.",
            }
        calibration_id = _stable_id(relative_path, sha256)
        expected_sha256 = provenance.get("sha256")
        integrity_status = (
            "sha256_verified_against_download_manifest"
            if expected_sha256 and sha256 == expected_sha256
            else "sha256_mismatch"
            if expected_sha256
            else "sha256_recorded_without_download_manifest"
        )
        base = {
            "calibration_id": calibration_id,
            "filename": path.name,
            "relative_path": relative_path,
            "sha256": sha256,
            "type": "spectral_wcs",
            "detector": expected_detector,
            "calibration_version": provenance.get("calibration_version"),
            "calibration_processing_date": provenance.get("processing_date"),
            "release": provenance.get("release"),
            "source_url": provenance.get("source_url"),
            "source_key": provenance.get("source_key"),
            "source_etag": provenance.get("source_etag"),
            "size_bytes": path.stat().st_size,
            "integrity_status": integrity_status,
        }

        def result(status: str, reason: str, **details: Any) -> Dict[str, Any]:
            return {
                **base,
                "calibration_status": status,
                "association_reason": reason,
                **details,
            }

        if expected_sha256 and sha256 != expected_sha256:
            return result(
                "incompatible",
                "Downloaded file SHA-256 does not match the recorded official product manifest.",
            )
        if provenance.get("size_bytes") and path.stat().st_size != provenance["size_bytes"]:
            return result(
                "incompatible",
                "Downloaded file size does not match the recorded official product manifest.",
            )

        table_tolerance_um = 1e-5
        try:
            with fits.open(path, mode="readonly", memmap=True, lazy_load_hdus=False) as hdul:
                if "CWAVE" not in hdul or "CBAND" not in hdul:
                    return result("incompatible", "Required CWAVE and/or CBAND extension is absent.")
                cwave = hdul["CWAVE"]
                cband = hdul["CBAND"]
                if (
                    cwave.data is None
                    or cband.data is None
                    or cwave.data.ndim != 2
                    or cband.data.ndim != 2
                    or tuple(cwave.data.shape) != tuple(cband.data.shape)
                ):
                    return result(
                        "incompatible",
                        "CWAVE and CBAND must be two-dimensional maps with identical dimensions.",
                    )
                file_detector = _header_detector(hdul)
                filename_match = re.search(
                    r"_D(?P<detector>[1-6])_spx_cal-swcs-v(?P<version>[^-]+)-"
                    r"(?P<date>\d{4}-\d{3})\.fits$",
                    path.name,
                    re.IGNORECASE,
                )
                if not filename_match:
                    return result("incompatible", "Calibration filename is not an official Spectral WCS pattern.")
                filename_detector = int(filename_match.group("detector"))
                if filename_detector != expected_detector or (
                    file_detector is not None and file_detector != expected_detector
                ):
                    return result(
                        "incompatible",
                        "Calibration detector in the official filename or FITS metadata does not match the MEF.",
                    )
                calibration_release = (
                    provenance.get("release")
                    or _release_from_path(path, inventory_root)
                )
                source_release = signature.get("release")
                if (
                    source_release
                    and calibration_release
                    and source_release != calibration_release
                ):
                    return result("incompatible", "Calibration and source products are in different releases.")
                units = []
                for hdu in (cwave, cband):
                    unit_text = hdu.header.get("BUNIT")
                    if not unit_text:
                        return result(
                            "unverified",
                            f"{hdu.name} has no BUNIT; unit cannot be assumed for this file.",
                        )
                    unit = u.Unit(unit_text, format="fits")
                    if not unit.is_equivalent(u.um):
                        return result(
                            "incompatible",
                            f"{hdu.name} unit {unit_text!r} is not a wavelength unit.",
                        )
                    units.append(str(unit))
                valid_data = all(
                    np.all(np.isfinite(hdu.data)) and np.all(np.asarray(hdu.data) > 0)
                    for hdu in (cwave, cband)
                )
                if not valid_data:
                    return result("incompatible", "CWAVE/CBAND contain non-finite or non-positive values.")
                if source_wcs_wave is None or source_wcs_wave.data is None:
                    return result(
                        "unverified",
                        "The source MEF has no readable WCS-WAVE table to establish pixel-grid correspondence.",
                    )
                source_comparison = self._compare_wcs_wave_to_maps(
                    source_wcs_wave,
                    cwave.data,
                    cband.data,
                    table_tolerance_um,
                )
                if not source_comparison["compatible"]:
                    return result(
                        "incompatible",
                        "Source WCS-WAVE control points do not agree with the official CWAVE/CBAND pixel maps.",
                        dimensions={
                            "source_image": list(image_shape),
                            "calibration_maps": list(cwave.data.shape),
                        },
                        wcs_wave_comparison=source_comparison,
                    )
                if "WCS-WAVE" not in hdul or hdul["WCS-WAVE"].data is None:
                    return result(
                        "unverified",
                        "Official Spectral WCS file lacks its expected WCS-WAVE control table.",
                    )
                official_comparison = self._compare_wcs_wave_to_maps(
                    hdul["WCS-WAVE"],
                    cwave.data,
                    cband.data,
                    table_tolerance_um,
                )
                if not official_comparison["compatible"]:
                    return result(
                        "incompatible",
                        "The calibration product's own WCS-WAVE controls disagree with CWAVE/CBAND.",
                        dimensions={
                            "source_image": list(image_shape),
                            "calibration_maps": list(cwave.data.shape),
                        },
                        wcs_wave_comparison=source_comparison,
                    )
                checksums = [
                    hdu.verify_checksum() if "CHECKSUM" in hdu.header else None
                    for hdu in hdul
                ]
                datasums = [
                    hdu.verify_datasum() if "DATASUM" in hdu.header else None
                    for hdu in hdul
                ]
                if any(value == 0 for value in checksums + datasums):
                    return result(
                        "incompatible",
                        "A present FITS CHECKSUM or DATASUM failed verification.",
                        integrity_status="fits_checksum_invalid",
                    )
                checksums_present = all(
                    "CHECKSUM" in hdu.header and "DATASUM" in hdu.header
                    for hdu in hdul
                )
                status = (
                    "verified"
                    if checksums_present and source_release and source_release == calibration_release
                    else "partially_verified"
                )
                integrity_status = (
                    "fits_checksum_valid"
                    if checksums_present
                    else integrity_status
                )
                return result(
                    status,
                    (
                        "Official detector-specific CWAVE/CBAND maps match the source MEF WCS-WAVE "
                        "at every declared control pixel; units, finite positive values, and integrity were checked."
                    ),
                    version=signature["version"],
                    processing_date=signature["processing_date"],
                    dimensions={
                        "source_image": list(image_shape),
                        "calibration_maps": list(cwave.data.shape),
                    },
                    units={"CWAVE": units[0], "CBAND": units[1], "WCS-WAVE": "um by official product definition"},
                    calibration_product_metadata={
                        "version": filename_match.group("version"),
                        "processing_date": filename_match.group("date"),
                        "release": calibration_release,
                    },
                    wcs_wave_comparison={
                        "compatible": True,
                        "source_mef": source_comparison,
                        "calibration_product": official_comparison,
                        "tolerance_um": table_tolerance_um,
                        "tolerance_rationale": "Direct table control-point comparisons only; 0.01 nm covers FITS float representation and is much tighter than display-grid interpolation accuracy.",
                    },
                    fits_checksums_present=checksums_present,
                    association_method="detector-specific official product plus exact 1-based WCS-WAVE control-pixel comparison against CWAVE/CBAND maps",
                )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return result(
                "unverified",
                f"Calibration FITS could not be validated: {type(exc).__name__}.",
            )

    @staticmethod
    def _compare_wcs_wave_to_maps(
        wcs_wave_hdu: Any,
        cwave: np.ndarray,
        cband: np.ndarray,
        tolerance_um: float,
    ) -> Dict[str, Any]:
        data = wcs_wave_hdu.data
        columns = set(data.names or []) if data is not None else set()
        required = {"X", "Y", "VALUES"}
        if data is None or len(data) != 1 or not required.issubset(columns):
            return {
                "compatible": False,
                "reason": "WCS-WAVE must contain one row with X, Y, and VALUES columns.",
            }
        x_values = np.asarray(data["X"][0], dtype=np.float64)
        y_values = np.asarray(data["Y"][0], dtype=np.float64)
        values = np.asarray(data["VALUES"][0], dtype=np.float64)
        if (
            x_values.ndim != 1
            or y_values.ndim != 1
            or values.shape != (len(y_values), len(x_values), 2)
            or not np.all(np.isfinite(x_values))
            or not np.all(np.isfinite(y_values))
            or not np.all(x_values == np.floor(x_values))
            or not np.all(y_values == np.floor(y_values))
        ):
            return {
                "compatible": False,
                "reason": "WCS-WAVE control coordinates or VALUES dimensions are invalid.",
            }
        x_indices = x_values.astype(np.int64) - 1
        y_indices = y_values.astype(np.int64) - 1
        if (
            len(np.unique(x_indices)) != len(x_indices)
            or len(np.unique(y_indices)) != len(y_indices)
            or np.any(x_indices < 0)
            or np.any(y_indices < 0)
            or np.any(x_indices >= cwave.shape[1])
            or np.any(y_indices >= cwave.shape[0])
        ):
            return {
                "compatible": False,
                "reason": "WCS-WAVE control coordinates fall outside the calibration map pixel grid.",
            }
        mapped = np.stack(
            (
                cwave[np.ix_(y_indices, x_indices)],
                cband[np.ix_(y_indices, x_indices)],
            ),
            axis=-1,
        )
        differences = np.abs(values - mapped)
        max_deltas = np.max(differences, axis=(0, 1))
        return {
            "compatible": bool(np.all(max_deltas <= tolerance_um)),
            "control_points": int(len(x_indices) * len(y_indices)),
            "coordinate_origin": "FITS 1-based; map index is (Y-1, X-1), verified by direct CWAVE/CBAND comparison",
            "wavelength_unit": "um by official product definition",
            "max_abs_delta_um": {
                "CWAVE": float(max_deltas[0]),
                "CBAND": float(max_deltas[1]),
            },
            "tolerance_um": tolerance_um,
            "reason": (
                "All tabulated control values agree within the stated floating-point tolerance."
                if np.all(max_deltas <= tolerance_um)
                else "At least one tabulated control value differs from the direct pixel-map lookup."
            ),
        }
