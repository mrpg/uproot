#!/usr/bin/env bash

set -euo pipefail

# Upgrade Alpine.js and Bootstrap CSS + JS
rm -f alpine.min.js  bootstrap.bundle.min.js  bootstrap.bundle.min.js.map  bootstrap.min.css  bootstrap.min.css.map
wget -q "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/js/bootstrap.bundle.min."{js,js.map} \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/css/bootstrap.min."{css,css.map}
mv cdn.min.js alpine.min.js

# Upgrade Bootstrap Icons CSS
cd ../fonts/bootstrap-icons-1.x.x
rm -f bootstrap-icons.min.css
wget -q "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.x.x/font/bootstrap-icons.min.css"

# Upgrade Bootstrap Icons font files
cd fonts
rm -f bootstrap-icons.woff  bootstrap-icons.woff2
wget -q "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.x.x/font/fonts/bootstrap-icons."{woff,woff2}

# Finish
echo OK