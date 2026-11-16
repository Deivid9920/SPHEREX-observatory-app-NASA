import asyncio

from app.core.config import settings
from app.main import health_check


def test_health_reports_application_version_without_claiming_data_release() -> None:
    response = asyncio.run(health_check())

    assert response == {"status": "online", "version": settings.VERSION}
