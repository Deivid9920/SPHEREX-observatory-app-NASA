import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from app.services.astrometry import (
    ASTROMETRY_BLOCKED,
    ASTROMETRY_UNVALIDATED,
    SIP_CONFIRMED_ACTIVE,
    SIP_CONVENTION_INCONSISTENT,
    SIP_CONFIRMED_INACTIVE,
    WCS_STRUCTURALLY_VALID,
    WCS_WITH_SIP_INCONSISTENCY,
    AstrometryBlockedError,
    CoordinateOutsideImageError,
    InvalidSkyCoordinateError,
    build_spatial_wcs,
    pixel_to_sky,
    sky_to_pixel,
)


def _header(*, sip: bool = False, sip_suffix: bool = True, finast=None) -> fits.Header:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [6.0, 6.0]
    wcs.wcs.crval = [120.0, 10.0]
    wcs.wcs.cdelt = [-0.001, 0.001]
    wcs.wcs.ctype = [
        "RA---TAN-SIP" if sip and sip_suffix else "RA---TAN",
        "DEC--TAN-SIP" if sip and sip_suffix else "DEC--TAN",
    ]
    header = wcs.to_header(relax=True)
    if sip:
        header["A_ORDER"] = 2
        header["B_ORDER"] = 2
        header["A_2_0"] = 1e-8
        header["B_0_2"] = -1e-8
    if finast is not None:
        header["FINAST"] = finast
    return header


def test_spatial_wcs_applies_declared_sip_and_marks_no_independent_validation() -> None:
    context = build_spatial_wcs(_header(sip=True, finast=0))
    expected = context.wcs.pixel_to_world(4.0, 7.0)

    selected = sky_to_pixel(context, expected.ra.deg, expected.dec.deg, (12, 12))
    recovered = pixel_to_sky(
        context, selected.x_index, selected.y_index, (12, 12)
    )

    assert context.sip_status == SIP_CONFIRMED_ACTIVE
    assert context.structural_status == WCS_STRUCTURALLY_VALID
    assert context.astrometry_status == ASTROMETRY_UNVALIDATED
    assert (selected.x_index, selected.y_index) == (4, 7)
    assert np.isfinite(recovered.ra.deg)
    assert any("FINAST=0" in item for item in context.warnings)


def test_missing_sip_is_not_reported_as_astrometrically_validated() -> None:
    context = build_spatial_wcs(_header(finast=None))

    assert context.sip_status == SIP_CONFIRMED_INACTIVE
    assert context.astrometry_status == ASTROMETRY_UNVALIDATED
    assert any("FINAST no está presente" in item for item in context.warnings)


def test_sip_without_ctype_suffix_blocks_celestial_transform() -> None:
    context = build_spatial_wcs(_header(sip=True, sip_suffix=False, finast=0))

    assert context.sip_status == SIP_CONVENTION_INCONSISTENT
    assert context.structural_status == WCS_WITH_SIP_INCONSISTENCY
    assert context.astrometry_status == ASTROMETRY_BLOCKED
    with pytest.raises(AstrometryBlockedError):
        sky_to_pixel(context, 120.0, 10.0, (12, 12))


@pytest.mark.parametrize(
    ("ra", "dec"),
    [(float("nan"), 10.0), (float("inf"), 10.0), (10.0, float("-inf")), (10.0, 91.0)],
)
def test_invalid_sky_coordinates_are_rejected(ra: float, dec: float) -> None:
    context = build_spatial_wcs(_header())

    with pytest.raises(InvalidSkyCoordinateError):
        sky_to_pixel(context, ra, dec, (12, 12))


def test_valid_coordinate_outside_image_is_not_clamped_to_an_edge() -> None:
    context = build_spatial_wcs(_header())

    with pytest.raises(CoordinateOutsideImageError):
        sky_to_pixel(context, 121.0, 10.0, (12, 12))

    with pytest.raises(CoordinateOutsideImageError):
        sky_to_pixel(context, 10.0, 10.0, (12, 12))


def test_declared_spatial_wcs_round_trip_uses_zero_based_pixel_centers() -> None:
    context = build_spatial_wcs(_header(sip=True))
    input_sky = context.wcs.pixel_to_world(2.0, 8.0)
    selected = sky_to_pixel(context, input_sky.ra.deg, input_sky.dec.deg, (12, 12))
    output_sky = pixel_to_sky(
        context, selected.x_index, selected.y_index, (12, 12)
    )

    assert np.hypot(selected.x_pixel - 2.0, selected.y_pixel - 8.0) < 1e-3
    assert SkyCoord(input_sky).separation(output_sky).arcsec < 1e-3
