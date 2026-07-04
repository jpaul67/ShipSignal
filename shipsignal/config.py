"""Repo-local defaults: `.shipsignal.toml` at the scan target's root.

Schema (all optional):

    [impact]
    extra_ai_aliases = { "acmebot" = "Acme internal" }  # merged into AI_TOOL_ALIASES at runtime
    squash = true
    release_tag_pattern = "^pkg@\\\\d+\\\\.\\\\d+\\\\.\\\\d+$"  # override default v?N.N[.N]
    [readiness]
    fail_under = 80
    exclude_modules = ["vendor/legacy"]
    [report]
    badge_label = "readiness"

Precedence (enforced by callers, not here): CLI flag > config file > built-in
default. Validation never raises: an unknown key is a warning (ignored), a
wrong-typed value is a warning naming the key (the built-in default is kept)
and a malformed/unreadable file is a warning (the whole file is skipped) — a
typo in `.shipsignal.toml` must never crash a scan. Callers should print the
returned warnings to stderr.

The schema is additive: unknown keys warn rather than error so later packages
(L's `survival` block, under `[impact]`) can add keys without breaking configs
written against an older ShipSignal.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = ".shipsignal.toml"


@dataclass
class ImpactConfig:
    extra_ai_aliases: dict[str, str] = field(default_factory=dict)
    squash: bool | None = None
    release_tag_pattern: str | None = None


@dataclass
class ReadinessConfig:
    fail_under: int | None = None
    exclude_modules: list[str] = field(default_factory=list)


@dataclass
class ReportConfig:
    badge_label: str | None = None


@dataclass
class Config:
    impact: ImpactConfig = field(default_factory=ImpactConfig)
    readiness: ReadinessConfig = field(default_factory=ReadinessConfig)
    report: ReportConfig = field(default_factory=ReportConfig)


_KNOWN_SECTIONS = {"impact", "readiness", "report"}


def _is_str_str_dict(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_int(value: object) -> bool:
    # bool is a subclass of int in Python — `fail_under = true` must not pass.
    return isinstance(value, int) and not isinstance(value, bool)


# impact.py's AI-alias matching is exact-TOKEN (see its `_tokens`/`_alias_key`):
# a key can only ever match a standalone alnum word in a trailer, never a
# hyphenated or multi-word phrase. An extra_ai_aliases key that isn't a single
# alnum word could never match anything, so it's rejected here rather than
# silently accepted and silently doing nothing.
_SINGLE_TOKEN_RE = re.compile(r"^[a-z0-9]+$")


def _valid_alias_key(kw: str) -> bool:
    return bool(_SINGLE_TOKEN_RE.match(kw.rstrip("-").lower()))


# Package K's release_tag_pattern is a user-supplied regex (for monorepo
# per-package tags like "pkg@1.2.3"). A malformed pattern must degrade like
# any other bad config value, not raise mid-scan — validated here, once,
# rather than at every impact.py call site.
def _is_valid_regex(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        re.compile(value)
    except re.error:
        return False
    return True


# section -> {key: (type-check, type-name-for-message, setter)}
_SCHEMA: dict[str, dict[str, tuple]] = {
    "impact": {
        "extra_ai_aliases": (_is_str_str_dict, "a table of string to string",
                             lambda cfg, v: setattr(cfg.impact, "extra_ai_aliases", dict(v))),
        "squash": (lambda v: isinstance(v, bool), "a bool",
                  lambda cfg, v: setattr(cfg.impact, "squash", v)),
        "release_tag_pattern": (_is_valid_regex, "a valid regex string",
                                lambda cfg, v: setattr(cfg.impact, "release_tag_pattern", v)),
    },
    "readiness": {
        "fail_under": (_is_int, "an int",
                       lambda cfg, v: setattr(cfg.readiness, "fail_under", v)),
        "exclude_modules": (_is_str_list, "a list of strings",
                            lambda cfg, v: setattr(cfg.readiness, "exclude_modules", list(v))),
    },
    "report": {
        "badge_label": (lambda v: isinstance(v, str), "a string",
                        lambda cfg, v: setattr(cfg.report, "badge_label", v)),
    },
}


def _apply_section(section: str, raw: object, cfg: Config, warnings: list[str]) -> None:
    if not isinstance(raw, dict):
        warnings.append(f"config section '[{section}]' must be a table (ignored)")
        return
    schema = _SCHEMA[section]
    for key, value in raw.items():
        if key not in schema:
            warnings.append(f"unknown config key '{section}.{key}' in {CONFIG_FILENAME} (ignored)")
            continue
        type_check, type_name, setter = schema[key]
        if not type_check(value):
            warnings.append(
                f"config key '{section}.{key}' expects {type_name}, "
                f"got {value!r} — using default"
            )
            continue
        if section == "impact" and key == "extra_ai_aliases":
            clean: dict[str, str] = {}
            for kw, label in value.items():
                if not _valid_alias_key(kw):
                    warnings.append(
                        f"config key 'impact.extra_ai_aliases' entry {kw!r} is not a single "
                        "alnum word — matching is exact-token, like the built-in registry "
                        "(see CLAUDE.md) — ignored"
                    )
                    continue
                clean[kw] = label
            setter(cfg, clean)
            continue
        setter(cfg, value)


def load_config(root: Path) -> tuple[Config, list[str]]:
    """Load `.shipsignal.toml` from ``root``. Never raises.

    Returns (config, warnings). Warnings are human-readable and safe to print
    to stderr as-is; an empty file, a missing file, or a fully-valid file all
    return an empty warnings list.
    """
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return Config(), []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return Config(), [f"could not parse {CONFIG_FILENAME}: {exc} — using defaults"]

    cfg = Config()
    warnings: list[str] = []
    for section, raw in data.items():
        if section not in _KNOWN_SECTIONS:
            warnings.append(f"unknown config section '[{section}]' in {CONFIG_FILENAME} (ignored)")
            continue
        _apply_section(section, raw, cfg, warnings)
    return cfg, warnings
