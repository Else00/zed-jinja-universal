#!/usr/bin/env python3
"""
Sync languages.toml with Zed's supported languages.
Fetches data from Zed repos, updates config, and can compare differences.

Usage:
    uv run scripts/sync_zed_languages.py                    # Update source fields
    uv run scripts/sync_zed_languages.py --add              # Add missing Zed languages
    uv run scripts/sync_zed_languages.py --add --native     # Add only native languages
    uv run scripts/sync_zed_languages.py --add --ext        # Add only extension languages
    uv run scripts/sync_zed_languages.py --list             # List all Zed languages
    uv run scripts/sync_zed_languages.py --list --native    # List native only
    uv run scripts/sync_zed_languages.py --list --ext       # List extensions only
    uv run scripts/sync_zed_languages.py --diff             # Compare with Zed data
    uv run scripts/sync_zed_languages.py --classify         # Report extension capabilities
    uv run scripts/sync_zed_languages.py --classify-json /tmp/report.json  # Capability report + JSON dump
"""

import argparse
import http.client
import json
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from common import CACHE_DIR, ConfigDict, LanguageConfig, Source, fail, load_config, save_config, validate_sync_environment

# Zed repos
ZED_MAIN_REPO_URL = "https://github.com/zed-industries/zed.git"
ZED_MAIN_REPO_PATH = CACHE_DIR / "zed"
ZED_MAIN_CARGO_PATH = ZED_MAIN_REPO_PATH / "Cargo.toml"
ZED_EXT_REPO_URL = "https://github.com/zed-industries/extensions.git"
ZED_EXT_REPO_PATH = CACHE_DIR / "extensions"


@dataclass
class LanguageInfo:
    id: str
    name: str
    zed_language: str
    extensions: list[str]
    source: Source
    syntax_signature: str = ""


@dataclass
class ExtensionCapability:
    extension_id: str
    repo_url: str
    has_extension_toml: bool
    grammar_names: list[str]
    grammar_repositories: list[str]
    language_servers: list[str]
    path_suffixes: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)
    full_filenames: list[str] = field(default_factory=list)
    other_patterns: list[str] = field(default_factory=list)


class SyncArgs(argparse.Namespace):
    list: bool = False
    add: bool = False
    diff: bool = False
    classify: bool = False
    classify_json: str | None = None
    native: bool = False
    ext: bool = False


def run_cmd(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def ensure_repo(repo_url: str, repo_path: Path, name: str) -> bool:
    CACHE_DIR.mkdir(exist_ok=True)
    if repo_path.exists():
        print(f"  Updating {name}...")
        code, _, _ = run_cmd(["git", "pull", "--ff-only"], cwd=repo_path)
        if code != 0:
            print("  Warning: git pull failed, recloning...", file=sys.stderr)
            shutil.rmtree(repo_path)
            return ensure_repo(repo_url, repo_path, name)
        return True
    else:
        print(f"  Cloning {name}...")
        code, _, err = run_cmd(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", repo_url, str(repo_path)])
        if code != 0:
            print(f"  ERROR: git clone failed: {err}", file=sys.stderr)
            return False
        return True


def ensure_zed_main_repo() -> bool:
    if not ensure_repo(ZED_MAIN_REPO_URL, ZED_MAIN_REPO_PATH, "zed-industries/zed"):
        return False
    _ = run_cmd(["git", "sparse-checkout", "set", "Cargo.toml", "crates/languages/src"], cwd=ZED_MAIN_REPO_PATH)
    _ = run_cmd(["git", "checkout"], cwd=ZED_MAIN_REPO_PATH)
    return True


def ensure_extensions_repo() -> bool:
    return ensure_repo(ZED_EXT_REPO_URL, ZED_EXT_REPO_PATH, "zed-industries/extensions")


def fetch_text(url: str, timeout: int = 10) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "jinja-universal-sync"})
    try:
        response = cast(http.client.HTTPResponse, urllib.request.urlopen(req, timeout=timeout))
        with response:
            payload = response.read()
        return payload.decode()
    except Exception:
        return None


def github_url_to_raw(repo_url: str, branch: str, file_path: str) -> str:
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    repo_url = repo_url.replace("github.com", "raw.githubusercontent.com")
    return f"{repo_url}/{branch}/{file_path}"


def parse_toml_value(content: str, key: str) -> str | list[str] | None:
    parsed_ok, parsed_value = parse_toml_value_with_tomllib(content, key)
    if parsed_ok:
        return parsed_value
    return parse_toml_value_regex_fallback(content, key)


def parse_toml_value_with_tomllib(content: str, key: str) -> tuple[bool, str | list[str] | None]:
    try:
        parsed = cast(dict[str, object], tomllib.loads(content))
    except tomllib.TOMLDecodeError:
        return False, None

    if key not in parsed:
        return True, None
    value = parsed[key]
    if isinstance(value, str):
        return True, value
    if isinstance(value, list):
        return True, flatten_string_list(cast(list[object], value))
    return True, str(value)


def parse_toml_value_regex_fallback(content: str, key: str) -> str | list[str] | None:
    pattern = rf"^{re.escape(key)}\s*=\s*(.+)$"
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("["):
        bracket_count = 0
        end_idx = 0
        for i, c in enumerate(value):
            if c == "[":
                bracket_count += 1
            elif c == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i + 1
                    break
        strings = re.findall(r'"([^"]*)"', value[:end_idx])
        return strings
    return value


def flatten_string_list(items: list[object]) -> list[str]:
    flattened: list[str] = []
    for item in items:
        if isinstance(item, str):
            flattened.append(item)
        elif isinstance(item, list):
            flattened.extend(flatten_string_list(cast(list[object], item)))
    return flattened


def extract_extensions(path_suffixes: list[str]) -> list[str]:
    extensions: list[str] = []
    for suffix in path_suffixes:
        if suffix.startswith("."):
            suffix = suffix[1:]
        if suffix.startswith("*"):
            suffix = suffix[1:]
            if suffix.startswith("."):
                suffix = suffix[1:]
        if "*" in suffix or "/" in suffix:
            continue
        if suffix:
            extensions.append(suffix)
    return list(dict.fromkeys(extensions))


def get_native_languages() -> list[LanguageInfo]:
    if not ensure_zed_main_repo():
        fail("Failed to clone/update Zed main repo")

    languages_dir = ZED_MAIN_REPO_PATH / "crates" / "languages" / "src"
    if not languages_dir.exists():
        fail(f"Expected Zed languages dir not found: {languages_dir}\nZed repo structure may have changed.")

    languages: list[LanguageInfo] = []
    parse_errors: list[str] = []
    for item in languages_dir.iterdir():
        if not item.is_dir():
            continue
        config_path = item / "config.toml"
        if not config_path.exists():
            continue

        try:
            content = config_path.read_text()
            parsed_name = parse_toml_value(content, "name")
            name = parsed_name if isinstance(parsed_name, str) else item.name.title()
            path_suffixes = parse_toml_value(content, "path_suffixes")
            extensions = extract_extensions(path_suffixes) if isinstance(path_suffixes, list) else []
            lang_id = item.name.lower().replace("-", "_")

            languages.append(
                LanguageInfo(
                    id=lang_id,
                    name=name,
                    zed_language=item.name.lower(),
                    extensions=extensions,
                    source=Source.NATIVE,
                )
            )
        except Exception as e:
            parse_errors.append(f"{item.name}: {e}")

    if parse_errors:
        print(f"  Warning: {len(parse_errors)} languages had parse errors:", file=sys.stderr)
        for err in parse_errors[:5]:
            print(f"    - {err}", file=sys.stderr)

    if not languages:
        fail("No native languages found - Zed repo structure may have changed")

    return languages


def parse_gitmodules() -> dict[str, str]:
    gitmodules_path = ZED_EXT_REPO_PATH / ".gitmodules"
    if not gitmodules_path.exists():
        fail(f".gitmodules not found: {gitmodules_path}\nZed extensions repo structure may have changed.")
    content = gitmodules_path.read_text()
    extensions: dict[str, str] = {}
    current_name: str | None = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('[submodule "extensions/'):
            match = re.match(r'\[submodule "extensions/([^"]+)"\]', line)
            if match:
                current_name = match.group(1)
        elif line.startswith("url = ") and current_name:
            extensions[current_name] = line[6:].strip()
            current_name = None

    if not extensions:
        fail("No extensions found in .gitmodules - format may have changed")

    return extensions


def normalize_repo_url(repo_url: str) -> str:
    normalized = repo_url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def parse_extension_table_keys(parsed_toml: object, table_name: str) -> list[str]:
    if not isinstance(parsed_toml, dict):
        return []
    parsed_dict = cast(dict[str, object], parsed_toml)
    table_obj = parsed_dict.get(table_name)
    if not isinstance(table_obj, dict):
        return []
    table = cast(dict[object, object], table_obj)
    return sorted(key for key in table if isinstance(key, str))


def parse_extension_grammar_repositories(parsed_toml: object) -> list[str]:
    if not isinstance(parsed_toml, dict):
        return []
    parsed_dict = cast(dict[str, object], parsed_toml)
    grammars_obj = parsed_dict.get("grammars")
    if not isinstance(grammars_obj, dict):
        return []
    grammars = cast(dict[object, object], grammars_obj)

    repositories: list[str] = []
    for grammar_config_obj in grammars.values():
        if not isinstance(grammar_config_obj, dict):
            continue
        grammar_config = cast(dict[str, object], grammar_config_obj)
        repository_obj = grammar_config.get("repository")
        if isinstance(repository_obj, str):
            repositories.append(normalize_repo_url(repository_obj))
    return sorted(set(repositories))


def make_repository_signature(repository: str, path: str | None = None) -> str:
    normalized_repository = normalize_repo_url(repository)
    if not path:
        return normalized_repository
    normalized_path = path.strip().strip("/").lower()
    return f"{normalized_repository}#{normalized_path}" if normalized_path else normalized_repository


def load_zed_workspace_dependencies() -> dict[object, object]:
    if not ZED_MAIN_CARGO_PATH.exists():
        fail(f"Expected Zed workspace Cargo.toml not found: {ZED_MAIN_CARGO_PATH}")

    with ZED_MAIN_CARGO_PATH.open("rb") as file_handle:
        parsed_obj = cast(dict[str, object], tomllib.load(file_handle))

    workspace_obj = parsed_obj.get("workspace")
    if not isinstance(workspace_obj, dict):
        fail("Invalid Zed workspace Cargo.toml: [workspace] section missing")
    assert isinstance(workspace_obj, dict)
    workspace = cast(dict[str, object], workspace_obj)

    dependencies_obj = workspace.get("dependencies")
    if not isinstance(dependencies_obj, dict):
        fail("Invalid Zed workspace Cargo.toml: [workspace.dependencies] section missing")
    assert isinstance(dependencies_obj, dict)
    return cast(dict[object, object], dependencies_obj)


def extract_native_tree_sitter_git_signatures(dependencies: dict[object, object]) -> set[str]:
    signatures: set[str] = set()
    for dependency_name, dependency_spec in dependencies.items():
        if not isinstance(dependency_name, str) or not dependency_name.startswith("tree-sitter-"):
            continue
        if not isinstance(dependency_spec, dict):
            continue
        spec = cast(dict[str, object], dependency_spec)
        git_obj = spec.get("git")
        if not isinstance(git_obj, str):
            continue
        path_obj = spec.get("path")
        path = path_obj if isinstance(path_obj, str) else None
        signatures.add(make_repository_signature(git_obj, path))

    if not signatures:
        fail("No native tree-sitter git repositories found in Zed workspace Cargo.toml")
    return signatures


def parse_native_tree_sitter_git_signatures() -> set[str]:
    if not ensure_zed_main_repo():
        fail("Failed to clone/update Zed main repo")
    dependencies = load_zed_workspace_dependencies()
    return extract_native_tree_sitter_git_signatures(dependencies)


def derive_extension_grammar_signature(grammar_config: object) -> str:
    if not isinstance(grammar_config, dict):
        return ""
    config = cast(dict[str, object], grammar_config)
    repository_obj = config.get("repository")
    if not isinstance(repository_obj, str):
        return ""
    path_obj = config.get("path")
    path = path_obj if isinstance(path_obj, str) else None
    return make_repository_signature(repository_obj, path)


def dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def split_path_suffixes(path_suffixes: list[str]) -> tuple[list[str], list[str], list[str]]:
    suffixes: list[str] = []
    full_filenames: list[str] = []
    other_patterns: list[str] = []

    for raw_value in path_suffixes:
        value = raw_value.strip()
        if not value:
            continue
        if "/" in value:
            other_patterns.append(value)
            continue
        if "*" in value:
            if value.startswith("*.") and value.count("*") == 1:
                suffixes.append(value)
            else:
                other_patterns.append(value)
            continue
        if value.startswith("."):
            suffixes.append(value)
            continue
        full_filenames.append(value)

    return dedupe_strings(suffixes), dedupe_strings(full_filenames), dedupe_strings(other_patterns)


def get_grammar_detection_targets(
    repo_url: str, branch: str, grammar_name: str
) -> tuple[list[str], list[str], list[str], list[str]]:
    config_content = fetch_grammar_config(repo_url, branch, grammar_name)
    if not config_content:
        return [], [], [], []

    path_suffixes_value = parse_toml_value(config_content, "path_suffixes")
    if not isinstance(path_suffixes_value, list):
        return [], [], [], []

    raw_suffixes = dedupe_strings(path_suffixes_value)
    suffixes, full_filenames, other_patterns = split_path_suffixes(raw_suffixes)
    return raw_suffixes, suffixes, full_filenames, other_patterns


def parse_extension_capability(extension_id: str, repo_url: str) -> ExtensionCapability:
    ext_info = fetch_extension_toml(repo_url)
    if not ext_info:
        return ExtensionCapability(
            extension_id=extension_id,
            repo_url=repo_url,
            has_extension_toml=False,
            grammar_names=[],
            grammar_repositories=[],
            language_servers=[],
            path_suffixes=[],
            suffixes=[],
            full_filenames=[],
            other_patterns=[],
        )

    ext_toml, branch = ext_info
    try:
        parsed_toml = tomllib.loads(ext_toml)
    except tomllib.TOMLDecodeError:
        grammar_names = extract_grammars(ext_toml)
        path_suffixes: list[str] = []
        suffixes: list[str] = []
        full_filenames: list[str] = []
        other_patterns: list[str] = []
        for grammar_name in grammar_names:
            raw_values, grammar_suffixes, grammar_full_filenames, grammar_other_patterns = get_grammar_detection_targets(
                repo_url, branch, grammar_name
            )
            path_suffixes.extend(raw_values)
            suffixes.extend(grammar_suffixes)
            full_filenames.extend(grammar_full_filenames)
            other_patterns.extend(grammar_other_patterns)
        return ExtensionCapability(
            extension_id=extension_id,
            repo_url=repo_url,
            has_extension_toml=True,
            grammar_names=grammar_names,
            grammar_repositories=[],
            language_servers=[],
            path_suffixes=dedupe_strings(path_suffixes),
            suffixes=dedupe_strings(suffixes),
            full_filenames=dedupe_strings(full_filenames),
            other_patterns=dedupe_strings(other_patterns),
        )

    grammar_names = parse_extension_table_keys(parsed_toml, "grammars")
    grammar_repositories = parse_extension_grammar_repositories(parsed_toml)
    language_servers = parse_extension_table_keys(parsed_toml, "language_servers")
    path_suffixes_all: list[str] = []
    suffixes_all: list[str] = []
    full_filenames_all: list[str] = []
    other_patterns_all: list[str] = []
    for grammar_name in grammar_names:
        raw_values, grammar_suffixes, grammar_full_filenames, grammar_other_patterns = get_grammar_detection_targets(
            repo_url, branch, grammar_name
        )
        path_suffixes_all.extend(raw_values)
        suffixes_all.extend(grammar_suffixes)
        full_filenames_all.extend(grammar_full_filenames)
        other_patterns_all.extend(grammar_other_patterns)

    return ExtensionCapability(
        extension_id=extension_id,
        repo_url=repo_url,
        has_extension_toml=True,
        grammar_names=grammar_names,
        grammar_repositories=grammar_repositories,
        language_servers=language_servers,
        path_suffixes=dedupe_strings(path_suffixes_all),
        suffixes=dedupe_strings(suffixes_all),
        full_filenames=dedupe_strings(full_filenames_all),
        other_patterns=dedupe_strings(other_patterns_all),
    )


def collect_extension_capabilities() -> list[ExtensionCapability]:
    if not ensure_extensions_repo():
        fail("Failed to clone/update Zed extensions repo")

    print("  Parsing .gitmodules...")
    extensions = parse_gitmodules()
    print(f"  Found {len(extensions)} extensions")
    print("  Analyzing extension capabilities...")

    capabilities: list[ExtensionCapability] = []
    checked = 0
    parse_errors = 0

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {
            executor.submit(parse_extension_capability, ext_name, repo_url): ext_name for ext_name, repo_url in extensions.items()
        }
        for future in as_completed(futures):
            checked += 1
            if checked % 100 == 0:
                print(f"    Checked {checked}/{len(extensions)}...")
            try:
                capabilities.append(future.result())
            except Exception:
                parse_errors += 1

    if parse_errors > len(extensions) * 0.5:
        fail(f"Too many analysis errors ({parse_errors}/{len(extensions)}) - network issue or API changed")

    if not capabilities:
        fail("No extension capabilities found - Zed extensions structure may have changed")

    return sorted(capabilities, key=lambda capability: capability.extension_id)


def print_extension_capability_report(capabilities: list[ExtensionCapability]) -> None:
    total = len(capabilities)
    with_toml = sum(1 for capability in capabilities if capability.has_extension_toml)
    with_grammar = sum(1 for capability in capabilities if capability.grammar_names)
    with_lsp = sum(1 for capability in capabilities if capability.language_servers)
    both = sum(1 for capability in capabilities if capability.grammar_names and capability.language_servers)
    lsp_only = sum(1 for capability in capabilities if not capability.grammar_names and capability.language_servers)
    grammar_only = sum(1 for capability in capabilities if capability.grammar_names and not capability.language_servers)
    no_features = total - both - lsp_only - grammar_only

    repo_to_extensions: dict[str, list[str]] = {}
    for capability in capabilities:
        for repository in capability.grammar_repositories:
            repo_to_extensions.setdefault(repository, []).append(capability.extension_id)

    shared_repositories = {
        repository: sorted(extension_ids) for repository, extension_ids in repo_to_extensions.items() if len(extension_ids) > 1
    }
    core_like_repositories = sorted(
        repository for repository in repo_to_extensions if repository.startswith("https://github.com/zed-industries/tree-sitter-")
    )

    print("\n" + "=" * 60)
    print("EXTENSION CAPABILITY REPORT")
    print("=" * 60)
    print(f"Total extensions analyzed: {total}")
    print(f"With extension.toml: {with_toml}")
    print(f"With grammars: {with_grammar}")
    print(f"With language servers: {with_lsp}")
    print(f"Grammar + LSP: {both}")
    print(f"Grammar-only: {grammar_only}")
    print(f"LSP-only: {lsp_only}")
    print(f"No grammar/LSP: {no_features}")
    print(f"Unique grammar repositories: {len(repo_to_extensions)}")
    print(f"Shared grammar repositories: {len(shared_repositories)}")
    print(f"Core-like tree-sitter repositories: {len(core_like_repositories)}")

    if shared_repositories:
        print("\nShared grammar repositories (first 20):")
        for repository in sorted(shared_repositories)[:20]:
            extensions = ", ".join(shared_repositories[repository][:5])
            suffix = "..." if len(shared_repositories[repository]) > 5 else ""
            print(f"  - {repository} ({len(shared_repositories[repository])}): {extensions}{suffix}")

    lsp_only_examples = sorted(
        capability.extension_id for capability in capabilities if not capability.grammar_names and capability.language_servers
    )
    if lsp_only_examples:
        print(f"\nLSP-only extensions (first 20): {', '.join(lsp_only_examples[:20])}")

    missing_toml_examples = sorted(capability.extension_id for capability in capabilities if not capability.has_extension_toml)
    if missing_toml_examples:
        print(f"\nMissing extension.toml (first 20): {', '.join(missing_toml_examples[:20])}")


def capability_to_json_dict(capability: ExtensionCapability) -> dict[str, object]:
    if capability.grammar_names and capability.language_servers:
        category = "grammar+lsp"
    elif capability.grammar_names:
        category = "grammar-only"
    elif capability.language_servers:
        category = "lsp-only"
    else:
        category = "none"

    return {
        "extension_id": capability.extension_id,
        "repo_url": capability.repo_url,
        "category": category,
        "has_extension_toml": capability.has_extension_toml,
        "grammar_names": capability.grammar_names,
        "grammar_repositories": capability.grammar_repositories,
        "language_servers": capability.language_servers,
        "path_suffixes": capability.path_suffixes,
        "suffixes": capability.suffixes,
        "full_filenames": capability.full_filenames,
        "other_patterns": capability.other_patterns,
    }


def write_extension_capability_json(capabilities: list[ExtensionCapability], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [capability_to_json_dict(capability) for capability in capabilities]
    _ = output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def get_extension_language_info(_ext_name: str, repo_url: str) -> list[LanguageInfo] | None:
    ext_info = fetch_extension_toml(repo_url)
    if not ext_info:
        return None
    ext_toml, branch = ext_info

    try:
        parsed_toml = tomllib.loads(ext_toml)
    except tomllib.TOMLDecodeError:
        parsed_toml = None

    grammar_entries: dict[str, object] = {}
    if isinstance(parsed_toml, dict):
        parsed_dict = cast(dict[str, object], parsed_toml)
        grammars_obj = parsed_dict.get("grammars")
        if isinstance(grammars_obj, dict):
            grammars = cast(dict[object, object], grammars_obj)
            grammar_entries = {str(key): value for key, value in grammars.items() if isinstance(key, str)}
    if not grammar_entries:
        grammar_entries = {grammar: {} for grammar in extract_grammars(ext_toml)}
    if not grammar_entries:
        return None

    return [
        build_extension_language_info(
            grammar,
            repo_url,
            branch,
            syntax_signature=derive_extension_grammar_signature(grammar_config),
        )
        for grammar, grammar_config in grammar_entries.items()
    ]


def fetch_extension_toml(repo_url: str) -> tuple[str, str] | None:
    for branch in ["main", "master"]:
        url = github_url_to_raw(repo_url, branch, "extension.toml")
        ext_toml = fetch_text(url)
        if ext_toml:
            return ext_toml, branch
    return None


def extract_grammars(ext_toml: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"\[grammars\.([^\]]+)\]", ext_toml)]


def get_grammar_dir_candidates(grammar: str) -> list[str]:
    candidates: list[str] = []
    base_variants = [grammar, grammar.replace("_", "-"), grammar.replace("-", "_")]
    for base in base_variants:
        for variant in (base, base.lower(), base.upper(), base.title()):
            if variant and variant not in candidates:
                candidates.append(variant)
    return candidates


def get_config_paths_for_grammar(grammar: str) -> list[str]:
    language_paths = [f"languages/{candidate}/config.toml" for candidate in get_grammar_dir_candidates(grammar)]
    return language_paths + ["language/config.toml"]


def fetch_grammar_config(repo_url: str, branch: str, grammar: str) -> str | None:
    for config_path in get_config_paths_for_grammar(grammar):
        url = github_url_to_raw(repo_url, branch, config_path)
        config_content = fetch_text(url)
        if config_content:
            return config_content
    return None


def get_display_name(grammar: str, config_content: str | None) -> str:
    if not config_content:
        return grammar.replace("_", " ").replace("-", " ").title()
    name = parse_toml_value(config_content, "name")
    if isinstance(name, str):
        return name
    return grammar.replace("_", " ").replace("-", " ").title()


def get_grammar_extensions(config_content: str | None) -> list[str]:
    if not config_content:
        return []
    path_suffixes = parse_toml_value(config_content, "path_suffixes")
    if isinstance(path_suffixes, list):
        return extract_extensions(path_suffixes)
    return []


def build_extension_language_info(grammar: str, repo_url: str, branch: str, syntax_signature: str = "") -> LanguageInfo:
    config_content = fetch_grammar_config(repo_url, branch, grammar)
    return LanguageInfo(
        id=grammar.lower().replace("-", "_"),
        name=get_display_name(grammar, config_content),
        zed_language=grammar.lower(),
        extensions=get_grammar_extensions(config_content),
        source=Source.EXTENSION,
        syntax_signature=syntax_signature,
    )


def filter_extensions_reusing_native_syntax(
    native_signatures: set[str], ext_langs: list[LanguageInfo]
) -> tuple[list[LanguageInfo], list[LanguageInfo]]:
    kept: list[LanguageInfo] = []
    skipped: list[LanguageInfo] = []
    for lang in ext_langs:
        if lang.syntax_signature and lang.syntax_signature in native_signatures:
            skipped.append(lang)
            continue
        kept.append(lang)
    return kept, skipped


def get_extension_languages() -> list[LanguageInfo]:
    if not ensure_extensions_repo():
        fail("Failed to clone/update Zed extensions repo")

    print("  Parsing .gitmodules...")
    extensions = parse_gitmodules()
    print(f"  Found {len(extensions)} extensions")
    print("  Fetching language configs...")

    all_languages: list[LanguageInfo] = []
    checked = 0
    fetch_errors = 0

    def check_ext(item: tuple[str, str]) -> tuple[str, list[LanguageInfo] | None]:
        return item[0], get_extension_language_info(item[0], item[1])

    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(check_ext, item): item for item in extensions.items()}
        for future in as_completed(futures):
            checked += 1
            if checked % 100 == 0:
                print(f"    Checked {checked}/{len(extensions)}...")
            try:
                _, langs = future.result()
                if langs:
                    all_languages.extend(langs)
            except Exception:
                fetch_errors += 1

    if fetch_errors > len(extensions) * 0.5:
        fail(f"Too many fetch errors ({fetch_errors}/{len(extensions)}) - network issue or API changed")

    if not all_languages:
        fail("No extension languages found - Zed extensions structure may have changed")

    return all_languages


def print_languages(languages: list[LanguageInfo], title: str) -> None:
    print(f"\n{title} ({len(languages)}):")
    print("-" * 50)
    for lang in sorted(languages, key=lambda x: x.id):
        ext_str = ", ".join(lang.extensions[:3])
        if len(lang.extensions) > 3:
            ext_str += "..."
        print(f"  {lang.id}: {lang.name} [{ext_str}]")


def compare_with_zed(native_langs: list[LanguageInfo], ext_langs: list[LanguageInfo]):
    """Compare our config with Zed's languages."""
    config = load_config()
    zed_by_lang = map_zed_languages(native_langs, ext_langs)
    config_by_zed = map_config_languages(config)

    zed_ids = set(zed_by_lang.keys())
    our_zed_langs = set(config_by_zed.keys())
    common = our_zed_langs & zed_ids

    print_comparison_header()
    only_ours = print_only_in_ours(our_zed_langs, zed_ids, config_by_zed)
    only_zed = print_only_in_zed(zed_ids, our_zed_langs, zed_by_lang)
    differences = collect_extension_differences(common, zed_by_lang, config_by_zed)
    print_extension_differences(differences)
    print_no_diff_message(only_ours, only_zed, differences)
    print_comparison_footer(config, zed_by_lang, common)


def map_zed_languages(native_langs: list[LanguageInfo], ext_langs: list[LanguageInfo]) -> dict[str, LanguageInfo]:
    zed_by_lang: dict[str, LanguageInfo] = {}
    for lang in native_langs + ext_langs:
        if lang.zed_language not in zed_by_lang or lang.source == Source.NATIVE:
            zed_by_lang[lang.zed_language] = lang
    return zed_by_lang


def map_config_languages(config: ConfigDict) -> dict[str, tuple[str, LanguageConfig]]:
    return {info.get("zed_language", lang_id): (lang_id, info) for lang_id, info in config.items()}


def print_comparison_header() -> None:
    print("\n" + "=" * 60)
    print("COMPARISON: languages.toml vs Zed")
    print("=" * 60)


def print_only_in_ours(
    our_zed_langs: set[str],
    zed_ids: set[str],
    config_by_zed: dict[str, tuple[str, LanguageConfig]],
) -> set[str]:
    only_ours = our_zed_langs - zed_ids
    if not only_ours:
        return only_ours
    print(f"\n[!] In our config but NOT in Zed ({len(only_ours)}):")
    for zed_lang in sorted(only_ours):
        lang_id, info = config_by_zed[zed_lang]
        print(f"    - {lang_id} ({info.get('name')})")
    return only_ours


def print_only_in_zed(zed_ids: set[str], our_zed_langs: set[str], zed_by_lang: dict[str, LanguageInfo]) -> set[str]:
    only_zed = zed_ids - our_zed_langs
    if not only_zed:
        return only_zed
    print(f"\n[+] In Zed but NOT in our config ({len(only_zed)}):")
    for zed_lang in sorted(only_zed):
        lang = zed_by_lang[zed_lang]
        ext_str = ", ".join(lang.extensions[:3]) if lang.extensions else "none"
        print(f"    + {lang.id} ({lang.name}) [{ext_str}]")
    return only_zed


def collect_extension_differences(
    common: set[str],
    zed_by_lang: dict[str, LanguageInfo],
    config_by_zed: dict[str, tuple[str, LanguageConfig]],
) -> list[tuple[str, list[str]]]:
    differences: list[tuple[str, list[str]]] = []
    for zed_lang in sorted(common):
        our_lid, our_info = config_by_zed[zed_lang]
        zed_info = zed_by_lang[zed_lang]
        diffs = compare_extension_sets(our_info, zed_info)
        if diffs:
            differences.append((our_lid, diffs))
    return differences


def compare_extension_sets(our_info: LanguageConfig, zed_info: LanguageInfo) -> list[str]:
    diffs: list[str] = []
    our_ext = set(our_info.get("extensions", []))
    zed_ext = set(zed_info.extensions)
    if our_ext == zed_ext:
        return diffs
    only_ours_ext = our_ext - zed_ext
    only_zed_ext = zed_ext - our_ext
    if only_ours_ext:
        diffs.append(f"only in ours: {only_ours_ext}")
    if only_zed_ext:
        diffs.append(f"only in Zed: {only_zed_ext}")
    return diffs


def print_extension_differences(differences: list[tuple[str, list[str]]]) -> None:
    if not differences:
        return
    print(f"\n[~] Extension differences ({len(differences)}):")
    for lang_id, diffs in differences[:20]:
        print(f"    {lang_id}:")
        for diff in diffs:
            print(f"      - {diff}")
    if len(differences) > 20:
        print(f"    ... and {len(differences) - 20} more")


def print_no_diff_message(only_ours: set[str], only_zed: set[str], differences: list[tuple[str, list[str]]]) -> None:
    if not only_ours and not only_zed and not differences:
        print("\n[OK] No differences found!")


def print_comparison_footer(config: ConfigDict, zed_by_lang: dict[str, LanguageInfo], common: set[str]) -> None:
    print("\n" + "=" * 60)
    print(f"Summary: {len(config)} in our config, {len(zed_by_lang)} in Zed, {len(common)} common")
    print("=" * 60)


def parse_arguments() -> SyncArgs:
    parser = argparse.ArgumentParser(description="Sync with Zed's supported languages")
    _ = parser.add_argument("--list", action="store_true", help="List Zed languages")
    _ = parser.add_argument("--add", action="store_true", help="Add missing languages to config")
    _ = parser.add_argument("--diff", action="store_true", help="Compare our config with Zed")
    _ = parser.add_argument("--classify", action="store_true", help="Analyze extension grammar/LSP capabilities")
    _ = parser.add_argument(
        "--classify-json",
        metavar="PATH",
        help="Write classify output as JSON (path_suffixes, suffixes, full_filenames, other_patterns)",
    )
    _ = parser.add_argument("--native", action="store_true", help="Only native/built-in languages")
    _ = parser.add_argument("--ext", action="store_true", help="Only extension languages")
    return cast(SyncArgs, parser.parse_args())


def get_fetch_flags(args: SyncArgs) -> tuple[bool, bool]:
    if not args.native and not args.ext:
        return True, True
    fetch_native = not args.ext or args.native
    fetch_ext = not args.native or args.ext
    return fetch_native, fetch_ext


def fetch_zed_languages(fetch_native: bool, fetch_ext: bool) -> tuple[list[LanguageInfo], list[LanguageInfo]]:
    native_langs = []
    ext_langs = []

    if fetch_native:
        print("Fetching Zed built-in languages...")
        native_langs = get_native_languages()
        print(f"  Found {len(native_langs)} native languages")

    if fetch_ext:
        print("\nFetching Zed extension languages...")
        ext_langs = get_extension_languages()
        print(f"  Found {len(ext_langs)} extension languages")

    return native_langs, ext_langs


def handle_list_mode(args: SyncArgs, native_langs: list[LanguageInfo], ext_langs: list[LanguageInfo]) -> bool:
    if not args.list:
        return False
    all_zed_langs = native_langs + ext_langs
    if args.native and not args.ext:
        print_languages(native_langs, "Zed Native Languages")
    elif args.ext and not args.native:
        print_languages(ext_langs, "Zed Extension Languages")
    else:
        print_languages(native_langs, "Zed Native Languages")
        print_languages(ext_langs, "Zed Extension Languages")
        print(f"\nTotal: {len(all_zed_langs)} languages")
    return True


def update_sources(config: ConfigDict, native_ids: set[str], ext_ids: set[str]) -> int:
    updated = 0
    for lang_id, info in config.items():
        zed_lang = info.get("zed_language", lang_id)

        if zed_lang in native_ids:
            new_source = Source.NATIVE
        elif zed_lang in ext_ids:
            new_source = Source.EXTENSION
        else:
            new_source = Source.EXTRA

        current = info.get("source")
        if current != new_source.value:
            info["source"] = new_source.value
            updated += 1
    return updated


def get_config_detection_tokens(info: LanguageConfig) -> list[str]:
    tokens: list[str] = []
    for key in ("suffixes", "filenames", "extensions"):
        raw_values = info.get(key)
        if not isinstance(raw_values, list):
            continue
        values = cast(list[object], raw_values)
        tokens.extend(value for value in values if isinstance(value, str) and value)
    return tokens


def backfill_missing_detection_tokens(config: ConfigDict, zed_by_lang: dict[str, LanguageInfo]) -> int:
    updated = 0
    for lang_id, info in config.items():
        if get_config_detection_tokens(info):
            continue

        zed_lang = info.get("zed_language", lang_id)
        zed_info = zed_by_lang.get(zed_lang)
        if not zed_info or not zed_info.extensions:
            continue

        info["extensions"] = zed_info.extensions
        updated += 1
    return updated


def add_missing_languages(config: ConfigDict, all_zed_langs: list[LanguageInfo], args: SyncArgs) -> int:
    if not args.add:
        return 0
    added = 0
    existing_zed_langs = {info.get("zed_language", lid) for lid, info in config.items()}

    for lang in all_zed_langs:
        if args.native and not args.ext and lang.source != Source.NATIVE:
            continue
        if args.ext and not args.native and lang.source != Source.EXTENSION:
            continue
        if lang.zed_language in existing_zed_langs:
            continue
        config[lang.id] = {
            "name": lang.name,
            "zed_language": lang.zed_language,
            "extensions": lang.extensions,
            "source": lang.source.value,
        }
        added += 1
    return added


def count_sources(config: ConfigDict) -> dict[str, int]:
    by_source = {Source.NATIVE.value: 0, Source.EXTENSION.value: 0, Source.EXTRA.value: 0}
    for info in config.values():
        by_source[info.get("source", Source.EXTRA.value)] += 1
    return by_source


def print_sync_results(updated: int, backfilled: int, added: int, by_source: dict[str, int], include_added: bool) -> None:
    print("\nResults:")
    print(f"  Updated: {updated} source fields")
    print(f"  Backfilled detections: {backfilled}")
    if include_added:
        print(f"  Added: {added} new languages")
    print("\nBy source:")
    print(f"  Native:    {by_source[Source.NATIVE.value]}")
    print(f"  Extension: {by_source[Source.EXTENSION.value]}")
    print(f"  Extra:     {by_source[Source.EXTRA.value]}")
    print("\nDone! Run `just generate` to regenerate language folders.")


def main() -> int:
    args = parse_arguments()

    # --- FAIL-FAST VALIDATION ---
    validate_sync_environment()

    if args.classify_json:
        args.classify = True

    if args.classify:
        capabilities = collect_extension_capabilities()
        print_extension_capability_report(capabilities)
        if args.classify_json:
            output_path = Path(args.classify_json)
            write_extension_capability_json(capabilities, output_path)
            print(f"\nSaved JSON report to: {output_path}")
        return 0

    fetch_native, fetch_ext = get_fetch_flags(args)
    native_langs, ext_langs = fetch_zed_languages(fetch_native, fetch_ext)

    if handle_list_mode(args, native_langs, ext_langs):
        return 0

    if args.diff:
        compare_with_zed(native_langs, ext_langs)
        return 0

    effective_ext_langs = ext_langs
    skipped_by_syntax: list[LanguageInfo] = []
    if native_langs and ext_langs:
        native_signatures = parse_native_tree_sitter_git_signatures()
        effective_ext_langs, skipped_by_syntax = filter_extensions_reusing_native_syntax(native_signatures, ext_langs)
        if skipped_by_syntax:
            print(
                f"\nFiltered {len(skipped_by_syntax)} extension languages with grammar repositories "
                + "explicitly declared as native in Zed Cargo workspace."
            )

    native_ids = {lang.zed_language for lang in native_langs}
    ext_ids = {lang.zed_language for lang in effective_ext_langs}

    print("\nLoading languages.toml...")
    config = load_config()
    print(f"  Found {len(config)} configured languages")

    zed_by_lang = map_zed_languages(native_langs, effective_ext_langs)
    updated = update_sources(config, native_ids, ext_ids)
    backfilled = backfill_missing_detection_tokens(config, zed_by_lang)
    added = add_missing_languages(config, native_langs + effective_ext_langs, args)

    save_config(config)

    by_source = count_sources(config)
    print_sync_results(updated, backfilled, added, by_source, include_added=args.add)
    return 0


if __name__ == "__main__":
    exit(main())
