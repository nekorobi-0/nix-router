# configuration.nix
{ modulesPath, config, pkgs, lib, ... }:

let
  wan = "enp1s0";
  lan = "enp2s0";
  lan2 = "enp3s0";
  xpass = import ./xpass-env.nix;
in
{
  imports = [
    ./hardware-configuration.nix
    ./snat-config.nix
    ./ssh-config.nix
    ./webui/configuration.nix
  ];
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
    noto-fonts-cjk-sans dejavu_fonts ipafont kochi-substitute
  ];

  # ── networking ───────────────────────────────────────────────────────
  services.resolved.enable = true;
  networking = {
    hostName = "router";
    useNetworkd = true;
    useDHCP = false;
    nftables ={
      enable = true;
    };
    firewall = {
      enable = true;
      trustedInterfaces = [ "enp2s0" "enp3s0" ];
    };
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
      address = [ xpass.xpassIPv6Prefix];
      networkConfig = {
        Tunnel = "ip6tnl1";
        DHCP         = "ipv6";
        IPv6AcceptRA = true;
      };
      ipv6AcceptRAConfig.DHCPv6Client = "always";
      dhcpV6Config.RapidCommit = false;
    };

    networks."20-lan" = {
      matchConfig.Name = lan;
      address = [ "172.16.1.1/24" ];
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
    networks."40-lan2" = {
      matchConfig.Name = lan2;
      address = [ "192.168.100.1/30" ];
    };
    # ── IPIP6 トンネル構成 ───────────────────────────────────────────────
    netdevs."30-ip6tnl1" = {
      netdevConfig = {
        Name = "ip6tnl1";
        Kind = "ip6tnl";
      };
      tunnelConfig = {
        Remote       = xpass.xpassTunnelRemote;
        Local        = xpass.xpassIPv6Prefix;
        Mode         = "ipip6";
        EncapsulationLimit = "none";
      };
    };

    networks."30-ip6tnl1" = {
      matchConfig.Name = "ip6tnl1";
      address = [ xpass.xpassIPv4Fixed ];
      routes = [
        { routeConfig.Destination = "0.0.0.0/0"; }
      ];
    };
  };
  # ── DHCP サーバ構成 ───────────────────────────────────────────────
  services.dnsmasq = {
    enable = true;

    settings = {
      interface = "${lan}";
      no-dhcp-interface="${wan}";
      domain-needed = true;
      dhcp-range = "172.16.1.11,172.16.1.99,12h";
      dhcp-option = [
        "option:router,172.16.1.1"
        "option:dns-server,172.16.1.1"
      ];
      port = 0;
    };
  };
  # ── BGP ───────────────────────────────────────────────────────────────
  services.frr = {
    bgpd.enable = true;

    config = ''
      route-map ALLOW permit 10
      router bgp 65000
        bgp router-id 192.168.100.1

        neighbor 192.168.100.2 remote-as 65100
        neighbor 192.168.100.2 route-map ALLOW in
        neighbor 192.168.100.2 route-map ALLOW out
        address-family ipv4 unicast
          neighbor 192.168.100.2 activate
          network 0.0.0.0/0
        exit-address-family
    '';
  };
  # ── DDNS 更新サービス ────────────────────────────────────────────────
  systemd.services.xpass-ddns = {
    description = "Xpass DDNS updater";
    after  = [ "network-online.target" ];
    wants  = [ "network-online.target" ];
    serviceConfig = {
      Type             = "oneshot";
      RemainAfterExit  = false;
      ExecStart = pkgs.writeShellScript "xpass-ddns-update" ''
        ${pkgs.curl}/bin/curl -k \
          "https://${xpass.xpassDDNSUser}:${xpass.xpassDDNSPassword}@${xpass.xpassDdnsDomain}/cgi-bin/ddns_api.cgi?d=${xpass.xpassFQDN}&p=${xpass.xpassDDNSPassword}&a=${xpass.xpassIPv6Prefix}&u=${xpass.xpassDDNSId}"
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
  services.prometheus.exporters.node = {
      enable = true;
      port = 9100;
  };
  # ── packages ─────────────────────────────────────────────────────────
  environment.systemPackages = with pkgs; [
    nano vim git curl wget htop btop tmux prometheus
    tcpdump iperf3 mtr traceroute dig bind nmap ndisc6
    iproute2 nftables ethtool bridge-utils vlan conntrack-tools frr
    pciutils usbutils lm_sensors smartmontools
    sysstat iotop iftop
    zstd zip unzip
    jq yq-go
    docker docker-compose
    fastfetch ookla-speedtest
  ];

  # ── misc ─────────────────────────────────────────────────────────────
  virtualisation.docker.enable = true;
  time.timeZone = "Asia/Tokyo";
  system.stateVersion = "26.05";
}
