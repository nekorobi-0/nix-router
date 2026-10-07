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
| LAN | `enp2s0` | `10.0.1.1/24`、IPv6 Prefix Delegation / RA |
| LAN 2 / BGP | `enp3s0` | `192.168.100.1/30` |
| LAN 3 | `enp1s0d1` | `172.16.0.1/24`、DHCPv4、IPv6 Prefix Delegation / RA |
| Xpass トンネル | `ip6tnl1` | IPIP6、IPv4 デフォルトルート、masquerade |

主な機能は次のとおりです。

- `systemd-networkd` による WAN / LAN / IPIP6 トンネル設定
- `dnsmasq` による LAN 向け DHCPv4
  （`172.16.0.11`～`172.16.0.99`）
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
- `wan-security.nix` / `wan-firewall.nft`: IPv4/IPv6の転送制限
- `scripts/prepare_xpass_credentials.py`: DDNS秘密情報の移行
- `scripts/xpass_ddns.py`: TLS検証付きDDNS更新
- `ssh-config.nix`: OpenSSHとroot公開鍵の設定
- `hardware-configuration.nix`: 現在の実機固有ハードウェア設定
- `build.sh`: `nixos-rebuild switch --flake .#router --impure` の実行スクリプト
- `configuration.nix`: `nixos-generate-config` が生成した標準設定
  （flake からは読み込まれません）
- `xpass-env.nix`: Xpass のネットワーク情報（移行後は秘密情報を含まない、Git管理対象外）
- `webui/`: ルーター状態を表示する Web UI と NixOS サービス

## Web UI

Web UI は `http://172.16.0.1:8080` で起動し、ホストの稼働時間、
ロードアベレージ、ネットワークインターフェースと IP アドレスを表示します。

NixOS サービスの実装は `webui/module.nix`、このルーター固有の有効化設定は
`webui/configuration.nix` に分離しています。バックエンドは FastAPI、
開発環境と依存関係の管理には uv を使用します。

```bash
cd webui
uv sync
uv run uvicorn backend:app --reload
```

詳しくは `webui/README.md` を参照してください。状態確認に加え、
`PUT /api/ports` でポート転送設定を保存できます。適用には再構築が必要です。
認証機能はないため、管理できるLAN内で利用してください。

## 事前準備

Nix Flakes を利用できる x86_64 NixOS 環境が必要です。
適用前に、少なくとも以下を自分の環境に合わせて変更してください。

- `router.nix` の NIC 名、LAN アドレス、BGP
- `general_config.toml` のポート転送、`ssh-config.nix` のSSH公開鍵
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

値は契約先から提供された情報に置き換えてください。既存の設定も上記のような
平坦な文字列の属性セットとして移行できます。Nix式や文字列補間は移行スクリプトが拒否します。

**最初のNix評価・ビルド前に**、ルーター上で次の移行を実行してください。

```bash
sudo python3 scripts/prepare_xpass_credentials.py
# python3がない場合:
# sudo nix shell github:NixOS/nixpkgs/nixos-26.05#python3 --command python3 scripts/prepare_xpass_credentials.py
```

DDNS情報を `/etc/nix-router/xpass-ddns.json`（root専用、0600）に保存し、
`xpass-env.nix` にはネットワーク用の3項目だけ残します。元のファイルは
`/etc/nix-router/xpass-env.original.nix` に0600でバックアップします。
繰り返し実行できます。移行済みならDDNS情報はJSON側で更新し、IPv6アドレスは
`xpass-env.nix` で変更してから移行スクリプトを再実行してください。
DDNSサービスはsystemdの `LoadCredential` を使って実行時にJSONを読みます。
JSONとバックアップはリポジトリ内へコピーしないでください。

以前の構成で秘密情報がNix storeに保存された場合、この移行では過去の生成物は
消えません。認証情報の変更と、不要な旧世代・storeの整理を検討してください。

> [!NOTE]
> Git 管理下の flake を `.#router` として評価すると、未追跡かつ除外された
> `xpass-env.nix` が flake のソースに含まれない場合があります。その場合は
> ローカルディレクトリを明示する
> `--flake path:.#router` を使用してください。秘密情報をリポジトリへ
> コミットしないでください。

## 適用

移行と設定確認の後、対象のNixOSマシン上で実行します。
SSHはLAN側に限定されるため、LANからの管理接続またはローカルコンソールを確保してください。

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
DDNS秘密情報を移行し、`router` 構成をビルドしてそのまま切り替えます。更新・移行できない場合は設定を
適用せず停止します。ISOは生成しません。

切り替えずに評価・ビルドだけ行う場合:

```bash
sudo NIXPKGS_ALLOW_UNFREE=1 \
  nixos-rebuild build --flake path:.#router --impure
```

## 運用上の注意

- WAN側の `enp1s0` と `ip6tnl1` からの転送は、戻り通信・必要なIPv6エラー・
  明示したIPv4ポート転送を許可し、その他の新規接続を拒否します。
  標準firewallはINPUTを担当し、FORWARDは独立した `inet wan-guard` テーブルが担当します。
- LAN間とLANから外への通信は維持します。LAN全体の信頼と、管理UIの認証は今後の分離対策の対象です。
- rootの鍵認証SSHはLAN側から利用可能です。WAN側のTCP 22は開放しません。
- Node ExporterのTCP 9100とWeb UIの8080はWAN側へ開放しません。
- Dockerが独自に公開したポートもWAN側の転送制限を受けます。必要な公開は
  `general_config.toml` に指定して `python3 generate_snat_config.py` で生成してください。
  カスタム名のDockerブリッジからの新規転送は、必要に応じて `wan-firewall.nft` で明示許可してください。
- DDNSは証明書を検証し、認証情報をコマンド引数・サービス定義・更新ログへ出力しません。
  リダイレクトは拒否します。失敗時は `journalctl -u xpass-ddns` で確認してください。
- nftables の転送先には `192.168.0.x` が固定指定されています。現在の
  直接接続LANとは異なるため、実際のBGP経路と配下ネットワークを確認してください。
- 既存の確立済み接続は維持されます。WAN帯域を埋めるDDoSにはISP側での対策が必要です。
- `flake.lock` でNixpkgsの版を固定します。セキュリティ更新は `nix flake update` 後に検証・適用してください。
- `system.stateVersion` は `26.05` です。既存システムでは理由なく変更しないでください。

## 検証

```bash
uv run --project webui pytest tests/test_xpass_credentials.py webui/tests
# Linux上でユーザー・ネットワーク名前空間を作成できる環境が必要
unshare -Urn python3 tests/firewall_integration.py
```

ネットワーク試験は隔離した名前空間で行い、ホストのインターフェースやfirewallを変更しません。
適用後は `sudo nft list ruleset` と別回線からのIPv4/IPv6到達性を確認してください。
