#!/usr/bin/env bash

set -euxo pipefail

# Create a temporary backup directory
mkdir _temp/

# Upgrade Alpine.js
mv alpinejs/ _temp/
mkdir alpinejs/
cd alpinejs/
curl -L -O "https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"
cd ..

# Bootstrap CSS + JS
mv bootstrap/ _temp/
mkdir bootstrap/
cd bootstrap/
curl -L \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/js/bootstrap.bundle.min.js" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/js/bootstrap.bundle.min.js.map" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css.map"
cd ..

# Upgrade Bootstrap Icons CSS and font files
mv bootstrap-icons/ _temp/
mkdir bootstrap-icons/
cd bootstrap-icons/
curl -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/bootstrap-icons.min.css"
mkdir fonts
cd fonts
curl -L \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff" \
    -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff2"
cd ../../

# Upgrade Tabulator
mv tabulator-tables/ _temp/
mkdir tabulator-tables/
cd tabulator-tables/
curl -L \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator.min.css" \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator.min.css.map" \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator_bootstrap5.min.css" \
    -O "https://unpkg.com/tabulator-tables@6/dist/css/tabulator_bootstrap5.min.css.map" \
    -O "https://unpkg.com/tabulator-tables@6/dist/js/tabulator.min.js" \
    -O "https://unpkg.com/tabulator-tables@6/dist/js/tabulator.min.js.map"
cd ..

# Remove backup directory
rm -rf _temp/