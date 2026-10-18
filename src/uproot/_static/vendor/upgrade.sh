#!/usr/bin/env bash

set -euxo pipefail

# Keep source maps alongside minified vendor files for debugging.

# Create a temporary backup directory
mkdir _temp/

# Upgrade Alpine.js
# Its npm package ships no license file, so take that from the matching GitHub tag
ALPINE_VERSION="$(curl -fsSL "https://data.jsdelivr.com/v1/packages/npm/alpinejs/resolved?specifier=3" | sed -n -E 's/^[[:space:]]*"version": "([^"]+)".*/\1/p')"
test -n "$ALPINE_VERSION"
mv alpinejs/ _temp/
mkdir alpinejs/
cd alpinejs/
curl -fL \
    -O "https://cdn.jsdelivr.net/npm/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js" \
    -O "https://raw.githubusercontent.com/alpinejs/alpine/v${ALPINE_VERSION}/LICENSE.md"
cd ..

# Bootstrap CSS + JS
# Newest 6.x release, including alphas and betas
BOOTSTRAP_VERSION="$(curl -fsSL -G "https://data.jsdelivr.com/v1/packages/npm/bootstrap/resolved" --data-urlencode "specifier=>=6.0.0-0 <7" | sed -n -E 's/^[[:space:]]*"version": "([^"]+)".*/\1/p')"
test -n "$BOOTSTRAP_VERSION"
mv bootstrap/ _temp/
mkdir bootstrap/
cd bootstrap/
curl -fL \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/LICENSE" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/js/bootstrap.bundle.min.js" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/js/bootstrap.bundle.min.js.map" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/css/bootstrap.min.css" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@${BOOTSTRAP_VERSION}/dist/css/bootstrap.min.css.map"
cd ..

# Upgrade Bootstrap Icons CSS and font files
mv bootstrap-icons/ _temp/
mkdir bootstrap-icons/
cd bootstrap-icons/
curl -fL \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/LICENSE" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/bootstrap-icons.min.css"
mkdir fonts
cd fonts
curl -fL \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff2"
cd ../../

# Upgrade Tabulator
mv tabulator-tables/ _temp/
mkdir tabulator-tables/
cd tabulator-tables/
curl -fL \
    -O "https://unpkg.com/tabulator-tables@6/LICENSE" \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator_bootstrap5.min.css" \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator_bootstrap5.min.css.map" \
    -O "https://unpkg.com/tabulator-tables@6/dist/js/tabulator.min.js" \
    -O "https://unpkg.com/tabulator-tables@6/dist/js/tabulator.min.js.map"
cd ..

# Remove backup directory
rm -rf _temp/
