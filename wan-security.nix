{ wan, lanInterfaces }:
{ lib, ... }:
{
  # FORWARD is owned by wan-guard; the standard NixOS firewall still owns INPUT.
  networking.firewall.filterForward = false;
  networking.nftables.tables.wan-guard = {
    family = "inet";
    content = lib.replaceStrings
      [ "@WAN@" "@LAN_INTERFACES@" ]
      [ wan (lib.concatMapStringsSep ", " (name: ''"${name}"'') lanInterfaces) ]
      (builtins.readFile ./wan-firewall.nft);
  };

  # Avoid Docker imposing a second default-drop policy on this router's LAN traffic.
  virtualisation.docker.daemon.settings.ip-forward-no-drop = true;
}
