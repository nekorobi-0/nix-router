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
      cp ${../generate_snat_config.py} $out/share/nix-router-webui/generate_snat_config.py
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

    configDirectory = lib.mkOption {
      type = lib.types.str;
      default = "/root/nix-router";
      description = "Writable directory containing general_config.toml and snat-config.nix.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.nix-router-webui = {
      description = "NixOS Router Web UI";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      path = [ pkgs.iproute2 pkgs.systemd pkgs.frr ];

      environment = {
        PYTHONUNBUFFERED = "1";
        NIX_ROUTER_WEBUI_STATIC = "${app}/share/nix-router-webui/static";
        NIX_ROUTER_SNAT_CONFIG = "${cfg.configDirectory}/general_config.toml";
        NIX_ROUTER_SNAT_OUTPUT = "${cfg.configDirectory}/snat-config.nix";
      };

      serviceConfig = {
        Type = "simple";
        User = "root";
        SupplementaryGroups = [ "frrvty" ];
        ExecStart = "${python}/bin/uvicorn backend:app --app-dir ${app}/share/nix-router-webui --host ${cfg.address} --port ${toString cfg.port}";
        Restart = "on-failure";
        RestartSec = "2s";

        # Keep the host read-only except for the two generated configuration files.
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectHome = "read-only";
        ProtectSystem = "strict";
        ReadWritePaths = [ cfg.configDirectory ];
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
