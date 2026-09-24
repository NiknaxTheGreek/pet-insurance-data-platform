#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-.estuary-keys}"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"

PRIVATE_KEY="$OUT_DIR/rsa_key.p8"
PUBLIC_KEY="$OUT_DIR/rsa_key.pub"
PUBLIC_BODY="$OUT_DIR/rsa_public_key_body.txt"

if [[ -e "$PRIVATE_KEY" || -e "$PUBLIC_KEY" || -e "$PUBLIC_BODY" ]]; then
  echo "Refusing to overwrite existing key material in $OUT_DIR" >&2
  exit 1
fi

openssl genrsa 2048   | openssl pkcs8 -topk8 -inform PEM -out "$PRIVATE_KEY" -nocrypt
chmod 600 "$PRIVATE_KEY"

openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"

awk 'BEGIN{ORS=""} !/BEGIN PUBLIC KEY|END PUBLIC KEY/ {gsub(/\r/,""); printf "%s",$0} END{print ""}'   "$PUBLIC_KEY" > "$PUBLIC_BODY"

echo "Created:"
echo "  private key: $PRIVATE_KEY  (store as GitHub secret ESTUARY_SNOWFLAKE_PRIVATE_KEY; never commit)"
echo "  public key:  $PUBLIC_KEY"
echo "  public body: $PUBLIC_BODY  (paste only this value into the Snowflake bootstrap placeholder)"
echo
echo "Private-key contents were not printed."
