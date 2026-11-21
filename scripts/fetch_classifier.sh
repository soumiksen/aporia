#!/usr/bin/env bash
# Downloads the exported leak-classifier bundle (model.onnx, tokenizer.json, model_card.json).
#
#   APORIA_CLASSIFIER_URL=https://.../classifier.tar.gz scripts/fetch_classifier.sh [dest]
#
# The URL points at a .tar.gz of the export directory (ml/artifacts/onnx). Host it somewhere
# private (a private Hugging Face repo file, an object store with a signed URL, ...). Set
# APORIA_CLASSIFIER_TOKEN if the URL needs a bearer token. Weights are never committed to git.
# After it finishes, set APORIA_CLASSIFIER_DIR to the destination directory.
set -euo pipefail

dest="${1:-ml/artifacts/onnx}"
if [[ -z "${APORIA_CLASSIFIER_URL:-}" ]]; then
  echo "APORIA_CLASSIFIER_URL is not set (see ml/README.md for where the artifacts live)" >&2
  exit 2
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
args=(--fail --location --silent --show-error --output "$tmp/classifier.tar.gz")
if [[ -n "${APORIA_CLASSIFIER_TOKEN:-}" ]]; then
  args+=(--header "Authorization: Bearer ${APORIA_CLASSIFIER_TOKEN}")
fi
curl "${args[@]}" "$APORIA_CLASSIFIER_URL"

mkdir -p "$dest"
tar -xzf "$tmp/classifier.tar.gz" -C "$dest" --strip-components=0
for f in model.onnx tokenizer.json model_card.json; do
  if [[ ! -f "$dest/$f" ]]; then
    echo "missing $f in the downloaded bundle" >&2
    exit 1
  fi
done
echo "classifier ready in $dest: set APORIA_CLASSIFIER_DIR=$(cd "$dest" && pwd)"
