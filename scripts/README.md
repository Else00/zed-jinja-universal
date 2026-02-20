# Scripts - Internal Documentation

Python scripts for managing jinja-universal. Run via `uv run <script>.py` from this directory.

## Architecture

```
scripts/
├── pyproject.toml          # Python project config (uv)
├── common.py               # Shared: Source enum, paths, validation, config I/O
├── generate.py             # Generates language folders from TOML
├── sync_zed_languages.py   # Syncs with Zed's supported languages
└── justfile                # Dev tasks (format, lint, typecheck)
```

## common.py

Shared module with:

- **Paths**: `REPO_ROOT`, `CONFIG_PATH`, `LANGUAGES_DIR`, `TEMPLATES_DIR`, etc.
- **Source enum**: `StrEnum` with `NATIVE`, `EXTENSION`, `EXTRA`
- **Validation**: `validate_generate_environment()`, `validate_sync_environment()`
- **Config I/O**: `load_config()`, `load_and_validate_config()`, `save_config()`
- **Fail-fast**: `fail()`, `fail_many()` for clear error reporting

## generate.py

Generates language folders from `languages.toml`.

### Flow

1. **Validate environment** - Check templates, directories, config exist
2. **Load config** - Parse and validate `languages.toml`
3. **Filter by source and detection** - Based on `--native`, `--ext`, `--all` flags, then exclude languages with no
   automatic detection tokens (`extensions`, `suffixes`, or `filenames`)
4. **Delete old folders** - Remove folders for languages not in selection
5. **Generate folders** - Create `{lang}_jinja/` with config.toml, injections.scm, highlights
6. **Update metadata files** - Regenerate README table/mode metadata and update `extension.toml` language count

### Generated Files

For each language:
- `config.toml` - From `templates/config.toml.template`
- `injections.scm` - From `templates/injections.scm.template`
- `highlights.scm`, `brackets.scm`, `indents.scm` - Copied from `languages/jinja2/`

## sync_zed_languages.py

Syncs with Zed's supported languages via git clones.

### Flow

1. **Validate environment** - Check git available
2. **Clone/update repos** - Shallow clones to `../.zed-cache/`
3. **Get native languages** - Parse `crates/languages/src/*/config.toml`
4. **Get extension languages** - Parse `.gitmodules`, fetch `extension.toml` from each
5. **Update source field** - Set `native`, `extension`, or `extra` in config
6. **Optionally add new languages** - With `--add` flag
7. **Syntax policy filter for sync** - Excludes extension languages that reuse a native syntax grammar
   (for example `docker-compose` reusing `tree-sitter-yaml`)

### Capability Report Mode

Use `--classify` to analyze extension capabilities without modifying `languages.toml`.
It reports how many extensions expose grammars, language servers, both, or neither, plus shared grammar repositories.
Use `--classify-json <path>` to write per-extension details, including `path_suffixes`, `suffixes`, `full_filenames`, and
`other_patterns`.

### Language Detection

Extension is a "language extension" if `extension.toml` contains:
```toml
[grammars.language_name]
repository = "..."
commit = "..."
```

This is the ONLY reliable indicator. Themes/icons/snippets are excluded.

### Cache

Repos cloned to `../.zed-cache/` (sibling directory, gitignored):
- `.zed-cache/zed/` - Main repo (sparse checkout of `crates/languages/src/`)
- `.zed-cache/extensions/` - Extensions repo

## Fail-Fast Design

Both scripts validate ALL requirements before making changes:

```python
def validate_generate_environment() -> None:
    errors = []
    if not TEMPLATES_DIR.exists():
        errors.append(f"Templates directory missing: {TEMPLATES_DIR}")
    # ... more checks ...
    if errors:
        fail_many(errors)
```

If Zed's repo structure changes, scripts fail with clear messages instead of silently breaking.

## Dependencies

- Python 3.13+
- `git` in PATH
- `uv` for running scripts
- Internet (for sync only)
