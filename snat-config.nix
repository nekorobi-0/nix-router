{ ... }:

{
  networking.firewall.allowedTCPPorts = [
    80
    25566
    25567
    25568
  ];

  networking.nftables.tables.nat = {
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
}
