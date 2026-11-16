from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from app.core.config import BASE_DIR


REAL_DATA_ROOT = BASE_DIR / "app" / "data" / "raw" / "spherex"


def test_real_image_hdus_round_trip_celestial_wcs_when_local_data_is_available() -> None:
    files = sorted(REAL_DATA_ROOT.rglob("*.fits"))
    if not files:
        pytest.skip("Local SPHEREx FITS are not installed; fixture tests cover CI.")

    image_count = 0
    mef_count = 0
    cube_count = 0
    for path in files:
        with fits.open(path, mode="readonly", memmap=True) as hdus:
            image_hdu = hdus["IMAGE"]
            data = image_hdu.data
            assert data is not None
            wcs = WCS(image_hdu.header, fobj=hdus, relax=True)
            celestial = wcs.celestial
            assert celestial.has_celestial
            image_count += 1
            if data.ndim == 2:
                mef_count += 1
                height, width = data.shape
            else:
                assert data.ndim == 3
                cube_count += 1
                height, width = data.shape[-2:]

            pixels = np.array([
                [0.0, 0.0],
                [(width - 1.0) / 2.0, (height - 1.0) / 2.0],
                [width - 1.0, 0.0],
                [0.0, height - 1.0],
                [width - 1.0, height - 1.0],
            ])
            sky = celestial.all_pix2world(pixels, 0)
            recovered = celestial.all_world2pix(sky, 0)
            errors = np.linalg.norm(recovered - pixels, axis=1)
            assert np.all(np.isfinite(sky)), path.name
            assert np.all(np.isfinite(errors)), path.name
            assert float(np.max(errors)) < 1e-3, path.name

    assert image_count == len(files)
    assert mef_count == 9
    assert cube_count == 1
