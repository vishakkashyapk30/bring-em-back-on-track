#!/usr/bin/env bash
# Restore the dataset archived by scripts/archive_dataset.sh into data/raw/maple_collections_release.
# Usage: scripts/restore_dataset.sh [archive_dir]   (recordings are decoded from FLAC back to the original WAV format)
set -euo pipefail
IN="${1:-$HOME/maple_archive}"
DEST="${RAW_DIR:-data/raw/maple_collections_release}"
# The voice archive may be stored whole or as maple_voice_flac.tar.part-NN files (large single uploads to Drive stall).
if [ -f "$IN/maple_voice_flac.tar" ]; then VOICE="$IN/maple_voice_flac.tar"; else
  ( cd "$IN" && sha256sum -c SHA256SUMS.parts )
  VOICE="$(mktemp)"; cat "$IN"/maple_voice_flac.tar.part-* > "$VOICE"
fi
( cd "$IN" && grep maple_release_text SHA256SUMS | sha256sum -c - )
mkdir -p "$DEST/files/voice"
zstd -dc "$IN/maple_release_text.tar.zst" | tar -xf - -C "$DEST"
tmp="$(mktemp -d)"; tar -xf "$VOICE" -C "$tmp"
ls "$tmp"/*.flac | xargs -P "$(nproc)" -I{} sh -c 'ffmpeg -loglevel error -y -i "{}" "'"$DEST"'/files/voice/$(basename "{}" .flac).wav"'
rm -rf "$tmp"
echo "restored to $DEST"
