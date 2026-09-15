from __future__ import annotations

import pytest

from opportunities_abroad.models import Job
from opportunities_abroad.prefs import prefs_from_dict


@pytest.fixture
def sample_prefs():
    return prefs_from_dict(
        {
            "include_keywords": ["python", "software engineer", "backend", "django"],
            "exclude_keywords": ["intern", "unpaid"],
            "locations": {
                "countries": ["Netherlands", "Germany", "EU", "Europe"],
                "cities": ["Amsterdam", "Berlin"],
            },
            "work_mode": {"remote": True, "hybrid": True, "onsite": True, "remote_only": False},
            "remote": {
                "accept_locations": ["Worldwide", "Anywhere", "Remote", "Europe", "EU", "India"],
                "reject_locations": ["USA only", "US only", "United States only"],
            },
            "visa_keywords": ["visa", "sponsorship", "relocation", "blue card"],
            "digest": {"max_jobs": 25},
        }
    )


def make_job(**overrides) -> Job:
    data = {
        "source": "test",
        "source_id": "1",
        "title": "Python Software Engineer",
        "company": "Acme",
        "url": "https://example.com/jobs/1",
        "location": "Amsterdam, Netherlands",
        "description": "Backend role with visa sponsorship.",
        "tags": ["python"],
        "remote": False,
    }
    data.update(overrides)
    return Job(**data)
