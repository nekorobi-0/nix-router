
#!/usr/bin/env bash
set -e

nix build .#nixosConfigurations.router.config.system.build.isoImage

mkdir -p artifacts

cp -r -L --remove-destination result artifacts 

echo "ISO copied to artifacts/router.iso"