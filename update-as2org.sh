#!/bin/bash
set -euo pipefail

DEST_DIR="/opt/bgp-report/data"
DEST_FILE="${DEST_DIR}/as2org.txt"
TMP_GZ="$(mktemp)"
TMP_TXT="$(mktemp)"

mkdir -p "$DEST_DIR"

curl -fsSL \
  https://data.caida.org/datasets/as-organizations/latest.as-org2info.txt.gz \
  -o "$TMP_GZ"

gunzip -c "$TMP_GZ" > "$TMP_TXT"
mv "$TMP_TXT" "$DEST_FILE"
rm -f "$TMP_GZ"

echo "Aggiornato: $DEST_FILE"
