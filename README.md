# NixOS Xpass ルーター

Xpass（IPIP6）で IPv4 over IPv6 接続を行う、実機向け NixOS
ルーター設定です。Nix Flake の `nixosConfigurations.router` を
`nixos-rebuild` で対象マシンへ適用します。

> [!WARNING]
> NIC 名、ディスク UUID、SSH 公開鍵、BGP ピア、ポート転送先などが
> 特定の環境向けに固定されています。そのまま別のマシンへ適用しないでください。

## 構成

| 用途 | インターフェース | 設定 |
| --- | --- | --- |
| WAN | `enp1s0` | DHCPv6、RA、Xpass IPv6 アドレス |
| LAN | `enp2s0` | `172.16.1.1/24`、DHCPv4、IPv6 Prefix Delegation / RA |
| LAN 2 / BGP | `enp3s0` | `192.168.100.1/30` |
| Xpass トンネル | `ip6tnl1` | IPIP6、IPv4 デフォルトルート、masquerade |

主な機能は次のとおりです。

- `systemd-networkd` による WAN / LAN / IPIP6 トンネル設定
- `dnsmasq` による LAN 向け DHCPv4
  （`172.16.1.11`～`172.16.1.99`）
- IPv4 / IPv6 フォワーディング
- `nftables` による NAT、フィルタリング、ポート転送
- FRR (`bgpd`) による `192.168.100.2`（AS 65100）との BGP
- Xpass DDNS の4分間隔更新
- Prometheus Node Exporter（TCP 9100）
- OpenSSH（root の公開鍵認証のみ）
- Docker、ネットワーク診断・運用ツール
- BBR と CAKE

## ファイル

- `flake.nix`: Nixpkgs `nixos-26.05` と `router` 構成のエントリーポイント
- `router.nix`: ルーター本体の設定
- `snat-config.nix`: Xpassトンネル向けSNATとポート転送設定
- `ssh-config.nix`: OpenSSHとroot公開鍵の設定
- `hardware-configuration.nix`: 現在の実機固有ハードウェア設定
- `build.sh`: `nixos-rebuild switch --flake .#router --impure` の実行スクリプト
- `configuration.nix`: `nixos-generate-config` が生成した標準設定
  （flake からは読み込まれません）
- `xpass-env.nix`: Xpass の契約・接続情報（Git 管理対象外）
- `webui/`: ルーター状態を表示する Web UI と NixOS サービス

## Web UI

Web UI は `http://172.16.1.1:8080` で起動し、ホストの稼働時間、
ロードアベレージ、ネットワークインターフェースと IP アドレスを表示します。

NixOS サービスの実装は `webui/module.nix`、このルーター固有の有効化設定は
`webui/configuration.nix` に分離しています。バックエンドは FastAPI、
開発環境と依存関係の管理には uv を使用します。

```bash
cd webui
uv sync
uv run uvicorn backend:app --reload
```

詳しくは `webui/README.md` を参照してください。現在は状態確認専用で、
ルーター設定を書き換える API や認証機能はありません。

## 事前準備

Nix Flakes を利用できる x86_64 NixOS 環境が必要です。
適用前に、少なくとも以下を自分の環境に合わせて変更してください。

- `router.nix` の NIC 名、LAN アドレス、BGP、ポート転送、SSH 公開鍵
- `hardware-configuration.nix` のファイルシステム UUID とハードウェア設定
- 必要に応じて `flake.nix` の Nixpkgs ブランチ

リポジトリ直下に `xpass-env.nix` を作成します。

```nix
{
  xpassIPv6Prefix = "2001:db8::1/64";
  xpassTunnelRemote = "2001:db8::2";
  xpassIPv4Fixed = "192.0.2.1/32";

  xpassDDNSUser = "ddns-user";
  xpassDDNSPassword = "ddns-password";
  xpassDdnsDomain = "ddns.example.net";
  xpassFQDN = "router.example.net";
  xpassDDNSId = "ddns-id";
}
```

値は契約先から提供された情報に置き換えてください。このファイルには認証情報が
含まれるため、`.gitignore` で除外されています。

> [!NOTE]
> Git 管理下の flake を `.#router` として評価すると、未追跡かつ除外された
> `xpass-env.nix` が flake のソースに含まれない場合があります。その場合は
> ローカルディレクトリを明示する
> `--flake path:.#router` を使用してください。秘密情報をリポジトリへ
> コミットしないでください。

## 適用

設定を確認してから、対象の NixOS マシン上で実行します。

```bash
sudo NIXPKGS_ALLOW_UNFREE=1 \
  nixos-rebuild switch --flake path:.#router --impure
```

`build.sh` を使う場合は次のとおりです。

```bash
./build.sh
```

`build.sh` は現在のブランチを
`https://github.com/nekorobi-0/nix-router.git` からfast-forwardで更新してから、
`router` 構成をビルドし、そのまま切り替えます。更新できない場合は設定を
適用せず停止します。ISOは生成しません。

切り替えずに評価・ビルドだけ行う場合:

```bash
sudo NIXPKGS_ALLOW_UNFREE=1 \
  nixos-rebuild build --flake path:.#router --impure
```

## 運用上の注意

- root のパスワードログインは無効ですが、root SSH ログイン自体は許可されています。
- Node Exporter の TCP 9100 はファイアウォールで開放されます。
- DDNS 更新 URL に認証情報が含まれ、サービス定義やログから参照される可能性があります。
- `curl -k` により DDNS サーバーの TLS 証明書検証を無効化しています。
- nftables の転送先には `192.168.0.x` が固定指定されています。現在の
  `172.16.1.0/24` LAN とは異なるため、実際の配下ネットワークを確認してください。
- `system.stateVersion` は `26.05` です。既存システムでは理由なく変更しないでください。
