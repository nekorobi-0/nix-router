# configuration.nix
{ modulesPath, config, pkgs, lib, ... }:

let
  wan = "enp1s0";
  lan = "enp2s0";
  envFile = "/etc/xpass.env";
in
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
  ];
  environment.etc."xpass.env" = {
    source = ./xpass.env;
    mode = "0600";
  };
  # ── boot ────────────────────────────────────────────────────────────
  boot.loader.systemd-boot.enable = true;

  boot.kernelModules = [
    "tcp_bbr" "sch_cake"
    "mlx4_core" "mlx4_en" "ixgbe"
    "ip6_tunnel" "ip6tnl" "sit"
    "nf_nat" "nft_chain_nat"
  ];

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward"             = 1;
    "net.ipv6.conf.all.forwarding"    = 1;
    "net.core.default_qdisc"          = "cake";
    "net.ipv4.tcp_congestion_control" = "bbr";
  };

  # ── fonts ────────────────────────────────────────────────────────────
  fonts.packages = with pkgs; [
    noto-fonts-cjk-jp dejavu_fonts ipafont kochi-substitute
  ];

  # ── networking ───────────────────────────────────────────────────────
  services.resolved.enable = true;
  networking = {
    hostName = "router";
    useNetworkd = true;
    useDHCP = false;
    nftables.enable = true;
    firewall.enable = true;
    enableIPv6 = true;
    networkmanager.enable = lib.mkForce false;
    nameservers = [
      "2001:4860:4860::8888"
      "8.8.8.8"
    ];
  };

  systemd.services.systemd-networkd.environment.SYSTEMD_LOG_LEVEL = "debug";

  systemd.services.ethtool-wan = {
    description = "Disable checksum offload on WAN";
    after    = [ "network-pre.target" ];
    before   = [ "systemd-networkd.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig.Type = "oneshot";
    script = ''
      ${pkgs.ethtool}/bin/ethtool -K ${wan} rx off tx off
    '';
  };

  systemd.network = {
    enable = true;
    config.dhcpV6Config.DUIDType = "link-layer";

    networks."10-wan" = {
      matchConfig.Name = wan;
      networkConfig = {
        DHCP         = "ipv6";
        IPv6AcceptRA = true;
      };
      ipv6AcceptRAConfig.DHCPv6Client = "always";
      dhcpV6Config.RapidCommit = false;
    };

    networks."20-lan" = {
      matchConfig.Name = lan;
      address = [ "192.168.1.1/24" ];
      networkConfig = {
        IPv6SendRA           = true;
        DHCPPrefixDelegation = true;
      };
      dhcpPrefixDelegationConfig = {
        UplinkInterface = wan;
        SubnetId        = 1;
        Announce        = true;
      };
    };
  };

  # ── DDNS 更新サービス ────────────────────────────────────────────────
  systemd.services.xpass-ddns = {
    description = "Xpass DDNS updater";
    after  = [ "network-online.target" ];
    wants  = [ "network-online.target" ];
    serviceConfig = {
      Type             = "oneshot";
      RemainAfterExit  = false;
      EnvironmentFile  = envFile;
      ExecStart = pkgs.writeShellScript "xpass-ddns-update" ''
        ${pkgs.curl}/bin/curl -k \
          "https://$XPASS_DDNS_USER:$XPASS_DDNS_PASS@$XPASS_DDNS_DOMAIN/cgi-bin/ddns_api.cgi?d=$XPASS_FQDN&p=$XPASS_DDNS_PASSWORD&a=$XPASS_IPV6_PREFIX&u=$XPASS_DDNS_ID"
      '';
    };
  };

  systemd.timers.xpass-ddns = {
    description = "Xpass DDNS periodic update";
    wantedBy    = [ "timers.target" ];
    timerConfig = {
      OnBootSec       = "30s";
      OnUnitActiveSec = "4min";
      Persistent      = true;
    };
  };

  # ── IPIP6 トンネル構成 ───────────────────────────────────────────────
  systemd.services.xpass-tunnel = {
    description = "Xpass IPIP6 tunnel";
    after    = [ "network-online.target" "xpass-ddns.service" ];
    wants    = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type            = "oneshot";
      RemainAfterExit = true;
      EnvironmentFile = envFile;
      ExecStart = pkgs.writeShellScript "xpass-tunnel-up" ''
        ${pkgs.iproute2}/bin/ip -6 addr add "$XPASS_IPV6_PREFIX" dev ${wan} || true

        ${pkgs.iproute2}/bin/ip -6 tunnel add ip6tnl1 mode ipip6 \
          remote "$XPASS_TUNNEL_REMOTE" \
          local  "$XPASS_IPV6_PREFIX"   \
          encaplimit none               \
          dev ${wan}                    || true

        ${pkgs.iproute2}/bin/ip link  set ip6tnl1 up                       || true
        ${pkgs.iproute2}/bin/ip addr  add "$XPASS_IPV4_FIXED" dev ip6tnl1 || true
        ${pkgs.iproute2}/bin/ip route add default              dev ip6tnl1 || true
      '';
      ExecStop = pkgs.writeShellScript "xpass-tunnel-down" ''
        ${pkgs.iproute2}/bin/ip link del ip6tnl1 || true
      '';
    };
  };

  # ── SSH ──────────────────────────────────────────────────────────────
  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin        = "yes";
      PasswordAuthentication = false;
    };
  };

  # ── SSH authorized keys ───────────────────────────────────────────────
  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC3F4EyORHK0dc+1o/fbY8T3t9XnsFO5DJ0b7T5DWo2p8RpYAEURtzg2N4kcwlD20n68FAmj3YfQXJhSg4dl5SbTB3VgYn8EWawFIp2p5o2o/wI8e8tIYFKzetkjFRb37tvJsHNdhIfrDYcOxUE9j8IcZSBYv8rmdjCKLzXRfLNt7QSz3WbRw5cS1PAN7MfUf/ygUxi/9qEzMW4sRBFcDfr9AelrUpglMnCO7OWk9oLZ0GxkwYcDmm3UX9UfIrlhbks2P7sxjTFE/jvGd6zKpPgcnsZW5EBogXbGlgVViRdB+QgIGm0XJ9zohG/Kz1kkw5jxTu9i4cTs14TMILQ3QL5M9J0jiEhX/etxJCpszyhkk0b7a1+IsCkCmqZtWW+ZmaV9wA8lQXdyJrNwum9vRtkDxUIhP3akV/zgCMzOfW3vaMo00uvivy8IY73sWkAVeaToRd9ao7Y4O0WgRaJPHupFogI45nGT9F/ir6BIjfwBY2tmN1CcAC9EHcKWwuWpeHCazS+MdvLeG2H2+fi0JqthqDHyg1sVALSNYne44yEGpHtCl4J+XLtfqamFM1hGi/GwiPv5K0at1tG3jgFCGVhgoz9CMTATqYeFfPR/gfX2EJ9PsMylxSBNW0Z8/e8Hu67xzyZ29nxNx2caFc20UbJXCwcU8zHn+499igq0YML/w== user@DESKTOP"
  ];

  # ── packages ─────────────────────────────────────────────────────────
  environment.systemPackages = with pkgs; [
    nano vim git curl wget htop btop tmux
    tcpdump iperf3 mtr traceroute dig bind nmap ndisc6
    iproute2 nftables ethtool bridge-utils vlan conntrack-tools frr
    pciutils usbutils lm_sensors smartmontools
    sysstat iotop iftop
    zstd zip unzip
    jq yq-go
    docker docker-compose
    fastfetch
  ];

  # ── misc ─────────────────────────────────────────────────────────────
  services.frr.bgpd.enable = true;
  virtualisation.docker.enable = true;
  time.timeZone = "Asia/Tokyo";
  system.stateVersion = "26.05";
}