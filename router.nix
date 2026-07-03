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
      tables.nat = {
        family = "ip";
        content = ''
          chain postrouting {
            type nat hook postrouting priority srcnat;
            oifname "ip6tnl1" masquerade
          }
          chain prerouting {
            type nat hook prerouting priority dstnat;
            iifname "ip6tnl1" tcp dport 25568 dnat to 192.168.0.105:25565
            iifname "ip6tnl1" tcp dport 25566 dnat to 192.168.0.103:25565
            iifname "ip6tnl1" tcp dport 25567 dnat to 192.168.0.110:25565
            iifname "ip6tnl1" tcp dport 80 dnat to 192.168.0.101:8352
          }
        '';
      };
      tables.filter = {
        family = "ip";
        content = ''
          chain forward {
            type filter hook forward priority filter;
            iifname "ip6tnl1" oifname "eth0" tcp dport 25565 ct state new accept
            ct state established,related accept
          }
        '';
      };
    };
    firewall = {
      enable = true;
      trustedInterfaces = [ "enp2s0" "enp3s0" ];
      allowedTCPPorts = [
        25566 25567 25568 80
      ];

        allowedUDPPorts = [
      ];
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
      openFirewall = true;
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
