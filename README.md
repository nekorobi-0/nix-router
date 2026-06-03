# NixOSによるXpass対応ルーターを作るだけ。
**Warning:まだIPv6しか繋がりません。WIPです**
## 概要

このリポジトリは、Nix Flake でルーター用の NixOS ISO をビルドするための最小構成です。
`flake.nix` で `router.nix` を読み込み、`nixosConfigurations.router` として定義しています。

`router.nix` では主に以下を設定しています。

- WAN (`enp1s0`): DHCPv6 / RA 受信
- LAN (`enp2s0`): `192.168.1.1/24` を付与し IPv6 RA 送信
- IPv4/IPv6 フォワーディング有効化
- `nftables` + firewall 有効化
- `tcp_bbr` / `sch_cake` などのカーネルモジュールと sysctl
- OpenSSH 有効化（root 公開鍵ログイン）
- FRR (bgpd) / Docker / 各種ネットワーク運用ツール同梱

## ビルド

`build.sh` で ISO をビルドし、`artifacts/router.iso` にコピーします。

```bash
./build.sh
```
