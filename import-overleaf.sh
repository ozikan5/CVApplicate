#!/usr/bin/env bash
# Import a CV from an Overleaf "Download > Source" zip (or a bare .tex file).
#
# Overleaf's git bridge is a premium feature, so on a free plan the round-trip is
# manual. This script makes the inbound half one command.
#
# Usage:
#   ./import-overleaf.sh ~/Downloads/MyProject.zip      # from a source zip
#   ./import-overleaf.sh ~/Downloads/resume.tex         # from a single .tex
#
# It copies the main .tex to cv.tex on the CURRENT branch, leaving it uncommitted
# so you can review the diff before committing.

set -euo pipefail

SRC="${1:-}"
if [[ -z "$SRC" ]]; then
    echo "usage: $0 <path-to-overleaf-zip-or-tex>" >&2
    exit 1
fi

if [[ ! -e "$SRC" ]]; then
    echo "error: no such file: $SRC" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [[ -n "$(git status --porcelain cv.tex)" ]]; then
    echo "error: cv.tex has uncommitted changes on branch '$(git branch --show-current)'." >&2
    echo "Commit or discard them first so this import doesn't clobber your work." >&2
    exit 1
fi

case "$SRC" in
    *.tex)
        cp "$SRC" cv.tex
        echo "imported $(basename "$SRC") -> cv.tex"
        ;;
    *.zip)
        TMP="$(mktemp -d)"
        trap 'rm -rf "$TMP"' EXIT
        unzip -q "$SRC" -d "$TMP"

        # Find the main .tex: the one containing \documentclass.
        MAIN=""
        while IFS= read -r f; do
            if grep -lq '\\documentclass' "$f" 2>/dev/null; then
                MAIN="$f"
                break
            fi
        done < <(find "$TMP" -name '*.tex' -type f | sort)

        if [[ -z "$MAIN" ]]; then
            echo "error: no .tex containing \\documentclass found in $SRC" >&2
            exit 1
        fi

        cp "$MAIN" cv.tex
        echo "imported $(basename "$MAIN") -> cv.tex"

        # Carry over any non-.tex assets (logos, .cls, .sty, images) it may need.
        ASSETS=0
        while IFS= read -r f; do
            base="$(basename "$f")"
            if [[ ! -e "$base" ]]; then
                cp "$f" .
                echo "  + asset: $base"
                ASSETS=$((ASSETS + 1))
            fi
        done < <(find "$TMP" -type f \( -name '*.cls' -o -name '*.sty' -o -name '*.png' -o -name '*.jpg' -o -name '*.pdf' \))
        [[ $ASSETS -gt 0 ]] && echo "  ($ASSETS asset(s) copied)"
        ;;
    *)
        echo "error: expected a .zip or .tex file, got: $SRC" >&2
        exit 1
        ;;
esac

echo
echo "branch: $(git branch --show-current)"
echo "review the change with:  git diff cv.tex"
