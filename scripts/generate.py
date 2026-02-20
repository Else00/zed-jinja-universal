#!/usr/bin/env python3
"""
Generate language folders and update README from languages.toml config.
Supports filtering by source type.

Usage:
    uv run generate.py              # Generate native + extension languages (default)
    uv run generate.py --native     # Only native Zed languages
    uv run generate.py --ext        # Only extension languages
    uv run generate.py --all        # ALL languages (including extra)
    uv run generate.py --sort       # Sort languages.toml
"""

import argparse
import re
import shutil
from pathlib import Path
from string import Template
from typing import cast

from common import (
    EXTENSION_TOML_PATH,
    JINJA2_DIR,
    LANGUAGES_DIR,
    README_PATH,
    TEMPLATES_DIR,
    ConfigDict,
    LanguageConfig,
    Source,
    fail,
    load_and_validate_config,
    save_config,
    validate_generate_environment,
)

JINJA_VARIANTS = ["jinja", "jinja2", "j2"]
README_START_MARKER = "<!-- LANGUAGES_TABLE_START -->"
README_END_MARKER = "<!-- LANGUAGES_TABLE_END -->"
README_MODE_START_MARKER = "<!-- GENERATED_MODE_START -->"
README_MODE_END_MARKER = "<!-- GENERATED_MODE_END -->"
EXCLUDE_LANGUAGES_WITHOUT_DETECTION = True

config_template: Template | None = None
injections_template: Template | None = None


class GenerateArgs(argparse.Namespace):
    sort: bool = False
    all: bool = False
    native: bool = False
    ext: bool = False


def load_template(name: str) -> Template:
    """Load a template file. Assumes validation already done."""
    path = TEMPLATES_DIR / f"{name}.template"
    return Template(path.read_text())


def init_templates() -> None:
    """Initialize templates. Call after validate_generate_environment()."""
    global config_template, injections_template
    config_template = load_template("config.toml")
    injections_template = load_template("injections.scm")


def generate_path_suffixes(extensions: list[str]) -> list[str]:
    return [f"{ext}.{variant}" for ext in sorted(extensions) for variant in JINJA_VARIANTS]


def get_detection_tokens(info: LanguageConfig) -> list[str]:
    suffixes = info.get("suffixes")
    filenames = info.get("filenames")
    if suffixes is not None or filenames is not None:
        collected: list[str] = []
        if suffixes is not None:
            collected.extend(suffixes)
        if filenames is not None:
            collected.extend(filenames)
        return list(dict.fromkeys(collected))

    extensions = info.get("extensions")
    return extensions if extensions is not None else []


def generate_config_toml(name: str, extensions: list[str]) -> str:
    assert config_template is not None
    suffixes = generate_path_suffixes(extensions)
    suffixes_str = ", ".join(f'"{s}"' for s in suffixes)
    return config_template.substitute(name=name, suffixes=suffixes_str)


def generate_injections_scm(zed_language: str) -> str:
    assert injections_template is not None
    return injections_template.substitute(zed_language=zed_language)


def copy_template_files(target_dir: Path) -> None:
    for filename in ["highlights.scm", "brackets.scm", "indents.scm"]:
        src = JINJA2_DIR / filename
        dst = target_dir / filename
        if src.exists():
            _ = shutil.copy(src, dst)


def generate_language_folder(lang_id: str, info: LanguageConfig) -> None:
    folder_name = f"{lang_id}_jinja"
    target_dir = LANGUAGES_DIR / folder_name
    target_dir.mkdir(exist_ok=True)

    config_content = generate_config_toml(info["name"], get_detection_tokens(info))
    _ = (target_dir / "config.toml").write_text(config_content)

    injections_content = generate_injections_scm(info["zed_language"])
    _ = (target_dir / "injections.scm").write_text(injections_content)

    copy_template_files(target_dir)


def delete_language_folder(lang_id: str) -> bool:
    folder_name = f"{lang_id}_jinja"
    target_dir = LANGUAGES_DIR / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
        return True
    return False


def get_existing_language_folders() -> set[str]:
    if not LANGUAGES_DIR.exists():
        return set()
    return {item.name[:-6] for item in LANGUAGES_DIR.iterdir() if item.is_dir() and item.name.endswith("_jinja")}


def normalize_source(info: LanguageConfig) -> str:
    source = info.get("source", Source.EXTRA.value)
    if isinstance(source, Source):
        return source.value
    return source


def has_detection_tokens(info: LanguageConfig) -> bool:
    return bool(get_detection_tokens(info))


def should_include(info: LanguageConfig, args: GenerateArgs) -> bool:
    """Determine if a language should be included based on source filters."""
    if EXCLUDE_LANGUAGES_WITHOUT_DETECTION and not has_detection_tokens(info):
        return False

    if args.all:
        return True

    source = normalize_source(info)

    if args.native and source == Source.NATIVE.value:
        return True
    if args.ext and source == Source.EXTENSION.value:
        return True

    # Default: native + extension (no extra)
    if not args.native and not args.ext:
        return source in (Source.NATIVE.value, Source.EXTENSION.value)

    return False


def generate_languages(config: ConfigDict, args: GenerateArgs) -> tuple[int, int, int]:
    """Generate language folders based on filters."""
    generated = 0
    skipped = 0
    deleted = 0

    selected_langs = {lang_id for lang_id, info in config.items() if should_include(info, args)}

    for lang_id in get_existing_language_folders():
        if lang_id not in selected_langs and delete_language_folder(lang_id):
            deleted += 1

    for lang_id, info in config.items():
        if lang_id in selected_langs:
            generate_language_folder(lang_id, info)
            generated += 1
        else:
            skipped += 1

    return generated, skipped, deleted


def format_extensions_for_readme(extensions: list[str]) -> str:
    return ", ".join(f"`.{ext}.*`" for ext in sorted(extensions))


def format_detection_for_readme(info: LanguageConfig) -> str:
    suffixes = info.get("suffixes")
    filenames = info.get("filenames")
    if suffixes is not None or filenames is not None:
        formatted: list[str] = []
        if suffixes is not None:
            formatted.extend(f"`.{ext}.*`" for ext in sorted(suffixes))
        if filenames is not None:
            formatted.extend(f"`{filename}.*`" for filename in sorted(filenames))
        return ", ".join(formatted)

    return format_extensions_for_readme(get_detection_tokens(info))


def generate_readme_table(config: ConfigDict, args: GenerateArgs) -> str:
    lines = [
        "| Language | File Extensions |",
        "|----------|-----------------|",
        "| Jinja2 | `.html.*`, `.j2`, `.jinja`, `.jinja2` |",
    ]

    entries = [
        (f"{info['name']}-Jinja", format_detection_for_readme(info)) for info in config.values() if should_include(info, args)
    ]

    for name, extensions in sorted(entries, key=lambda x: x[0].lower()):
        lines.append(f"| {name} | {extensions} |")

    return "\n".join(lines)


def replace_marked_block(content: str, start_marker: str, end_marker: str, replacement: str) -> str:
    """Replace content between markers with replacement text."""
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        fail(f"Markers not found or invalid order. Expected '{start_marker}' and '{end_marker}'")

    return content[: start_idx + len(start_marker)] + "\n\n" + replacement + "\n\n" + content[end_idx:]


def update_readme(table: str, count: int, filter_label: str, filter_scope: str) -> bool:
    content = README_PATH.read_text()

    content, summary_updates = re.subn(
        r"<summary>Click to expand the full list of \d+ supported languages</summary>",
        f"<summary>Click to expand the full list of {count} supported languages</summary>",
        content,
    )
    if summary_updates == 0:
        fail("README summary line not found or has unexpected format")

    mode_block = f"**Generated selection:** `{filter_label}`\n\nLiteral scope: {filter_scope}"
    content = replace_marked_block(content, README_MODE_START_MARKER, README_MODE_END_MARKER, mode_block)
    content = replace_marked_block(content, README_START_MARKER, README_END_MARKER, table)
    _ = README_PATH.write_text(content)
    return True


def format_human_list(items: list[str]) -> str:
    """Format a list as natural language."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def update_extension_manifest(count: int, source_categories: list[str]) -> bool:
    """Update extension.toml description with generated count and categories."""
    content = EXTENSION_TOML_PATH.read_text()

    if source_categories == ["none"]:
        source_phrase = "configured"
    else:
        source_list = format_human_list(source_categories)
        source_phrase = f"{source_list} category" if len(source_categories) == 1 else f"{source_list} categories"

    description = (
        f"Jinja2 template support for {count} languages "
        f"across Zed's {source_phrase} (Python, YAML, TOML, Markdown, HTML, JS, SQL, and more)"
    )
    updated_content, replacements = re.subn(
        r'(?m)^description\s*=\s*"[^"\n]*"$',
        f'description = "{description}"',
        content,
        count=1,
    )
    if replacements == 0:
        fail("extension.toml description line not found or has unexpected format")

    _ = EXTENSION_TOML_PATH.write_text(updated_content)
    return True


def sort_config() -> None:
    """Sort languages.toml alphabetically preserving all fields."""
    config = load_and_validate_config()
    save_config(config)
    print(f"Sorted {len(config)} languages in languages.toml")


def print_stats(config: ConfigDict) -> None:
    """Print config statistics."""
    by_source = {Source.NATIVE.value: 0, Source.EXTENSION.value: 0, Source.EXTRA.value: 0}
    for info in config.values():
        source = normalize_source(info)
        if "enabled" in info and "source" not in info:
            source = Source.NATIVE.value if info.get("enabled") else Source.EXTRA.value
        by_source[source] = by_source.get(source, 0) + 1

    print(f"Loaded {len(config)} languages from languages.toml")
    summary = (
        f"  Native: {by_source[Source.NATIVE.value]}, "
        + f"Extension: {by_source[Source.EXTENSION.value]}, "
        + f"Extra: {by_source[Source.EXTRA.value]}"
    )
    print(summary)


def print_filter_info(args: GenerateArgs) -> None:
    """Print filter information in a human-readable format."""
    print(f"Filter: {get_filter_label(args)}")


def get_filter_label(args: GenerateArgs) -> str:
    """Return the short label used for generated mode output."""
    if args.all:
        return "all (native + extension + extra)"
    if args.native and args.ext:
        return "native + extension"
    if args.native:
        return "native only"
    if args.ext:
        return "extension only"
    return "native + extension (default)"


def get_filter_scope(args: GenerateArgs) -> str:
    """Return a literal scope description for README metadata."""
    if args.all:
        return "all native, extension, and extra languages."
    if args.native and args.ext:
        return "all native and extension languages."
    if args.native:
        return "only native languages."
    if args.ext:
        return "only extension languages."
    return "all native and extension languages (extra excluded)."


def infer_selected_source_categories(config: ConfigDict, args: GenerateArgs) -> list[str]:
    """Return selected source categories in stable order: native, extension, extra."""
    selected_sources = {normalize_source(info) for info in config.values() if should_include(info, args)}
    ordered_sources = [Source.NATIVE.value, Source.EXTENSION.value, Source.EXTRA.value]
    source_categories = [source for source in ordered_sources if source in selected_sources]
    return source_categories if source_categories else ["none"]


def parse_arguments() -> GenerateArgs:
    parser = argparse.ArgumentParser(description="Generate language folders")
    _ = parser.add_argument("--sort", action="store_true", help="Sort languages.toml")
    _ = parser.add_argument("--all", action="store_true", help="Generate ALL languages (including extra)")
    _ = parser.add_argument("--native", action="store_true", help="Only native Zed languages")
    _ = parser.add_argument("--ext", action="store_true", help="Only extension languages")
    return cast(GenerateArgs, parser.parse_args())


def main() -> int:
    args = parse_arguments()

    # --- FAIL-FAST VALIDATION ---
    validate_generate_environment()

    if args.sort:
        sort_config()
        return 0

    # Load and validate config
    config = load_and_validate_config()

    # Initialize templates (after validation)
    init_templates()

    # Print info
    print_stats(config)
    print_filter_info(args)

    # Generate
    generated, skipped, deleted = generate_languages(config, args)
    print(f"\nGenerated {generated} language folders")
    if skipped > 0:
        print(f"Skipped {skipped} languages")
    if deleted > 0:
        print(f"Deleted {deleted} old folders")

    # Update README
    table = generate_readme_table(config, args)
    filter_label = get_filter_label(args)
    filter_scope = get_filter_scope(args)
    source_categories = infer_selected_source_categories(config, args)
    _ = update_readme(table, generated, filter_label, filter_scope)
    print("README.md updated!")
    _ = update_extension_manifest(generated, source_categories)
    print("extension.toml updated!")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
