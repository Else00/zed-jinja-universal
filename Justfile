set shell := ["bash", "-lc"]

mod scripts

# Show help
default:
    @just --list

# === SYNC ===

# Update source fields from Zed repos
[group('sync')]
sync:
    cd scripts && uv run sync_zed_languages.py

# Add new languages from Zed
[group('sync')]
sync-add:
    cd scripts && uv run sync_zed_languages.py --add

# Add only native Zed languages
[group('sync')]
sync-add-native:
    cd scripts && uv run sync_zed_languages.py --add --native

# Add only extension languages
[group('sync')]
sync-add-ext:
    cd scripts && uv run sync_zed_languages.py --add --ext

# === GENERATE ===

# Generate native + extension languages (default)
[group('generate')]
generate:
    cd scripts && uv run generate.py

# Generate only native Zed languages
[group('generate')]
generate-native:
    cd scripts && uv run generate.py --native

# Generate only extension languages
[group('generate')]
generate-ext:
    cd scripts && uv run generate.py --ext

# Generate ALL languages (including extra)
[group('generate')]
generate-all:
    cd scripts && uv run generate.py --all

# === LIST ===

# List Zed native languages
[group('list')]
zed-native:
    cd scripts && uv run sync_zed_languages.py --list --native

# List Zed extension languages
[group('list')]
zed-ext:
    cd scripts && uv run sync_zed_languages.py --list --ext

# List all Zed languages
[group('list')]
zed-list:
    cd scripts && uv run sync_zed_languages.py --list

# === UTILITIES ===

# Sort languages.toml
[group('util')]
sort:
    cd scripts && uv run generate.py --sort

# Compare our config with Zed data
[group('util')]
diff:
    cd scripts && uv run sync_zed_languages.py --diff

# Count languages by source
[group('util')]
count:
    @echo "=== Languages by source ==="
    @echo "Native:    $(grep 'source = \"native\"' languages.toml 2>/dev/null | wc -l | tr -d ' ')"
    @echo "Extension: $(grep 'source = \"extension\"' languages.toml 2>/dev/null | wc -l | tr -d ' ')"
    @echo "Extra:     $(grep 'source = \"extra\"' languages.toml 2>/dev/null | wc -l | tr -d ' ')"
    @echo ""
    @echo "Total:     $(grep '^\[' languages.toml | wc -l | tr -d ' ')"

# === CLEAN ===

# Remove all generated language folders and clear README table
[group('util')]
clean:
    @echo "Removing generated language folders..."
    @find languages -maxdepth 1 -type d -name '*_jinja' -exec rm -rf {} + 2>/dev/null || true
    @echo "Clearing README language table..."
    @sed -i '' '/<!-- LANGUAGES_TABLE_START -->/,/<!-- LANGUAGES_TABLE_END -->/{ /<!-- LANGUAGES_TABLE_START -->/!{ /<!-- LANGUAGES_TABLE_END -->/!d; }; }' README.md
    @echo "Done! Run 'just generate' to regenerate."

# === BUILD VARIANTS ===

# Build base version (native only)
[group('build')]
build-base: sync sort generate-native
    @echo "Built base version (native languages only)"

# Build standard version (native + extension)
[group('build')]
build: sync sort generate
    @echo "Built standard version (native + extension languages)"

# Build full version (all languages including extra)
[group('build')]
build-full: sync sort generate-all
    @echo "Built full version (all languages)"
