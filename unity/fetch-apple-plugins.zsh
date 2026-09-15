#!/bin/zsh
# Build Apple.Core + Apple.PHASE tarballs from pinned upstream source.
# Apple does not publish these as GitHub Release assets.
# https://github.com/apple/unityplugins
set -euo pipefail

root="${0:A:h:h}"
packages="$root/unity/Packages"
cache="$root/.cache/apple-unityplugins"

# Last main commit before 2026-09-09; matches Core 3.2.0 + PHASE 1.2.7
# used by this project. Do not float on main.
rev='17f601bf68fc9867ee4c4f0f14870ca55f28c798'
core_tgz='com.apple.unityplugin.core-3.2.0.tgz'
phase_tgz='com.apple.unityplugin.phase-1.2.7.tgz'
repo='https://github.com/apple/unityplugins.git'

have_expected() {
  [[ -f "$packages/$core_tgz" && -f "$packages/$phase_tgz" ]]
}

if have_expected; then
  print "Apple plug-in tarballs already in $packages"
  exit 0
fi

for cmd in git python3 npm xcodebuild; do
  if ! command -v "$cmd" >/dev/null; then
    print "error: $cmd is required to build Apple Unity plug-ins" >&2
    print "Install Xcode, Python 3, and npm, then re-run." >&2
    exit 1
  fi
done

mkdir -p "$packages" "$cache"
if [[ ! -d "$cache/.git" ]]; then
  print "Cloning apple/unityplugins…"
  git clone "$repo" "$cache"
fi

print "Checking out $rev…"
git -C "$cache" fetch --quiet origin
git -C "$cache" checkout --quiet --detach "$rev"

print "Building Apple.Core and Apple.PHASE (Release)…"
(
  cd "$cache"
  python3 build.py -p Core PHASE -bc Release
)

built="$cache/Build"
if [[ ! -f "$built/$core_tgz" || ! -f "$built/$phase_tgz" ]]; then
  print "error: expected $core_tgz and $phase_tgz under $built" >&2
  print "Upstream versions changed. Update this script and Packages/manifest.json." >&2
  ls -1 "$built"/*.tgz 2>/dev/null || true
  exit 1
fi

cp "$built/$core_tgz" "$built/$phase_tgz" "$packages/"
print "Installed:"
print "  $packages/$core_tgz"
print "  $packages/$phase_tgz"
print "Open the unity/ folder in Unity Hub. Do not commit these tarballs or Assets/Apple Plug-In Support/."
