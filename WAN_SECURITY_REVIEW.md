# 外部WANからの攻撃防御に関する調査

調査日: 2026-10-07

この文書は実装前の調査記録。後続の実装で転送制限、WAN側SSH閉鎖、
Xpass受信許可、DDNS秘密情報の移行とTLS検証を追加した。
現在の設定・適用手順は `README.md`、転送ルールは `wan-security.nix` と
`wan-firewall.nft` を参照。標準の `filterForward` の代わりに独立したFORWARDチェーンを使用する。
実装後は例示アドレスだけを使った一時コピーでNixOS構成を評価し、モジュールの
assertionと全nftablesテーブルの構文を検証した。隔離ネットワークで転送制限を18件、
評価済みルールと実際のIPIP6トンネルで管理ポート制限等を18件確認した。
秘密移行・DDNS・既存UIのテスト16件も成功。実機への適用とシステム全体のビルドは未実施。

リポジトリの設定と、指定されている Nixpkgs `nixos-26.05` ブランチの公式モジュールを照合した静的レビュー。実機の稼働設定、外部からの到達性、ISP側の制限は未確認。作業環境には `nix` がなく、NixOS構成の評価・ビルドは実施していない。`flake.lock` もないため、実機が使用したモジュールの版との一致は保証できない。

現状はルーター自身への基本的なフィルタリングがある一方、WAN→LANの新規接続を拒否する転送フィルタの設定がない。特にLANへ配布するグローバルIPv6アドレスへの防御が最優先。

## 現状と優先順位

| 優先度 | 対象 | 確認結果と影響 |
| --- | --- | --- |
| 最優先 | WAN→LANの転送 | `router.nix:28` でIPv4/IPv6転送を有効化、`:50` のfirewallに `filterForward` 指定なし。NixOSの既定値はfalseで、標準firewallによるFORWARDフィルタは生成されない。IPv6 PD/RAも有効なため、ISPが到達を許し、端末側で拒否しなければLAN端末の待受サービスが外部から到達可能になる。 |
| 高 | WAN側SSH | `ssh-config.nix:4` で有効化。NixOSの `services.openssh.openFirewall` は既定trueで、待受アドレスの限定もないためTCP 22はIPv4/IPv6でWAN側にも許可される。パスワード認証無効は有効な防御だが、root公開鍵ログインとSSH実装への攻撃面は残る。 |
| 高 | 公開サービス | `snat-config.nix:21` にTCP 80、25566、25567、25568のDNATあり。到達する公開サービスの脆弱性や認証攻撃は、ポート許可だけでは防げない。転送先 `192.168.0.x` への実際のBGP経路は未確認。 |
| 高・要確認 | Docker | `router.nix:244` で有効。Dockerは独自に転送/NATルールを作成し、ポート公開も行う。コンテナと公開ポートの現状は不明で、ホストのINPUT設定だけから公開範囲を判断できない。 |
| 中 | 不要なホスト側ポート許可 | `snat-config.nix:6` は公開転送用の4ポートを全インターフェースのINPUTにも許可する。IPv6にはDNATがないが、この許可は適用される。同じ番号でルーター自身のサービスが待受すると公開される。 |
| 中 | DDNS | `router.nix:210` の `curl -k` はTLS証明書検証を無効化。通信を介入できる攻撃者に認証情報を渡す危険がある。秘密を生成スクリプトへ埋め込むためNix storeにも残り得る。 |
| 中・侵入後の影響 | 管理UIとLANの信頼 | LAN側3 NICはtrustedInterfacesで、ルーターへの通信を無条件許可。UIは `172.16.0.1:8080` のみでWANへ明示公開されていないが、認証なしの `PUT /api/ports` で設定ファイルを書き換えられる。公開サーバー侵害後の横展開対策として管理用ネットワークの分離が必要。 |

転送フィルタの既定値と生成ルールは[NixOS firewallモジュール](https://github.com/NixOS/nixpkgs/blob/nixos-26.05/nixos/modules/services/networking/firewall.nix)、[nftables実装](https://github.com/NixOS/nixpkgs/blob/nixos-26.05/nixos/modules/services/networking/firewall-nftables.nix)を確認した。SSHの自動開放は[sshdモジュール](https://github.com/NixOS/nixpkgs/blob/nixos-26.05/nixos/modules/services/networking/ssh/sshd.nix)による。

Dockerとホストfirewallの関係は[Docker公式資料](https://docs.docker.com/engine/network/packet-filtering-firewalls/)参照。TLS検証を省略する挙動は[curl公式マニュアル](https://curl.se/docs/manpage.html#-k)参照。

## 既にある防御とREADMEとの差

- 標準nftables firewallはルーター自身への未許可通信をdropし、接続済み・関連通信を許可する。既定の逆引き経路フィルタもある。ただし、これは転送方向の新規接続を拒否する仕組みの代替にはならない。
- SSHのパスワード認証は無効。公開鍵の掲載だけから秘密鍵漏洩とは判断しない。
- dnsmasqはLAN側インターフェース限定で、`port = 0` によりDNSサービス自体が無効。設定上、外部へ開いたdnsmasq DNSの反射攻撃源ではない。
- Web UIはLAN IPv4アドレスのみで待受し、`openFirewall` は既定false。root実行だがsystemdの保護設定もある。ただし書込可能範囲は設定ディレクトリ全体。
- READMEの「Node Exporterの9100を開放」はコードと異なる。`router.nix:226` に `openFirewall = true` はなく、[exportersモジュール](https://github.com/NixOS/nixpkgs/blob/nixos-26.05/nixos/modules/services/monitoring/prometheus/exporters.nix)の既定値はfalse。設定上WAN側INPUTで9100は許可されない。LANからはtrustedInterfacesによってアクセス可能。
- READMEの「状態確認専用・設定変更APIなし」も現在の `webui/backend.py:232` と異なる。保存した変更の適用にはNixOSの再構築が必要で、API単体では即時適用しない。

## 推奨する防御設計

1. **IPv4/IPv6の転送を既定拒否にする。** NixOS標準実装を使うなら `networking.firewall.filterForward = true` と、LAN→WANおよび必要なLAN間転送の `extraForwardRules` をセットで設計する。trueだけでは通常のLAN通信も止まり得る。戻り通信は標準ルールが許可する。標準実装はDNAT通信を包括許可するため、Dockerも含めてDNAT設定を監査する。宛先・入口ごとの厳密な制限が必要なら別途転送ルールを設計する。
2. **管理用SSHはLANまたはVPNへ限定する。** `services.openssh.openFirewall = false` として、必要な管理インターフェース・送信元だけ許可する。root直接ログインの廃止は管理ユーザーとsudo、復旧手段を準備してから行う。現在の遠隔管理経路を確認せず適用しない。
3. **転送用ポートとホスト用ポートを分ける。** DNAT用4ポートのグローバルINPUT許可を除去する。修正対象は生成物だけでなく `generate_snat_config.py:133`。公開サービスは更新・認証を整え、公開サーバーから管理LANへの通信を制限する。
4. **Xpass受信を接続先限定で明示する。** 設定にはトンネル外側のIPv6内IPv4（Next Header 4）を新規受信として許可するルールが見当たらない。トンネル定義だけではfirewall許可にならず、標準INPUT既定拒否と衝突する可能性がある。動作中なら追加ルールやconntrack状態等を実機で確認し、WAN入口・指定のトンネル接続先IPv6・ローカル宛先に限定して許可する。物理WAN全体をtrustedにしない。
5. **IPv6の制御通信を維持する。** DHCPv6、近隣探索、必要なRA、Packet Too Big等を壊さない。ICMPv6の一括拒否は接続不良の原因になる。[RFC 4890](https://www.rfc-editor.org/rfc/rfc4890)を基準に、INPUTとFORWARDそれぞれで必要な種類・スコープを整理する。
6. **DDNSのTLS検証と秘密管理を修正する。** 正しいCAで検証し、秘密はNix storeへ文字列展開せず、root限定ファイルやsystemd credentialsから実行時に読む。API仕様上必要な認証情報がプロセス引数やログに露出しない形にする。
7. **監視と更新を運用に組み込む。** WAN受信量、dropカウンタ、conntrack使用量、SSH失敗、CPU/メモリ、公開サービスの異常を監視する。拒否ログにはレート制限を設ける。依存版をlockで追跡し、計画的にセキュリティ更新する。IDS/IPSの追加はこの基本設定と更新を整えた後に評価する。

BBRは輻輳制御、CAKEはキュー制御であり、この設定だけで侵入防止やDDoS対策になるとは評価できない。回線を埋める攻撃はルーターでdropしても到着時点で帯域を消費するため、ISPや公開サービスの上流での対策が必要。CISAも上流を含むDDoS対応を案内している（[CISAの対応案内](https://content.govdelivery.com/accounts/USDHSCISA/bulletins/362e57b)）。

## 実機で確認する項目

以下は確認手順で、今回実行していない。外部からの試験は自身が管理するアドレスに限定する。

```bash
# ルーター上: 動的に追加されたDockerルールも含める
sudo nft list ruleset
sudo iptables-save
sudo ip6tables-save
sudo ss -lntup
ip -4 route show
ip -6 route show
sudo docker ps --format '{{.Names}}\t{{.Ports}}'
sudo conntrack -S
```

別回線からWAN IPv4、ルーターのグローバルIPv6、代表的なLAN端末のグローバルIPv6について、22・80・8080・9100・25566〜25568と未公開ポートへの到達性を確認する。LAN端末については既知の待受サービスも確認し、端末側firewallによる拒否とルーターによる拒否を区別する。

修正後はLANからのIPv4/IPv6接続、DNS、DHCP/RA、PMTU、Xpass、BGP、公開サービス、管理SSHを確認する。Docker起動前後と再起動後にもWAN→LANの新規接続拒否が維持されることを確認する。

本調査では設定変更、NixOSへの適用、外部スキャンは行っていない。
