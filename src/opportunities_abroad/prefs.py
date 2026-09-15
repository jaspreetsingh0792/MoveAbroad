from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Ranking weights applied when prefs do not override them. These reproduce the
# original hardcoded scoring, so an unconfigured prefs file ranks as it always did.
DEFAULT_SCORE_WEIGHTS: dict[str, int] = {
    "title_hit": 8,
    "keyword_hit": 3,
    "remote": 4,
    "visa_hit": 5,
}
DEFAULT_LOCATION_WEIGHTS: dict[str, int] = {
    "netherlands": 6,
    "germany": 3,
    "europe": 3,
}
ATS_NAMES = ("greenhouse", "lever", "ashby")


@dataclass(slots=True)
class Prefs:
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    title_include: list[str] = field(default_factory=list)
    title_exclude: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    accept_remote: bool = True
    accept_hybrid: bool = True
    accept_onsite: bool = True
    remote_only: bool = False
    remote_accept_locations: list[str] = field(default_factory=list)
    remote_reject_locations: list[str] = field(default_factory=list)
    visa_keywords: list[str] = field(default_factory=list)
    visa_require: bool = False
    visa_classifier: bool = False
    visa_classifier_model: str = "claude-sonnet-4-6"
    max_age_days: int = 14
    max_jobs: int = 25
    save_html_to: str | None = None
    score_weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SCORE_WEIGHTS))
    location_weights: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_LOCATION_WEIGHTS)
    )
    source_enabled: dict[str, bool] = field(default_factory=dict)
    ats_boards: dict[str, list[str]] = field(default_factory=dict)
    adzuna_countries: list[str] = field(default_factory=list)
    adzuna_what: str = "software engineer"
    adzuna_results_per_page: int = 20
    adzuna_max_pages: int = 1
    arbeitnow_max_pages: int = 2
    arbeitnow_visa_sponsorship: bool | None = None
    http_timeout_seconds: float = 30.0

    def source_is_enabled(self, name: str) -> bool:
        return self.source_enabled.get(name, True)

    def boards_for(self, ats: str) -> list[str]:
        return self.ats_boards.get(ats, [])

    def weight(self, name: str) -> int:
        return int(self.score_weights.get(name, DEFAULT_SCORE_WEIGHTS.get(name, 0)))


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
    ats_boards = data.get("ats_boards") or {}
    adzuna = data.get("adzuna") or {}
    arbeitnow = data.get("arbeitnow") or {}
    visa = data.get("visa") or {}
    http = data.get("http") or {}

    arbeitnow_visa = arbeitnow.get("visa_sponsorship", None)
    if arbeitnow_visa is not None:
        arbeitnow_visa = bool(arbeitnow_visa)

    save_html_to = digest.get("save_html_to")

    return Prefs(
        include_keywords=_str_list(data.get("include_keywords")),
        exclude_keywords=_str_list(data.get("exclude_keywords")),
        title_include=_str_list(data.get("title_include")),
        title_exclude=_str_list(data.get("title_exclude")),
        countries=_str_list(locations.get("countries")),
        cities=_str_list(locations.get("cities")),
        accept_remote=bool(work_mode.get("remote", True)),
        accept_hybrid=bool(work_mode.get("hybrid", True)),
        accept_onsite=bool(work_mode.get("onsite", True)),
        remote_only=bool(work_mode.get("remote_only", False)),
        remote_accept_locations=_str_list(remote.get("accept_locations")),
        remote_reject_locations=_str_list(remote.get("reject_locations")),
        visa_keywords=_str_list(data.get("visa_keywords")),
        visa_require=bool(visa.get("require", False)),
        visa_classifier=bool(visa.get("classifier", False)),
        visa_classifier_model=str(visa.get("classifier_model") or "claude-sonnet-4-6"),
        max_age_days=int(data.get("max_age_days", 14)),
        max_jobs=int(digest.get("max_jobs", 25)),
        save_html_to=str(save_html_to) if save_html_to else None,
        score_weights=_int_map(data.get("score_weights"), DEFAULT_SCORE_WEIGHTS),
        location_weights=_int_map(
            data.get("location_weights"), DEFAULT_LOCATION_WEIGHTS, replace=True
        ),
        source_enabled={str(k): bool(v) for k, v in sources.items()},
        ats_boards={str(name): _str_list(ats_boards.get(name)) for name in ATS_NAMES},
        adzuna_countries=[c.lower() for c in _str_list(adzuna.get("countries"))],
        adzuna_what=str(adzuna.get("what") or "software engineer"),
        adzuna_results_per_page=int(adzuna.get("results_per_page", 20)),
        adzuna_max_pages=int(adzuna.get("max_pages", 1)),
        arbeitnow_max_pages=int(arbeitnow.get("max_pages", 2)),
        arbeitnow_visa_sponsorship=arbeitnow_visa,
        http_timeout_seconds=float(http.get("timeout_seconds", 30)),
    )


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _int_map(value: Any, defaults: dict[str, int], *, replace: bool = False) -> dict[str, int]:
    """Read a user map of name -> int, lowercasing keys.

    With ``replace`` the supplied map stands alone, so a user can drop a default
    entry entirely; otherwise it overrides the defaults key by key.
    """
    if not isinstance(value, dict):
        return dict(defaults)
    merged = {} if replace else dict(defaults)
    for key, weight in value.items():
        try:
            merged[str(key).lower().strip()] = int(weight)
        except (TypeError, ValueError):
            continue
    return merged
