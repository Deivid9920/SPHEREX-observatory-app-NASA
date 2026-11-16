from pathlib import Path

from astropy.table import Table
import pytest
import requests

from app.services.irsa_client import IRSAClient, IRSAQueryError


class FakeTAPService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def run_sync(self, query: str, *, maxrec: int):
        self.queries.append(query)
        if "TAP_SCHEMA.columns" in query:
            return Table(
                rows=[
                    ("obs_id", None),
                    ("obs_collection", None),
                    ("s_ra", "deg"),
                    ("s_dec", "deg"),
                    ("t_min", "d"),
                    ("t_max", "d"),
                    ("em_min", "m"),
                    ("em_max", "m"),
                    ("access_url", None),
                    ("dataproduct_type", None),
                ],
                names=("column_name", "unit"),
            )
        return Table(
            rows=[(
                "o-1", "SPHEREx", 60000.0, 60001.0, 10.0, -2.0, 1e-6, 2e-6,
                "https://example.test/a", "cube",
            )],
            names=(
                "obs_id", "obs_collection", "t_min", "t_max", "s_ra", "s_dec", "em_min", "em_max",
                "access_url", "dataproduct_type",
            ),
        )


def test_irsa_tap_schema_is_checked_and_observation_results_are_normalized(
    tmp_path: Path,
) -> None:
    client = IRSAClient(str(tmp_path / "raw"))
    service = FakeTAPService()
    client.tap_service = service

    observations = client.query_spherex_observations(ra=10.0, dec=-2.0)

    assert len(service.queries) == 2
    assert "FROM spherex.obscore AS o" in service.queries[-1]
    assert observations == [{
        "obs_id": "o-1",
        "collection": "SPHEREx",
        "t_min": 60000.0,
        "t_max": 60001.0,
        "wavelength_min_um": 1.0,
        "wavelength_max_um": 2.0,
        "product_type": "cube",
        "base_uri": "https://example.test/a",
    }]


def test_irsa_tap_timeout_is_reported_without_synthetic_fallback(
    tmp_path: Path,
) -> None:
    client = IRSAClient(str(tmp_path / "raw"), tap_timeout_seconds=0.1)

    class TimeoutTAPService:
        def run_sync(self, query: str, *, maxrec: int):
            raise requests.Timeout("test timeout")

    client.tap_service = TimeoutTAPService()

    with pytest.raises(IRSAQueryError, match="timeout de 0.1 segundos"):
        client.query_spherex_observations(ra=10.0, dec=-2.0)


def test_irsa_query_rejects_out_of_range_coordinates_before_network(
    tmp_path: Path,
) -> None:
    client = IRSAClient(str(tmp_path / "raw"))

    with pytest.raises(ValueError, match="fuera del rango"):
        client.query_spherex_observations(ra=361.0, dec=0.0)
