{ config, pkgs, ... }:

{
  boot.loader.systemd-boot.enable = true;

  networking.hostName = "router";

  services.openssh.enable = true;

  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC3F4EyORHK0dc+1o/fbY8T3t9XnsFO5DJ0b7T5DWo2p8RpYAEURtzg2N4kcwlD20n68FAmj3YfQXJhSg4dl5SbTB3VgYn8EWawFIp2p5o2o/wI8e8tIYFKzetkjFRb37tvJsHNdhIfrDYcOxUE9j8IcZSBYv8rmdjCKLzXRfLNt7QSz3WbRw5cS1PAN7MfUf/ygUxi/9qEzMW4sRBFcDfr9AelrUpglMnCO7OWk9oLZ0GxkwYcDmm3UX9UfIrlhbks2P7sxjTFE/jvGd6zKpPgcnsZW5EBogXbGlgVViRdB+QgIGm0XJ9zohG/Kz1kkw5jxTu9i4cTs14TMILQ3QL5M9J0jiEhX/etxJCpszyhkk0b7a1+IsCkCmqZtWW+ZmaV9wA8lQXdyJrNwum9vRtkDxUIhP3akV/zgCMzOfW3vaMo00uvivy8IY73sWkAVeaToRd9ao7Y4O0WgRaJPHupFogI45nGT9F/ir6BIjfwBY2tmN1CcAC9EHcKWwuWpeHCazS+MdvLeG2H2+fi0JqthqDHyg1sVALSNYne44yEGpHtCl4J+XLtfqamFM1hGi/GwiPv5K0at1tG3jgFCGVhgoz9CMTATqYeFfPR/gfX2EJ9PsMylxSBNW0Z8/e8Hu67xzyZ29nxNx2caFc20UbJXCwcU8zHn+499igq0YML/w== kamiy@DESKTOP-6S46DFA"
  ];

  system.stateVersion = "25.11";
}