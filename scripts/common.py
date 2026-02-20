"""
Shared constants, types, and utilities for jinja-universal scripts.
"""

import shutil
import sys
import tomllib
from collections.abc import Mapping
from enum import StrEnum, auto
from pathlib import Path
from typing import NotRequired, TypedDict, cast

# Paths
REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "languages.toml"
LANGUAGES_DIR = REPO_ROOT / "languages"
TEMPLATES_DIR = Path(__file__).parent / "templates"
JINJA2_DIR = LANGUAGES_DIR / "jinja2"
README_PATH = REPO_ROOT / "README.md"
EXTENSION_TOML_PATH = REPO_ROOT / "extension.toml"

# Cache for Zed repo clones
CACHE_DIR = REPO_ROOT.parent / ".zed-cache"

# Required template files
REQUIRED_TEMPLATES = ["config.toml.template", "injections.scm.template"]

# Required fields in language config entries
REQUIRED_LANG_FIELDS = ["name", "zed_language"]
DETECTION_FIELDS = ["extensions", "suffixes", "filenames"]


class Source(StrEnum):
    """Where the language support comes from."""

    NATIVE = auto()  # Built into Zed
    EXTENSION = auto()  # From Zed extensions
    EXTRA = auto()  # Added manually, no Zed support


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


class LanguageConfig(TypedDict):
    name: str
    zed_language: str
    extensions: NotRequired[list[str]]
    suffixes: NotRequired[list[str]]
    filenames: NotRequired[list[str]]
    source: NotRequired[str]
    enabled: NotRequired[bool]


type ConfigDict = dict[str, LanguageConfig]


def fail(message: str) -> None:
    """Print error and exit."""
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def fail_many(errors: list[str]) -> None:
    """Print multiple errors and exit."""
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    raise SystemExit(1)


def validate_paths_exist(*paths: Path, context: str = "") -> None:
    """Validate that all paths exist, fail-fast if any missing."""
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            kind = "directory" if path.suffix == "" else "file"
            errors.append(f"{kind} not found: {path}")
    if errors:
        if context:
            print(f"Validation failed: {context}", file=sys.stderr)
        fail_many(errors)


def validate_generate_environment() -> None:
    """Validate environment for generate.py - call before any modifications."""
    errors: list[str] = []

    required_paths = [
        (TEMPLATES_DIR, f"Templates directory missing: {TEMPLATES_DIR}"),
        (LANGUAGES_DIR, f"Languages directory missing: {LANGUAGES_DIR}"),
        (JINJA2_DIR, f"Jinja2 base directory missing: {JINJA2_DIR}"),
        (README_PATH, f"README.md missing: {README_PATH}"),
        (EXTENSION_TOML_PATH, f"extension.toml missing: {EXTENSION_TOML_PATH}"),
        (CONFIG_PATH, f"Config file missing: {CONFIG_PATH}"),
    ]
    for path, message in required_paths:
        if not path.exists():
            errors.append(message)

    # Check template files
    if TEMPLATES_DIR.exists():
        for tmpl in REQUIRED_TEMPLATES:
            tmpl_path = TEMPLATES_DIR / tmpl
            if not tmpl_path.exists():
                errors.append(f"Template file missing: {tmpl_path}")

    if errors:
        fail_many(errors)


def validate_sync_environment() -> None:
    """Validate environment for sync_zed_languages.py."""
    errors: list[str] = []

    # Check git is available
    if not shutil.which("git"):
        errors.append("git command not found in PATH")

    # Config can be missing for sync (we create it), but parent must exist
    if not CONFIG_PATH.parent.exists():
        errors.append(f"Config parent directory missing: {CONFIG_PATH.parent}")

    if errors:
        fail_many(errors)


def validate_config_entry(lang_id: str, info: Mapping[str, object]) -> list[str]:
    """Validate a single config entry, return list of errors."""
    errors: list[str] = []

    for field in REQUIRED_LANG_FIELDS:
        if field not in info:
            errors.append(f"[{lang_id}] missing required field: {field}")

    if not any(field in info for field in DETECTION_FIELDS):
        errors.append(f"[{lang_id}] missing detection fields: one of {DETECTION_FIELDS} is required")

    for field in DETECTION_FIELDS:
        if field not in info:
            continue
        value = info[field]
        if not isinstance(value, list):
            errors.append(f"[{lang_id}] '{field}' must be a list")
            continue
        list_value = cast(list[object], value)
        if any(not isinstance(item, str) for item in list_value):
            errors.append(f"[{lang_id}] '{field}' must contain only strings")

    if "source" in info:
        valid_sources = [s.value for s in Source]
        if info["source"] not in valid_sources:
            errors.append(f"[{lang_id}] invalid source '{info['source']}', must be one of: {valid_sources}")

    return errors


def validate_config(config: ConfigDict) -> None:
    """Validate entire config, fail-fast if any issues."""
    if not config:
        fail("Config is empty")

    errors: list[str] = []
    for lang_id, info in config.items():
        errors.extend(validate_config_entry(lang_id, info))

    if errors:
        fail_many(errors)


def load_config() -> ConfigDict:
    """Load languages.toml config."""
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as f:
        raw = tomllib.load(f)
    return normalize_config(raw)


def normalize_config(raw: object) -> ConfigDict:
    """Convert parsed TOML content to typed config map."""
    if not isinstance(raw, dict):
        fail(f"Invalid config format in {CONFIG_PATH}: expected TOML table")

    raw_dict = cast(dict[object, object], raw)
    normalized: ConfigDict = {}
    for raw_lang_id, raw_info in raw_dict.items():
        if not isinstance(raw_lang_id, str):
            fail(f"Invalid config key type in {CONFIG_PATH}: expected string keys")
        if not isinstance(raw_info, dict):
            fail(f"Invalid config entry for [{raw_lang_id}] in {CONFIG_PATH}: expected table")
        lang_id = cast(str, raw_lang_id)
        info = cast(LanguageConfig, raw_info)
        normalized[lang_id] = info
    return normalized


def load_and_validate_config() -> ConfigDict:
    """Load and validate config - use this for operations that need valid config."""
    if not CONFIG_PATH.exists():
        fail(f"Config file not found: {CONFIG_PATH}")

    config = load_config()
    validate_config(config)
    return config


def save_config(config: ConfigDict) -> None:
    """Save languages.toml config."""
    lines = [
        "# Languages configuration for jinja-universal",
        "# source: native (Zed built-in), extension (Zed extension), extra (manual)",
        "",
    ]

    for lang_id in sorted(config.keys()):
        info = config[lang_id]
        lines.append(f"[{lang_id}]")
        lines.append(f'name = "{info["name"]}"')
        lines.append(f'zed_language = "{info["zed_language"]}"')
        detection_written = False
        for field in DETECTION_FIELDS:
            if field not in info:
                continue
            values = info.get(field, [])
            if not isinstance(values, list):
                continue
            typed_values = cast(list[str], values)
            val_str = ", ".join(f'"{e}"' for e in typed_values)
            lines.append(f"{field} = [{val_str}]")
            detection_written = True
        if not detection_written:
            lines.append("extensions = []")

        source = info.get("source", Source.EXTRA.value)
        lines.append(f'source = "{source}"')
        lines.append("")

    _ = CONFIG_PATH.write_text("\n".join(lines))
