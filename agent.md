# Agent Notes

## Repository overview
- This repository defines a NixOS router image.
- Main configuration is in `router.nix`.
- Flake entrypoint is `flake.nix`.
- ISO build script is `build.sh`.

## Common tasks
- Build router ISO: `./build.sh`
- Direct build command: `nix build .#nixosConfigurations.router.config.system.build.isoImage`

## Output
- Build artifacts are copied to `artifacts/router.iso`.
