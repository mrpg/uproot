#!/usr/bin/env bash

set -euo pipefail

rm -f alpine.min.js  bootstrap.bundle.min.js  bootstrap.bundle.min.js.map  bootstrap.min.css  bootstrap.min.css.map

wget -q "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/js/"{bootstrap.bundle.min.js,bootstrap.bundle.min.js.map} \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/css/"{bootstrap.min.css,bootstrap.min.css.map}

mv cdn.min.js alpine.min.js

echo OK