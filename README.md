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
- FRR Exporter（管理LANの `172.16.0.1:9342`、BGP・経路情報）
- OpenSSH（root の公開鍵認証のみ）
- Docker、ネットワーク診断・運用ツール
- BBR と CAKE

## ファイル

- `flake.nix`: Nixpkgs `nixos-26.05` と `router` 構成のエントリーポイント
- `router.nix`: ルーター本体の設定
- `snat-config.nix`: Xpassトンネル向けSNATとポート転送設定
- `wan-security.nix` / `wan-firewall.nft`: IPv4/IPv6の転送制限
- `scripts/prepare_xpass_credentials.py`: DDNS秘密情報の移行
- `scripts/xpass_ddns.py`: TLS検証を設定できるDDNS更新
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
  xpassBasicPassword = "basic-password"; # DDNSパスワードと異なる場合に指定
  xpassDdnsDomain = "ddns.example.net";
  xpassFQDN = "router.example.net";
  xpassDDNSId = "ddns-id";
}
```

値は契約先から提供された情報に置き換えてください。既存の設定も上記のような
平坦な文字列の属性セットとして移行できます。Nix式や文字列補間は移行スクリプトが拒否します。
旧名の `xpassDDNSPass` はBasic認証用の `xpassBasicPassword` に移行します。
DDNS更新用には `xpassDDNSPassword` を使用します。Basic用を省略した場合はDDNS用と同じ値を使用します。

**最初のNix評価・ビルド前に**、ルーター上で次の移行を実行してください。

```bash
sudo python3 scripts/prepare_xpass_credentials.py
# python3がない場合:
# sudo nix --extra-experimental-features 'nix-command flakes' shell github:NixOS/nixpkgs/nixos-26.05#python3 --command python3 scripts/prepare_xpass_credentials.py
```

DDNS情報を `/etc/nix-router/xpass-ddns.json`（root専用、0600）に保存し、
`xpass-env.nix` にはネットワーク用の3項目だけ残します。元のファイルは
`/etc/nix-router/xpass-env.original.nix` に0600でバックアップします。
繰り返し実行できます。移行済みならDDNS情報はJSON側で更新し、IPv6アドレスは
`xpass-env.nix` で変更してから移行スクリプトを再実行してください。
DDNSサービスはsystemdの `LoadCredential` を使って実行時にJSONを読みます。
JSONとバックアップはリポジトリ内へコピーしないでください。

TLS証明書は既定で検証します。今回の実機の接続先は自己署名・期限切れ証明書を
使用するため、ユーザー指定によりJSONに `"xpassDDNSVerifyTLS": false` を設定します。
この設定では証明書・ホスト名の検証を省略します。移行スクリプトの再実行でも設定を維持します。

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

## FRR Exporter

Nixpkgs標準の `services.prometheus.exporters.frr` を使用します。
現在の `flake.lock` では `tynany/frr_exporter` v1.10.0です。
FRRの `/run/frr` にあるUnixソケットへ、標準モジュールのユーザー `frr`・
グループ `frrvty` で接続します。`frr.service` の起動後にExporterを起動します。

IPv4 BGPと経路のcollectorを使用し、未使用のBFD・OSPFは無効にします。
待受は管理LANの `172.16.0.1:9342` のみです。LANは既存の
`trustedInterfaces` で許可されているため、`openFirewall = false` でも
LANから収集できます。WAN側へのポート開放は追加しません。

外部Prometheusの設定に次を追加し、設定検証後に再読み込みしてください。
このリポジトリではPrometheusサーバー自体は有効化しません。

```yaml
scrape_configs:
  - job_name: frr
    scrape_interval: 30s
    scrape_timeout: 25s
    static_configs:
      - targets: ["172.16.0.1:9342"]
```

設定をビルドして適用した後、ルーター上で確認します。

```bash
systemctl status prometheus-frr-exporter.service
sudo journalctl -u prometheus-frr-exporter.service -b --no-pager
curl --fail --max-time 25 http://172.16.0.1:9342/metrics
sudo vtysh -c 'show bgp summary json'
```

管理LANのPrometheusホストからも `/metrics` の到達性を確認してください。
Prometheusで `up{job="frr"} == 1` を確認し、
`frr_bgp_peer_state{job="frr"}` の6ピアがFRRの表示と一致することを確認します。
状態値は `1` がEstablished、`0` がDown、`2` が管理上の停止です。
プレフィックス数と経路数が収集でき、scrapeの時間が25秒未満であることも確認します。
WAN側の別回線からはTCP 9342に接続できないことを確認してください。

通知はまず `up{job="frr"} == 0` が2分続く場合を対象にします。
BGPの通知対象は、常時接続を期待するピアを選んだうえで
`frr_bgp_peer_state{job="frr", peer="対象のIP"} == 0` が2分続く条件にします。
ピアのメトリクス欠落はこの条件では検知できないため、対象ピアの
`absent(frr_bgp_peer_state{job="frr", peer="対象のIP"})` も別途監視します。

適用後に問題があれば `sudo nixos-rebuild switch --rollback` で直前の
generationへ戻します。これは同時に適用した他の変更も戻すため、
Exporterだけを外す場合は追加したExporterとsystemdの設定を削除して再適用してください。

## 運用上の注意

- WAN側の `enp1s0` と `ip6tnl1` からの転送は、戻り通信・必要なIPv6エラー・
  明示したIPv4ポート転送を許可し、その他の新規接続を拒否します。
  標準firewallはINPUTを担当し、FORWARDは独立した `inet wan-guard` テーブルが担当します。
- LAN間とLANから外への通信は維持します。LAN全体の信頼と、管理UIの認証は今後の分離対策の対象です。
- rootの鍵認証SSHはLAN側から利用可能です。WAN側のTCP 22は開放しません。
- Node ExporterのTCP 9100、FRR Exporterの9342とWeb UIの8080はWAN側へ開放しません。
- Dockerが独自に公開したポートもWAN側の転送制限を受けます。必要な公開は
  `general_config.toml` に指定して `python3 generate_snat_config.py` で生成してください。
  カスタム名のDockerブリッジからの新規転送は、必要に応じて `wan-firewall.nft` で明示許可してください。
- DDNSはJSONの `xpassDDNSVerifyTLS` で証明書検証を選択します。
  認証情報をコマンド引数・サービス定義・更新ログへ出力しません。
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
