#!/usr/bin/env bash
# Joern ile bir kaynak ağacını normalize 'kod indeks' JSON'una indeksler.
# Kullanım: scripts/joern_index.sh <src_root> <out.json>
set -euo pipefail

SRC="${1:?kullanım: joern_index.sh <src_root> <out.json>}"
OUT="${2:?kullanım: joern_index.sh <src_root> <out.json>}"

JOERN_HOME="${JOERN_HOME:-$HOME/joern/joern-cli}"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}"
export PATH="/opt/homebrew/bin:$JAVA_HOME/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_ABS="$(cd "$SRC" && pwd)"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

"$JOERN_HOME/joern-parse" "$SRC_ABS" --output "$WORK/cpg.bin" >/dev/null
# workspace'in temp'e düşmesi için WORK içinde çalıştır
( cd "$WORK" && "$JOERN_HOME/joern" --script "$SCRIPT_DIR/export_cpg.sc" \
    --param cpgFile="$WORK/cpg.bin" \
    --param outFile="$OUT_ABS" \
    --param root="$SRC" >/dev/null )

echo "indekslendi -> $OUT"
