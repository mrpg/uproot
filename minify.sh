#!/usr/bin/env bash
# Build minified copies of uproot's own scripts. uproot serves X.min.js instead
# of X.js only while the SHA-256 in its first line matches X.js (see minified()
# in src/uproot/pages.py). Otherwise, it serves X.js.

set -euo pipefail

cd "$(dirname "$0")/src/uproot/_static"

source="uproot.js"

build="${source%.js}.min.js"
sha256="$(python3 -c 'import hashlib, sys; print(hashlib.file_digest(open(sys.argv[1], "rb"), "sha256").hexdigest())' "$source")"

{
    echo "/* Minified from source with SHA-256 $sha256 */"
    npx --yes terser@5 "$source" --compress --mangle --ecma 2020
} > "$build.tmp"

mv "$build.tmp" "$build"
