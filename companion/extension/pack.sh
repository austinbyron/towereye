#!/bin/sh
# Zip the extension for the Chrome Web Store (upload dist/towereye-extension-<version>.zip).
set -e
cd "$(dirname "$0")"
v=$(python3 -c "import json;print(json.load(open('manifest.json'))['version'])")
mkdir -p dist
rm -f "dist/towereye-extension-$v.zip"
zip -q -r "dist/towereye-extension-$v.zip" manifest.json content.js popup.html popup.js icons
echo "dist/towereye-extension-$v.zip"
