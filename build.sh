
#!/usr/bin/env bash
set -e

nix build .#nixosConfigurations.router.config.system.build.isoImage

mkdir -p artifacts

cp -r --remove-destination result artifacts/router.iso

echo "ISO copied to artifacts/router.iso"