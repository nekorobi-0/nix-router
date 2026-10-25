# NixOS Xpass ルーター

Xpass（IPIP6）で IPv4 over IPv6 接続を行う、実機向け NixOS ルーター設定リポジトリです。
Nix Flake の `nixosConfigurations.router` を `nixos-rebuild` で対象マシンへ適用します。
Nixpkgs は `nixos-26.05`、システムは `x86_64-linux` です。

> [!WARNING]
> NIC 名、ディスク UUID、SSH 公開鍵、BGP ピア、ポート転送先などが特定の環境向けに固定されています。
> そのまま別のマシンへ適用しないでください。

## 概要

本リポジトリは単一の NixOS ルーターマシン（ホスト名 `router`）の構成を宣言的に定義します。
WAN 側に Xpass 契約の IPv6 / IPIP6 トンネル（`ip6tnl1`）を立てて IPv4 通信を搬送し、
LAN 側は 3 つのインターフェースに分けて DHCP / Prefix Delegation / BGP 配信を行います。

主な機能:

- `systemd-networkd` による WAN / LAN / IPIP6 トンネル設定
- `dnsmasq` による LAN3 向け DHCPv4（`172.16.0.11`〜`172.16.0.99`、DNS 待ち受け無効）
- IPv4 / IPv6 フォワーディング
- `nftables` による NAT、フィルタリング、ポート転送
- FRR (`bgpd`) による複数ピアとの BGP（ローカル AS 65000 / 65001）
- Xpass DDNS の定期更新（4 分間隔、systemd credentials で秘密情報を読込）
- Prometheus Node Exporter（TCP 9100）/ FRR Exporter（`172.16.0.1:9342`）
- OpenSSH（root 公開鍵認証のみ、LAN 側限定）
- Docker、ネットワーク診断・運用ツール
- BBR（輻輳制御）と CAKE（キュー制御）

## ネットワーク構成

| 用途 | インターフェース | 設定 |
| --- | --- | --- |
| WAN | `enp1s0` | DHCPv6、RA、Xpass IPv6 アドレス |
| LAN | `enp2s0` | `10.0.1.1/24`、IPv6 Prefix Delegation（SubnetId 1）/ RA |
| LAN2 / BGP | `enp3s0` | `192.168.100.1/30` |
| LAN3（管理） | `enp1s0d1` | `172.16.0.1/24`、DHCPv4、IPv6 Prefix Delegation（SubnetId 2）/ RA |
| Xpass トンネル | `ip6tnl1` | IPIP6、IPv4 デフォルトルート、masquerade |

BGP は `router.nix` の FRR 設定で定義します（ローカル AS 65000、
`192.168.100.2`（AS 65100）、`172.16.0.2`（AS 65110）、`10.0.1.100`〜`.104`
（AS 65200〜65204、local-as 65001 で replace-as））。

## ファイル構成

| ファイル | 説明 |
| --- | --- |
| `flake.nix` | Nixpkgs `nixos-26.05` と `router` 構成のエントリーポイント |
| `router.nix` | ルーター本体の設定（networkd、dnsmasq、FRR、DDNS、exporter 等） |
| `snat-config.nix` | Xpass トンネル向け SNAT / DNAT と `wan-guard` のポート転送許可（生成物） |
| `general_config.toml` | ポート転送定義（`snat-config.nix` のソース、Git 管理外） |
| `generate_snat_config.py` | `general_config.toml` から `snat-config.nix` を生成するスクリプト |
| `wan-security.nix` / `wan-firewall.nft` | IPv4/IPv6 の転送制限（独立した FORWARD チェーン） |
| `scripts/prepare_xpass_credentials.py` | DDNS 秘密情報の移行（JSON へ移動、`xpass-env.nix` は 3 項目に削減） |
| `scripts/xpass_ddns.py` | TLS 検証を設定できる DDNS 更新スクリプト |
| `ssh-config.nix` | OpenSSH と root 公開鍵の設定 |
| `hardware-configuration.nix` | 現実機固有のハードウェア設定（ファイルシステム UUID 等） |
| `configuration.nix` | `nixos-generate-config` が生成した標準設定（flake からは読み込まれない） |
| `xpass-env.nix` | Xpass のネットワーク情報（移行後は秘密情報を含まない、Git 管理対象外） |
| `build.sh` | 更新 → 秘密移行 → `nixos-rebuild switch --flake path:.#router --impure` の実行スクリプト |
| `webui/` | ルーター状態表示・ポート転送編集の Web UI（FastAPI + uv）と NixOS サービス |
| `tests/` | 秘密移行・DDNS・Web UI の pytest と、ファイアウォールの統合テスト |
| `WAN_SECURITY_REVIEW.md` | 外部 WAN からの攻撃防御に関する調査・設計記録 |

## Web UI

Web UI は `http://172.16.0.1:8080` で起動し、稼働時間、ロードアベレージ、
ネットワークインターフェースと IP アドレスを表示します。
`PUT /api/ports` でポート転送設定を保存できますが、適用には再構築が必要です。

NixOS サービスの実装は `webui/module.nix`、ルーター固有の有効化設定は
`webui/configuration.nix` に分離されています。バックエンドは FastAPI、
依存関係の管理は uv を使用します。

```bash
cd webui
uv sync
uv run uvicorn backend:app --reload
```

API エンドポイント: `GET /api/health` / `GET /api/status` / `GET /api/ports` /
`PUT /api/ports` / `GET /api/docs`。詳しくは `webui/README.md` を参照してください。
**認証機能はないため、管理できる LAN 内で利用してください。**

## 事前準備

Nix Flakes を利用できる x86_64 NixOS 環境が必要です。適用前に、少なくとも以下を
自分の環境に合わせて変更してください。

- `router.nix` の NIC 名、LAN アドレス、BGP
- `general_config.toml` のポート転送、`ssh-config.nix` の SSH 公開鍵
- `hardware-configuration.nix` のファイルシステム UUID とハードウェア設定
- 必要に応じて `flake.nix` の Nixpkgs ブランチ

リポジトリ直下に `xpass-env.nix` を作成します（Git 管理対象外）。

```nix
{
  xpassIPv6Prefix = "2001:db8::1/64";
  xpassTunnelRemote = "2001:db8::2";
  xpassIPv4Fixed = "192.0.2.1/32";

  xpassDDNSUser = "ddns-user";
  xpassDDNSPassword = "ddns-password";
  xpassBasicPassword = "basic-password"; # DDNSパスワードと異なる場合に指定
  xpassDdnsDomain = "ddns.example.net";
  xpassFQDN = "router.example.net";
  xpassDDNSId = "ddns-id";
}
```

値は契約先から提供された情報に置き換えてください。Nix 式や文字列補間は
移行スクリプトが拒否します。旧名の `xpassDDNSPass` は Basic 認証用の
`xpassBasicPassword` に移行し、DDNS 更新には `xpassDDNSPassword` を使用します
（Basic 用を省略すると DDNS 用と同じ値を使用します）。

### DDNS 秘密情報の移行

**最初の Nix 評価・ビルド前に**、ルーター上で次の移行を実行してください。

```bash
sudo python3 scripts/prepare_xpass_credentials.py
# python3 がない場合:
# sudo nix --extra-experimental-features 'nix-command flakes' shell github:NixOS/nixpkgs/nixos-26.05#python3 --command python3 scripts/prepare_xpass_credentials.py
```

DDNS 情報を `/etc/nix-router/xpass-ddns.json`（root 専用、0600）に保存し、
`xpass-env.nix` にはネットワーク用の 3 項目だけ残します。元のファイルは
`/etc/nix-router/xpass-env.original.nix` に 0600 でバックアップします。
繰り返し実行でき、移行済みなら JSON 側で DDNS 情報を更新します。
IPv6 アドレスを変更した場合は `xpass-env.nix` で編集してから再実行してください。
DDNS サービスは systemd の `LoadCredential` を使って実行時に JSON を読みます。
JSON とバックアップをリポジトリ内へコピーしないでください。

TLS 証明書は既定で検証します。接続先が自己署名・期限切れ証明書を使用する場合、
JSON に `"xpassDDNSVerifyTLS": false` を設定できます（証明書・ホスト名の検証を省略。
移行スクリプトの再実行でも設定は維持されます）。

以前の構成で秘密情報が Nix store に保存された場合、この移行では過去の生成物は
消えません。認証情報の変更と、不要な旧世代・store の整理を検討してください。

> [!NOTE]
> Git 管理下の flake を `.#router` として評価すると、未追跡かつ除外された
> `xpass-env.nix` が flake のソースに含まれない場合があります。その場合は
> ローカルディレクトリを明示する `--flake path:.#router` を使用してください。
> 秘密情報をリポジトリへコミットしないでください。

## 適用

移行と設定確認の後、対象の NixOS マシン上で実行します。
SSH は LAN 側に限定されるため、LAN からの管理接続またはローカルコンソールを確保してください。

```bash
sudo NIXPKGS_ALLOW_UNFREE=1 \
  nixos-rebuild switch --flake path:.#router --impure
```

`build.sh` を使う場合は `./build.sh` とします。現在のブランチを
`https://github.com/nekorobi-0/nix-router.git` から fast-forward で更新してから、
DDNS 秘密情報を移行し、`router` 構成をビルドしてそのまま切り替えます。
更新・移行できない場合は設定を適用せず停止します。

切り替えずに評価・ビルドだけ行う場合:

```bash
sudo NIXPKGS_ALLOW_UNFREE=1 \
  nixos-rebuild build --flake path:.#router --impure
```

## ポート転送

公開ポート転送は `general_config.toml` で定義し、`generate_snat_config.py` で
`snat-config.nix` を生成します。トンネル経由（`iifname "ip6tnl1"`）の DNAT と、
`wan-guard` テーブルの `wan_port_forwards` チェーンによる許可ルールの対を生成します。
変更時は `./generate_snat_config.py` を実行して `snat-config.nix` を再生成してください。

## WAN セキュリティ

標準 `filterForward` の代わりに独立した FORWARD チェーン（`wan-firewall.nft`、
`wan-security.nix` が `wan-guard` テーブルとして組み込み）で転送を制御します。
既定は drop、LAN 間 / 確立済み / コンテナ発の通信を許可し、WAN・トンネル入口からの
新規接続は ICMPv6 の制御通信と `wan_port_forwards` の許可ポートのみ通します。
Docker の独自ルールと干渉しないよう `ip-forward-no-drop = true` を設定しています。
設計の経緯と確認手順は `WAN_SECURITY_REVIEW.md` を参照してください。

## FRR Exporter

Nixpkgs 標準の `services.prometheus.exporters.frr` を使用します
（`flake.lock` では `tynany/frr_exporter` v1.10.0）。FRR の `/run/frr` にある
Unix ソケットへ、標準モジュールの `frr` ユーザー・`frrvty` グループで接続し、
`frr.service` の起動後に Exporter を起動します。

IPv4 BGP と経路の collector を使用し、未使用の BFD・OSPF は無効にします。
待受は管理 LAN の `172.16.0.1:9342` のみで、WAN 側へのポート開放はしません。

外部 Prometheus の設定に次を追加し、設定検証後に再読み込みしてください
（このリポジトリでは Prometheus サーバー自体は有効化しません）。

```yaml
scrape_configs:
  - job_name: frr
    scrape_interval: 30s
    scrape_timeout: 25s
    static_configs:
      - targets: ["172.16.0.1:9342"]
```

設定を適用後の確認手順:

```bash
systemctl status prometheus-frr-exporter.service
sudo journalctl -u prometheus-frr-exporter.service -b --no-pager
curl --fail --max-time 25 http://172.16.0.1:9342/metrics
sudo vtysh -c 'show bgp summary json'
```

管理 LAN の Prometheus ホストからも `/metrics` の到達性を確認し、
`up{job="frr"} == 1` と `frr_bgp_peer_state{job="frr"}` の 6 ピアが FRR の
表示と一致すること（`1` = Established、`0` = Down、`2` = 管理上の停止）、
プレフィックス数・経路数の収集、scrape 25 秒未満、WAN 側の別回線から
TCP 9342 に接続できないこと、を確認してください。

## テスト

```bash
# 秘密移行・DDNS・Web UI のテスト
uv run --project webui pytest tests/test_xpass_credentials.py webui/tests

# ユーザー/ネットワーク名前空間で転送制限を検証（ホストネットワークは変更しない）
unshare -Urn python3 tests/firewall_integration.py
```

`nixos_firewall_integration.py` は評価済み NixOS の INPUT / FORWARD テーブルを
実 kernel の IPIP6 と一緒に検証します。実行時は `xpass-env.nix`（実値）、
認証情報、`.git`、仮想環境を除いた一時コピーを用意してください。
詳細は `tests/README.md` を参照してください。
