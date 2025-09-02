#!/usr/bin/env bash

set -euxo pipefail

# Upgrade Alpine.js and Bootstrap CSS + JS
rm -f alpine.min.js bootstrap.bundle.min.js* bootstrap.min.css*
curl -sS -O "https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/js/bootstrap.bundle.min.js"
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/js/bootstrap.bundle.min.js.map"
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css"
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css.map"
mv cdn.min.js alpine.min.js

# Upgrade Bootstrap Icons CSS
rm -f bootstrap-icons.min.css
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/bootstrap-icons.min.css"

# Upgrade Bootstrap Icons font files
rm -rf fonts
mkdir fonts
cd fonts

curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff"
curl -sS -O "https://cdn.jsdelivr.net/npm/bootstrap-icons@1/font/fonts/bootstrap-icons.woff2"
