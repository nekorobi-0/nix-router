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
