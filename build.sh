#!/usr/bin/env bash

set -euo pipefail

readonly REPOSITORY="https://github.com/nekorobi-0/nix-router.git"
readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cd "$PROJECT_DIR"

branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "Detached HEADでは更新できません。ブランチをcheckoutしてください。" >&2
  exit 1
fi

echo "Updating $branch from $REPOSITORY"
git pull --ff-only "$REPOSITORY" "$branch"

# Sanitize the flake source before Nix can copy it into the world-readable store.
if command -v python3 >/dev/null 2>&1; then
  prepare_command=("$(command -v python3)" "$PROJECT_DIR/scripts/prepare_xpass_credentials.py")
else
  prepare_command=(nix shell github:NixOS/nixpkgs/nixos-26.05#python3 --command python3 "$PROJECT_DIR/scripts/prepare_xpass_credentials.py")
fi
if [[ "$EUID" -eq 0 ]]; then
  "${prepare_command[@]}"
else
  sudo "${prepare_command[@]}"
fi

rebuild_command=(
  nixos-rebuild
  switch
  --flake
  "path:.#router"
  --impure
)

echo "Applying NixOS configuration"
if [[ "$EUID" -eq 0 ]]; then
  NIXPKGS_ALLOW_UNFREE=1 "${rebuild_command[@]}"
else
  sudo NIXPKGS_ALLOW_UNFREE=1 "${rebuild_command[@]}"
fi
