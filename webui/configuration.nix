{ ... }:

{
  imports = [ ./module.nix ];

  # This file contains settings for this router. The service implementation
  # itself lives in module.nix so it can be reused from another host.
  services.nix-router-webui = {
    enable = true;
    address = "172.16.1.1";
    port = 8080;
    configDirectory = "/root/nix-router";
  };
}
