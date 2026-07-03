{ config, lib, pkgs, ... }:

let
  cfg = config.services.nix-router-webui;

  python = pkgs.python3.withPackages (pythonPackages: with pythonPackages; [
    fastapi
    uvicorn
  ]);

  app = pkgs.stdenvNoCC.mkDerivation {
    pname = "nix-router-webui";
    version = "0.2.0";
    src = ./.;

    installPhase = ''
      runHook preInstall
      mkdir -p $out/share/nix-router-webui
      cp backend.py $out/share/nix-router-webui/
      cp -r static $out/share/nix-router-webui/
      runHook postInstall
    '';
  };
in
{
  options.services.nix-router-webui = {
    enable = lib.mkEnableOption "NixOS router Web UI";

    address = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Address on which the Web UI listens.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8080;
      description = "TCP port on which the Web UI listens.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Whether to open the Web UI port in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.nix-router-webui = {
      description = "NixOS Router Web UI";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      path = [ pkgs.iproute2 pkgs.systemd ];

      environment = {
        PYTHONUNBUFFERED = "1";
        NIX_ROUTER_WEBUI_STATIC = "${app}/share/nix-router-webui/static";
      };

      serviceConfig = {
        Type = "simple";
        DynamicUser = true;
        ExecStart = "${python}/bin/uvicorn backend:app --app-dir ${app}/share/nix-router-webui --host ${cfg.address} --port ${toString cfg.port}";
        Restart = "on-failure";
        RestartSec = "2s";

        # The dashboard only needs read access to procfs/sysfs and netlink.
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectHome = true;
        ProtectSystem = "strict";
        ProtectControlGroups = true;
        ProtectKernelModules = true;
        ProtectKernelTunables = true;
        RestrictSUIDSGID = true;
      };
    };

    networking.firewall.allowedTCPPorts =
      lib.optionals cfg.openFirewall [ cfg.port ];
  };
}
