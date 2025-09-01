#!/usr/bin/env bash

set -euo pipefail

# Detect OS
OS=$(uname)

# Function to download one or more files
download() {
    # Loop over arguments two at a time (url, outfile)
    while [[ $# -gt 0 ]]; do
        url="$1"
        if [[ "$OS" == "Darwin" ]]; then
            # macOS: use curl (silent, show errors, output to file)
            echo "curl -sS -O $url"
            curl -sS -O "$url"
        else
            # Linux: use wget (quiet, output to file)
            wget -q -O "$url"
            echo "wget -q -O $url"
        fi
        shift 1
    done
}

# Upgrade Alpine.js and Bootstrap CSS + JS
rm -f alpine.min.js bootstrap.bundle.min.js* bootstrap.min.css*
download \
     "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js" \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/js/bootstrap.bundle.min."{js,js.map} \
     "https://cdn.jsdelivr.net/npm/bootstrap@5.x.x/dist/css/bootstrap.min."{css,css.map}
mv cdn.min.js alpine.min.js
echo "Alpine.js and Bootstrap CSS + JS complete"

# Upgrade Bootstrap Icons CSS
cd ../fonts/bootstrap-icons-1.x.x
rm -f bootstrap-icons.min.css
download \
     "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.x.x/font/bootstrap-icons.min.css"
echo "Bootstrap Icons CSS complete"

# Upgrade Bootstrap Icons font files
cd fonts
rm -f bootstrap-icons.woff*
download \
     "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.x.x/font/fonts/bootstrap-icons."{woff,woff2}
echo "Bootstrap Icons font files complete"

# Finish
echo "Upgrade complete"