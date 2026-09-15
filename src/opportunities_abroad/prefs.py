from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Prefs:
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    accept_remote: bool = True
    accept_hybrid: bool = True
    accept_onsite: bool = True
    remote_only: bool = False
    remote_accept_locations: list[str] = field(default_factory=list)
    remote_reject_locations: list[str] = field(default_factory=list)
    visa_keywords: list[str] = field(default_factory=list)
    max_jobs: int = 25
    source_enabled: dict[str, bool] = field(default_factory=dict)
    adzuna_countries: list[str] = field(default_factory=list)
    adzuna_what: str = "software engineer"
    adzuna_results_per_page: int = 20
    adzuna_max_pages: int = 1
    arbeitnow_max_pages: int = 2
    arbeitnow_visa_sponsorship: bool | None = None
    http_timeout_seconds: float = 30.0

    def source_is_enabled(self, name: str) -> bool:
        return self.source_enabled.get(name, True)


def load_prefs(path: str | Path) -> Prefs:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Preferences file not found: {path}. "
            "Copy prefs.example.yaml to prefs.yaml or pass --prefs."
        )
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
    else:
        data = yaml.safe_load(raw_text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Preferences in {path} must be a mapping, not {type(data).__name__}")
    return prefs_from_dict(data)


def prefs_from_dict(data: dict[str, Any]) -> Prefs:
    locations = data.get("locations") or {}
    work_mode = data.get("work_mode") or {}
    remote = data.get("remote") or {}
    digest = data.get("digest") or {}
    sources = data.get("sources") or {}
    adzuna = data.get("adzuna") or {}
    arbeitnow = data.get("arbeitnow") or {}
    http = data.get("http") or {}

    visa = arbeitnow.get("visa_sponsorship", None)
    if visa is not None:
        visa = bool(visa)

    return Prefs(
        include_keywords=_str_list(data.get("include_keywords")),
        exclude_keywords=_str_list(data.get("exclude_keywords")),
        countries=_str_list(locations.get("countries")),
        cities=_str_list(locations.get("cities")),
        accept_remote=bool(work_mode.get("remote", True)),
        accept_hybrid=bool(work_mode.get("hybrid", True)),
        accept_onsite=bool(work_mode.get("onsite", True)),
        remote_only=bool(work_mode.get("remote_only", False)),
        remote_accept_locations=_str_list(remote.get("accept_locations")),
        remote_reject_locations=_str_list(remote.get("reject_locations")),
        visa_keywords=_str_list(data.get("visa_keywords")),
        max_jobs=int(digest.get("max_jobs", 25)),
        source_enabled={str(k): bool(v) for k, v in sources.items()},
        adzuna_countries=[c.lower() for c in _str_list(adzuna.get("countries"))],
        adzuna_what=str(adzuna.get("what") or "software engineer"),
        adzuna_results_per_page=int(adzuna.get("results_per_page", 20)),
        adzuna_max_pages=int(adzuna.get("max_pages", 1)),
        arbeitnow_max_pages=int(arbeitnow.get("max_pages", 2)),
        arbeitnow_visa_sponsorship=visa,
        http_timeout_seconds=float(http.get("timeout_seconds", 30)),
    )


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]
