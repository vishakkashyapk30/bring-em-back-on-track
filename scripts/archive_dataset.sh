#!/usr/bin/env bash
# Compress the released dataset into two archives so data/raw can be deleted and restored later.
#   maple_release_text.tar.zst : every table, label, schema, transcript and policy document (zstd)
#   maple_voice_flac.tar       : the 2,000 call recordings re-encoded from WAV to lossless FLAC
# Restore with scripts/restore_dataset.sh. Usage: scripts/archive_dataset.sh [output_dir]
set -euo pipefail
SRC="${RAW_DIR:-data/raw/maple_collections_release}"
OUT="${1:-$HOME/maple_archive}"
mkdir -p "$OUT/flac"
echo "encoding recordings to FLAC"
ls "$SRC/files/voice"/*.wav | xargs -P "$(nproc)" -I{} sh -c 'ffmpeg -loglevel error -y -i "{}" -compression_level 8 "'"$OUT"'/flac/$(basename "{}" .wav).flac"'
echo "compressing tables and text"
tar -cf - -C "$SRC" --exclude=./files/voice . | zstd -12 -T0 -q -o "$OUT/maple_release_text.tar.zst"
echo "packing recordings"
tar -cf "$OUT/maple_voice_flac.tar" -C "$OUT/flac" .
rm -rf "$OUT/flac"
( cd "$OUT" && sha256sum maple_release_text.tar.zst maple_voice_flac.tar > SHA256SUMS )
( cd "$SRC" && find . -type f -not -path "./files/voice/*" -print0 | sort -z | xargs -0 sha256sum ) > "$OUT/source_file_checksums.txt"
du -sh "$OUT"/*
