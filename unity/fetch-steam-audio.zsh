#!/usr/bin/env bash
# Fetch pinned Steam Audio Unity 4.8.1 from GitHub Releases and unpack it
# into Assets/Plugins/SteamAudio/. Valve publishes the zip; it is not committed.
# https://github.com/ValveSoftware/steam-audio/releases/tag/v4.8.1
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unity="$root/unity"
cache="$root/.cache"
marker="$unity/Assets/Plugins/SteamAudio/Scripts/Runtime/SteamAudioSource.cs"

version='4.8.1'
zip_name="steamaudio_unity_${version}.zip"
url="https://github.com/ValveSoftware/steam-audio/releases/download/v${version}/${zip_name}"
sha256='9b7e3689561670e6b4b8e0c579a2d951bb4a0589f7d46c23bc9df923d62940f0'
package_in_zip='steamaudio_unity/unity/SteamAudio.unitypackage'

file_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

have_plugin() {
  [[ -f "$marker" ]]
}

if have_plugin; then
  echo "Steam Audio already in $unity/Assets/Plugins/SteamAudio"
  exit 0
fi

mkdir -p "$cache" "$unity/Assets/Plugins"
zip_path="$cache/$zip_name"

need_download=1
if [[ -f "$zip_path" ]]; then
  actual="$(file_sha256 "$zip_path")"
  if [[ "$actual" == "$sha256" ]]; then
    need_download=0
  else
    echo "Cached zip hash mismatch; re-downloading."
    rm -f "$zip_path"
  fi
fi

if (( need_download )); then
  echo "Downloading Steam Audio Unity $version…"
  delay=4
  ok=0
  for attempt in 1 2 3 4; do
    if curl -L --fail --retry 0 -o "$zip_path" "$url"; then
      ok=1
      break
    fi
    echo "download failed (attempt $attempt); retry in ${delay}s…"
    sleep "$delay"
    delay=$(( delay * 2 ))
  done
  if (( !ok )); then
    echo "error: could not download $url" >&2
    exit 1
  fi
fi

actual="$(file_sha256 "$zip_path")"
if [[ "$actual" != "$sha256" ]]; then
  echo "error: SHA-256 mismatch for $zip_name" >&2
  echo "  expected $sha256" >&2
  echo "  actual   $actual" >&2
  exit 1
fi

python3 - "$zip_path" "$package_in_zip" "$unity" <<'PY'
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

zip_path, package_name, unity_root = sys.argv[1], sys.argv[2], sys.argv[3]
unity_root = Path(unity_root)

with zipfile.ZipFile(zip_path) as zf:
    payload = zf.read(package_name)

with tempfile.NamedTemporaryFile(suffix=".unitypackage", delete=False) as tmp:
    tmp.write(payload)
    package_path = tmp.name

try:
    with tarfile.open(package_path, "r:gz") as tar:
        grouped = {}
        for member in tar.getmembers():
            parts = [p for p in Path(member.name).parts if p != "."]
            if len(parts) < 2:
                continue
            grouped.setdefault(parts[0], {})[parts[-1]] = member

        written = 0
        for files in grouped.values():
            pathname_member = files.get("pathname")
            if pathname_member is None:
                continue
            handle = tar.extractfile(pathname_member)
            if handle is None:
                continue
            rel = handle.read().decode("utf-8").split("\0", 1)[0].strip().splitlines()[0].strip()
            if not rel.startswith("Assets/"):
                raise SystemExit(f"refusing to extract unexpected path: {rel}")
            dest = unity_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            asset_member = files.get("asset")
            if asset_member is not None and asset_member.isfile():
                blob = tar.extractfile(asset_member)
                if blob is None:
                    raise SystemExit(f"missing asset payload for {rel}")
                dest.write_bytes(blob.read())
            else:
                dest.mkdir(parents=True, exist_ok=True)
            meta_member = files.get("asset.meta")
            if meta_member is not None and meta_member.isfile():
                meta = tar.extractfile(meta_member)
                if meta is not None:
                    Path(str(dest) + ".meta").write_bytes(meta.read())
            written += 1
        print(f"Extracted {written} Steam Audio assets into {unity_root / 'Assets/Plugins/SteamAudio'}")
finally:
    Path(package_path).unlink(missing_ok=True)
PY

if ! have_plugin; then
  echo "error: extract finished but $marker is missing" >&2
  exit 1
fi

echo "Installed Steam Audio $version (gitignored). Open the unity/ folder in Unity Hub."
echo "Do not commit Assets/Plugins/SteamAudio/."
