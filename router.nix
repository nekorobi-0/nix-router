{modulesPath, config, pkgs, ... }:

{
    imports = [
        "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
    ];
    boot.loader.systemd-boot.enable = true;
    fonts.packages = with pkgs; [
        noto-fonts-cjk-jp # 日本語表示用
        dejavu_fonts      # 基本的な記号・文字用
        ipafont           # IPAフォント
        kochi-substitute  # 東芝フォント等
    ];
    networking = {
        hostName = "router";

        useNetworkd = true;
        useDHCP = false;

        nftables.enable = true;

        firewall = {
            enable = true;
        };

        enableIPv6 = true;
    };
    systemd.services.systemd-networkd.environment.SYSTEMD_LOG_LEVEL = "debug";
    systemd.services.ethtool-wan = {
        description = "Disable checksum offload on WAN";
        after = [ "network-pre.target" ];
        before = [ "systemd-networkd.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig.Type = "oneshot";

        script = ''
            ${pkgs.ethtool}/bin/ethtool -K enp1s0 rx off tx off
        '';
    };
    systemd.network = {
        enable = true;

        config = {
        # DUID-EN → DUID-LL に変更
            dhcpV6Config.DUIDType = "link-layer";
        };
        networks."10-wan" = {
            matchConfig.Name = "enp1s0";

            networkConfig = {
                DHCP = "ipv6";
                IPv6AcceptRA = true;
            };
            ipv6AcceptRAConfig = {
                DHCPv6Client = "always";
            };
            dhcpV6Config = {
                RapidCommit = false;
            };
        };

            # LAN
        networks."20-lan" = {
            matchConfig.Name = "enp2s0";

            address = [
                "192.168.1.1/24"
            ];

            networkConfig = {
                IPv6SendRA = true;
            };
            dhcpPrefixDelegationConfig = {
                UplinkInterface = "enp1s0";
                SubnetId = 1;
            };
        };
    };
    services.dnsmasq = {
        enable = true;
        settings = {
            interface = "enp2s0";

            dhcp-range = [
                "192.168.1.100,192.168.1.200,12h"
            ];

            dhcp-option = [
                "option:router,192.168.1.1"
                "option:dns-server,192.168.1.1"
            ];
        };
    };
    systemd.services.dslite = {
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];

        serviceConfig.Type = "oneshot";

        script = ''
            AFTR="2404:1a8:7f01:b::3"

            ip -6 tunnel add dslite mode ipip6 remote "$AFTR" dev enp1s0 || true
            ip link set dslite up
            ip route add default dev dslite
        '';
    };
    services.openssh = {
        enable = true;

        settings = {
            PermitRootLogin = "yes";
            PasswordAuthentication = false;
        };
    };

    users.users.root.openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC3F4EyORHK0dc+1o/fbY8T3t9XnsFO5DJ0b7T5DWo2p8RpYAEURtzg2N4kcwlD20n68FAmj3YfQXJhSg4dl5SbTB3VgYn8EWawFIp2p5o2o/wI8e8tIYFKzetkjFRb37tvJsHNdhIfrDYcOxUE9j8IcZSBYv8rmdjCKLzXRfLNt7QSz3WbRw5cS1PAN7MfUf/ygUxi/9qEzMW4sRBFcDfr9AelrUpglMnCO7OWk9oLZ0GxkwYcDmm3UX9UfIrlhbks2P7sxjTFE/jvGd6zKpPgcnsZW5EBogXbGlgVViRdB+QgIGm0XJ9zohG/Kz1kkw5jxTu9i4cTs14TMILQ3QL5M9J0jiEhX/etxJCpszyhkk0b7a1+IsCkCmqZtWW+ZmaV9wA8lQXdyJrNwum9vRtkDxUIhP3akV/zgCMzOfW3vaMo00uvivy8IY73sWkAVeaToRd9ao7Y4O0WgRaJPHupFogI45nGT9F/ir6BIjfwBY2tmN1CcAC9EHcKWwuWpeHCazS+MdvLeG2H2+fi0JqthqDHyg1sVALSNYne44yEGpHtCl4J+XLtfqamFM1hGi/GwiPv5K0at1tG3jgFCGVhgoz9CMTATqYeFfPR/gfX2EJ9PsMylxSBNW0Z8/e8Hu67xzyZ29nxNx2caFc20UbJXCwcU8zHn+499igq0YML/w== user@DESKTOP"
    ];
    environment.systemPackages = with pkgs; [
        # editor/tools
        nano
        vim
        git
        curl
        wget
        htop
        btop
        tmux

        # network debug
        tcpdump
        iperf3
        mtr
        traceroute
        dig
        bind
        nmap
        ndisc6

        # routing/network
        iproute2
        nftables
        ethtool
        bridge-utils
        vlan
        conntrack-tools
        frr

        # nic / hw
        pciutils
        usbutils
        lm_sensors
        smartmontools

        # performance/debug
        sysstat
        iotop
        iftop

        # compression/fs
        zstd
        zip
        unzip

        # json/log
        jq
        yq-go

        # containers
        docker
        docker-compose

        # misc
        fastfetch
    ];
    boot.kernelModules = [
        "tcp_bbr"
        "sch_cake"

        # Mellanox
        "mlx4_core"
        "mlx4_en"

        # Intel
        "ixgbe"

        # tunnels
        "ip6_tunnel"
        "ip6tnl"
        "sit"

        # nft nat
        "nf_nat"
        "nft_chain_nat"
    ];

    boot.kernel.sysctl = {
        "net.ipv4.ip_forward" = 1;
        "net.ipv6.conf.all.forwarding" = 1;
        # BBR
        "net.core.default_qdisc" = "cake";
        "net.ipv4.tcp_congestion_control" = "bbr";
    };
    services.frr.bgpd = {
        enable = true;
    };

    virtualisation.docker.enable = true;

    time.timeZone = "Asia/Tokyo";

    system.stateVersion = "26.05";
}