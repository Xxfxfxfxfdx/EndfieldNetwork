# NetworkHUD · ネットワーク状態モニター「ダイナミックアイランド」

[简体中文](README.md) · [English](README_EN.md) · **日本語**

[QinAnze/zmd-charge](https://github.com/QinAnze/zmd-charge)（ノート PC の電源状態ダイナミックアイランド）
の UI とアニメーションを模し、**Python 3.12 + Win32 レイヤードウィンドウ**で再現した**ネットワーク
アダプター状態**の HUD です。

いずれかのネットワークアダプターが「切断 ↔ 接続」の間で変化すると、画面中央上部からカプセルが
ポップアウトします：まず種類のロゴがポップアウト → カプセルが縦に広がって結果テキスト（**接続成功 /
通信切断 / DHCPエラー**）を表示 → 情報カプセルに縮んで詳細（SSID、ネットワークアダプター名、
周波数、リンク速度、電波強度）を表示 → そのまま停止した後、全体が縮小して引っ込みます。
HUD をクリックするか、トレイメニューからでも途中で引っ込められます。

![実機スクリーンショット](out/live/contact_connected.png)

---

## クイックスタート

**初回のみ**（依存関係のインストール、1 回だけ）：

```bat
install.bat         :: 自动 pip install -r requirements.txt
```

Python 3.9 以上（3.12 推奨）と `pillow`、`numpy`、`pywin32` の 3 つのライブラリが必要です；
手動で `python -m pip install -r requirements.txt` を実行してもかまいません。

**通常の実行**：

```bat
:: 方式一：双击（无控制台窗口，托盘常驻）
start.bat
stop.bat            :: 停止

:: 方式二：命令行
python -m net_hud                 :: 常驻监听
python -m net_hud --preview       :: 启动后立刻按当前网络状态播一次
python -m net_hud --demo          :: 依次播放三种状态（检查 UI 用）
python -m net_hud --state dhcp_failed --kind ethernet   :: 播放指定状态后退出
```

**スタートアップ時の自動起動**：

```bat
install_autostart.bat      :: 添加（在「启动」文件夹建一个快捷方式）
uninstall_autostart.bat    :: 移除
python tools\autostart.py --status      :: 查看当前状态
```

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NetworkHUD.lnk`
にショートカットを 1 つ置くだけです（ターゲット = `pythonw.exe run.pyw`）。そのため
「タスクマネージャー → スタートアップ」で確認・無効化したり、直接削除したりできます；
管理者権限は不要で、レジストリにも書き込みません。

トレイアイコン（通知領域）は、左クリック = 現在の状態をプレビュー、右クリック = メニュー
（3 つの状態をプレビュー / ログフォルダーを開く / プログラムを終了する）。
ログ：`%TEMP%\NetworkHUD\log-YYYYMMDD.txt`。

---

## 設定ファイル

初回実行時にプロジェクトルートへ **`config.json`** が自動生成されます（UTF-8、`//` と `#` の
行頭コメントを使用可）。**保存すれば反映され、再起動は不要** —— プログラムはトリガーのたびに
ファイルが変更されていないか確認し、変更されていれば再読み込みします。このうち拡縮倍率は
即座にウィンドウを調整します（実測では実行中に `scale` を 1 から 1.7 に変更すると、次の
トリガーでウィンドウが 672×108 から 1142×184 になり、依然として上端に張り付いたまま中央
揃えでした）。`grace` / `poll` / `ignore` の 3 項目だけは監視スレッドに影響するため、再起動が
必要です。コマンドライン引数は明示的に指定した項目だけを上書きします；手書きで壊してしまっても
問題ありません。解析に失敗した場合はログに警告を出してデフォルト値に戻ります。

```jsonc
{
  "scale": 1,             // 缩放倍率 1.0 = 默认大小（0.35 ~ 4.0）
  "label_hold": 3,        // SSID / 适配器名称显示几秒，之后该区域换成 IP
  "total": 12,            // 整个窗口的总时长（胶囊出现 → 完全消失）
  "duration": 6,          // 入场动画基线时长（3 ~ 10）
  "grace": 10,            // DHCP 宽限秒数
  "poll": 2,              // 兜底轮询间隔
  "ignore": [],           // 追加忽略的适配器关键字
  "prefer_ipv6": false,   // 同时有 v4/v6 时优先显示哪个
  "swap_to_ip": true,     // 是否启用「名称 → IP」切换
  "lang": "cn"            // 界面语言：cn / en / jp
}
```

* **拡縮倍率**：`scale` は表示サイズだけを変更し、**ウィンドウは常にワークエリアの上端に
  張り付き、水平方向は中央揃え**になります（上端は上から 48 論理ピクセルに固定され、倍率とは
  無関係です；倍率が大きすぎる場合は左右に対称にはみ出しますが、それでも中央揃えです）。
  実測（本機、幅 2560、dpi 144）では `scale` が 0.5/1/2/3 → ウィンドウ 336×54 / 672×108 /
  1344×216 / 2016×324 となり、カプセルの中心は常に `x=1280`、上端は常に `y=72` です。
* **`total` と `label_hold` の関係**：情報ページの停止時間 = `total − 入場アニメーション −
  退場アニメーション` として自動算出されます。デフォルト `total=12` → 入場 5.16s + 停止
  6.66s + 退場 0.18s。`total` が小さすぎる場合や `label_hold` が停止時間を超える場合は、
  起動ログにヒントが出ます（このとき IP が表示に間に合わないことがあります）。
* **IP 切り替えの計測開始点**：**情報ページが出現した**瞬間（cue `0.42`、ベースライン 6s の
  とき約 2.52s）から数え、`label_hold` 秒後に左側 1 行目を SSID / アダプター名からその
  アダプターの IP に置き換え、ウィンドウが閉じるまでそのままにします。
* **IP の表記**：アドレスそのものだけを表示します（`IP` プレフィックスなし）。IPv6 は小文字
  16 進数（例 `2408:8214:5b3a:1f00:...:7a8b`）、IPv4 は 10 進数（例 `192.168.3.51`）。
  長い IPv6 は自動で文字サイズを縮めて収め、それでも収まらない場合のみ省略記号を付けます。
* `python -m net_hud --show-config` で、現在実際に有効な設定と時間配分を表示できます。

---

## 表示言語

`config.json` の **`lang`** が HUD とトレイメニューの文字を決定します。選択肢は `"cn"`
（簡体字中国語、デフォルト）、`"en"`（English）、`"jp"`（日本語）です；`zh-CN`、`ja`、`English`
といった書き方も受け付け、判別できない場合はログに警告を出して `cn` に戻ります。コマンドラインの
`--lang en` で一時的に上書きできます。

| 位置 | cn | en | jp |
| --- | --- | --- | --- |
| 接続成功時 | 连接成功 | Connected | 接続成功 |
| 通信切断時 | 断开连接 | Disconnected | 通信切断 |
| DHCP エラー時 | DHCP异常 | DHCP Failed | DHCPエラー |
| トレイ · 現在の状態をプレビュー | 预览当前网络状态 | Preview: Current Connection Status | 今のネットワーク状態をプレビュー |
| トレイ · ログフォルダーを開く | 打开日志目录 | Open logs dir | ログフォルダーを開く |
| トレイ · プログラムを終了する | 退出 | Exit | プログラムを終了する |

画面の文字にはプロジェクト同梱の HarmonyOS Sans SC（原プロジェクトの第一候補フォント）を
使用しており、簡体字中国語と日本語のかなを同時にカバーしているため、日本語に切り替えても
別途フォントをインストールする必要はありません。1 ページ目の `/// NETWORK ONLINE` などの
tagline は原プロジェクトのデザイン要素であり、3 言語すべてで英語のままです。`config.json` を
変更して保存すれば切り替わります（次のトリガー時に反映され、トレイメニューも同期して更新されます）。

![英語インターフェース](out/lang_en.png)

---

## トリガー規則

| イベント | 条件 | 結果 |
| --- | --- | --- |
| アダプターのオンライン | `oper_status` が切断から Up になり、かつ**169.254 以外の IP が既にある** | 直ちに `connected` を表示 |
| アダプターのオンライン（DHCP 未準備） | オンライン時に IP が空、またはすべて `169.254.*` | **10 秒の猶予期間**に入りポーリング |
| └ 猶予期間内に IP を取得 | `--grace` 秒以内に `169.254.*` 以外のアドレスが出現 | 直ちに `connected` を表示 |
| └ 猶予期間終了後も IP なし | `--grace`（デフォルト 10）秒を超過 | `dhcp_failed` を表示 |
| アダプターのオフライン | `oper_status` が Up から切断に変化 | `disconnected` を表示 |

* 即時性：`NotifyIpInterfaceChange`（IP Helper API）を登録してイベント駆動とし、さらに
  `--poll`（デフォルト 2s）のフォールバックポーリングを併用しています。実測では切断イベント
  から HUD のポップアウトまでの遅延は約 **0.3 s** です。
* **変化**にのみ反応し、プログラム起動時にすでにオンラインだったアダプターはトリガーしません。
* 仮想ネットワークアダプター（名前/説明に `Microsoft Wi-Fi Direct Virtual Adapter`、
  `Wi-Fi Direct` を含むもの）は無視します。`--ignore 关键字1,关键字2` で追加できます。

## 3 つの状態

| state | 1 ページ目のテキスト | tagline | logo |
| --- | --- | --- | --- |
| `connected` | 接続成功 | `/// NETWORK ONLINE` | アダプターの種類による（下記参照） |
| `disconnected` | 通信切断 | `/// LINK DOWN` | `nointernet` |
| `dhcp_failed` | DHCPエラー | `/// DHCP FAILED` | `nointernet`（副行に現在の IP を表示） |

logo は原プロジェクトの「電源マーク」の動きを踏襲しています：まずカプセル中央にポップアウトし、
次に左へスライドし、最終的に情報ページの最左端で停止します。

## アダプターの分類

| kind | 判定 | logo |
| --- | --- | --- |
| `wifi` | `if_type == IEEE80211`、または名前/説明に `WLAN`/`Wi-Fi`/`wireless`/`无线` を含む | `wifi.png` |
| `btpan` | 名前/説明に `Bluetooth`/`蓝牙` を含む | `btpan.png` |
| `usb_rndis` | 名前/説明に `NDIS` を含む（「以太网」を含む NDIS アダプターはこの分類に入り、スマートフォンの USB テザリングに対応） | `usb_rndis.png` |
| `ethernet` | その他の有線アダプター | `ethernet.png` |

`assets/` 内の二値画像は自動処理されます：白背景の素材は**反転**して黒背景に白い図形とし、
さらに字形の bbox で余白を切り落とし、暗い角丸のベースプレート（`#141313`）の中に描画します；
角丸の状態では塗りつぶしの円形ベース、情報ページでは方形のベースプレートを使います。

## 情報ページのレイアウト

| アダプター | 左列 | 右列 |
| --- | --- | --- |
| WiFi | 上段（大きい文字）WiFi SSID；下段（小さい文字）`网卡名 · 频率MHz` | リンク速度 `1081 Mbps`；下段に電波強度 `-54 dBm` |
| 非 WiFi | アダプター名のみ（1 行で垂直中央揃え） | 接続速度のみ `1.0 Gbps` |

左列のテキスト幅は、右列から**行ごと**に計算した使用可能幅に合わせて切り詰め、長すぎる場合は
省略記号を付けます（右列が押し出されることはありません）。

**「名前 → IP」の定時切り替え**：接続成功後、左列 1 行目はまず SSID / アダプター名を表示し、
`label_hold` 秒（デフォルト 3s）後にその場でそのアダプターの IP に置き換わり、ウィンドウが
閉じるまでそのままになります。2 行目と右列は最後まで変わらず、レイアウトもずれません。

| 時刻（デフォルト設定） | 左列 1 行目 | 左列 2 行目 | 右列 |
| --- | --- | --- | --- |
| 2.52s ~ 5.52s | `229028` | `Intel(R) Wi-Fi 6 AX201 160MHz · 5785MHz` | `1081 Mbps` / `-54 dBm` |
| 5.52s ~ 閉じるまで | `192.168.3.51` | 同上（変化なし） | 同上（変化なし） |

![IP 切り替えの前後（label_hold=1 時の合成プレビュー）](out/swap_wifi.png)

## コマンドライン引数

以下のはじめの 5 項目は `config.json` と同名で、**指定しなければ設定ファイルの値**を使います。

| 引数 | 説明 |
| --- | --- |
| `--config PATH` | 設定ファイルを指定（デフォルトはプロジェクトルートの `config.json`） |
| `--scale F` | 拡縮倍率を上書き |
| `--label-hold S` | 「名前の表示時間」を上書き |
| `--total S` | ウィンドウの総時間を上書き |
| `--duration S` | アニメーションのベースライン時間を上書き（内部的に 3~10 に制限） |
| `--grace S` / `--poll S` | DHCP 猶予 / フォールバックポーリング間隔を上書き |
| `--ignore LIST` | 無視するアダプターのキーワードを追加、カンマ区切り |
| `--prefer-ipv6` / `--no-prefer-ipv6` | 「IPv6 を優先表示」を上書き |
| `--no-swap` | 「名前 → IP」の切り替えを無効化 |
| `--lang cn\|en\|jp` | 表示言語を上書き |
| `--show-config` | 有効な設定を表示して終了 |
| `--preview` | 起動後に 1 回再生 |
| `--state` / `--kind` | 指定した状態（`connected`/`disconnected`/`dhcp_failed`）とサンプル種別を再生して終了 |
| `--demo` | 3 つの状態を順に再生して終了 |
| `--no-tray` | トレイアイコンを作成しない |
| `--quit` / `--restart` | 実行中のインスタンスに終了 / 再起動を通知 |

## ディレクトリ構成

```
config.json       設定ファイル（初回実行時に自動生成）
requirements.txt  依存関係リスト（pillow / numpy / pywin32）
README.md         簡体字中国語 / README_EN.md 英語 / README_JP.md 日本語
install.bat       依存関係をインストール
start.bat         バックグラウンド起動 / stop.bat で停止
install_autostart.bat     スタートアップに追加 / uninstall_autostart.bat で削除
net_hud/
  __main__.py      python -m net_hud のエントリーポイント
  config.py        設定ファイルの読み書き、既定値、クランプと説明
  i18n.py          画面文言テーブル（cn / en / jp）
  app.py           単一インスタンス、トレイメニュー、メインループ、コマンドライン
  watcher.py       アダプター状態の監視 + DHCP 猶予のステートマシン
  netinfo.py       IP Helper API によるアダプター列挙（サブプロセスなし、IPv4/IPv6 対応）
  wlaninfo.py      netsh wlan show interfaces の解析（中国語・英語ラベル）→ SSID/周波数/速度/dBm
  content.py       状態 → ページ文言/ロゴ/数値（「名前 → IP」の置換を含む）
  hud.py           レイヤードウィンドウ + 60fps フレームループ + 名前/停留/収尾/IP 切替のスケジューリング
  anim.py          キーフレームタイムライン（HudAnimations.cs の cue 体系を 1:1 で再現）
  easing.py        KeySpline 三次ベジェの評価
  renderer.py      1 フレームを RGBA で直接描画（numpy によるアンチエイリアス済みカプセル/波紋）
  theme.py         色/フォント/寸法（HudTheme.axaml に対応）
  logos.py         素材の読み込み、反転、トリミング、着色
  tray.py          トレイアイコンと右クリックメニュー（Shell_NotifyIcon）
  win32ui_ext.py   UpdateLayeredWindow レイヤードウィンドウ、DPI 対応
tools/
  autostart.py     スタートアップ自動起動のスイッチ（「スタートアップ」フォルダーのショートカットを作成/削除）
  preview.py       静的レンダリングの一覧（任意の cue 時点）、UI 確認用
  smoke.py         実機スモークテスト：HUD を実際に表示し、指定時刻にスクリーンショット
  live_test.py     実機エンドツーエンド：実際に WLAN を切断/再接続し、トリガー経路を検証して自動撮影
  test_watcher.py  ステートマシンの自己テスト（偽スナップショットで接続/切断/DHCP 猶予/無視を網羅）
  test_netinfo.py  netinfo の自己テスト（IPv6 リストを手動構築し、圧縮/フィルタ/選択を網羅）
  test_wlaninfo.py wlaninfo の自己テスト（中国語/英語ラベル、十六進数および GBK/UTF-8 の SSID、未接続）
```

## 実装のポイント

* **レイヤードウィンドウによるピクセル単位の透過**：`WS_EX_LAYERED|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE`
  \+ `UpdateLayeredWindow(ULW_ALPHA)` を使い、毎フレーム**乗算済みアルファの BGRA** を
  `CreateDIBSection`（top-down 32bpp）へ書き込みます。カラーキーを使わないため、角丸や波紋に
  ジャギーが出ません。
* **拡縮は描画段階で完了**：`base_scale = 0.8 × (dpi/96) × scale`（0.8 は原プロジェクトの
  GlobalScale、`scale` は設定ファイル由来）とし、すべての座標/文字サイズにこの係数を掛けます。
  途中でビットマップの resize は一切行わないため、どの倍率でも文字は最終的なピクセルサイズで
  レンダリングされ、ぼやけません。
* **配置**：ウィンドウの上端はワークエリア上端から 48 **論理**ピクセル下（さらに dpi 倍率を
  掛ける）に固定し、水平方向は厳密に中央揃えにします。したがって倍率はサイズにだけ影響し、
  「上端に張り付いた中央揃え」には影響しません。
* **アニメーションタイムラインの 1:1 再現**：原プロジェクト `Animations/HudAnimations.cs` の
  14 個の cue 定数（`TExpand=0.12`、`TMove=0.20`、`TTitle=0.25`、`TContract=0.36`、
  `TNumReady=0.42`、`THoldC=0.86`、`TClose=0.89` …）、`MapCue` の正規化セグメント分割、
  および `KS_In/Out/InOut/Smooth/BackOut` の各セグメント独立の KeySpline をすべて踏襲して
  います。入場セグメントの絶対時間は常に 2.52 s です。
* **波紋の方向**：`connected` は外側へ拡散し（`Ripple`、3 重の 1.5/2.0/2.5 倍）、
  `disconnected` / `dhcp_failed` は両端から内側へ収束して logo に吸い込まれます（`RippleIn`）。
  原プロジェクトのプラグ挿入/抜去と一致しています。

## 開発ツール

```bat
python tools\preview.py --state connected --kind wifi --label-hold 1 --cues 0.42,0.65,0.86
python tools\preview.py --state connected --kind wifi --ipv6 --label-hold 1    :: 看长 IPv6 缩字号
python tools\preview.py --state connected --kind wifi --lang jp                :: 看日文界面
python tools\smoke.py   --state connected --kind wifi --scale 2 --label-hold 1
python tools\live_test.py --profile <你的WiFi配置名>          :: 会真实断开/重连 WLAN
python tools\test_watcher.py
python tools\test_netinfo.py
python tools\autostart.py --status
```

## 既知の制限

* Windows 10/11 + Python 3.9 以上が必要です（開発環境は 3.12；依存関係は pillow / numpy /
  pywin32）。
* 非管理者権限でも実行できます；ただし一般ユーザーはアダプターを有効化/無効化できないため、
  実機のエンドツーエンドテストは `netsh wlan disconnect/connect` で行っています。
* WiFi の詳細は `netsh wlan show interfaces` から取得し、中国語と英語のラベルに対応済みです；
  電波強度の dBm はパーセンテージから `pct/2 - 100` で推定しています（Windows は dBm を
  直接提供しません）。
* 802.11 の SSID は生のバイト列であるため、非 ASCII バイトを含むと `netsh` はテキストではなく
  十六進数で出力します（例：`创新实验室` → `E5889BE696B0E5AE9EE9AA8CE5AEA4`。これはまさに
  その UTF-8 バイトです）。本プログラムは UTF-8、次にシステムの OEM コードページで復元を試み、
  可読なテキストに復元できない場合はプロファイル名にフォールバックします。純粋な ASCII の
  SSID が十六進数化されることはないため、誤変換は起きません。これらのケースは
  `tools/test_wlaninfo.py` で網羅しています。
* アダプターの状態変化のみを監視し、接続性のプローブは行いません（外部ネットワークに接続
  できるかどうかは判定範囲外です）。
* 本機（および多くのデフォルト設定の Windows）では、すべてのアダプターの「インターネット
  プロトコル バージョン 6 (TCP/IPv6)」が無効になっているため、実機では IPv6 アドレスが取得
  されず、IPv6 も表示されません；IPv6 の圧縮、リンクローカル/未完了アドレスのフィルタリング、
  優先度の選択ロジックは `tools/test_netinfo.py` で `IP_ADAPTER_UNICAST_ADDRESS` 連結リストを
  手動構築してカバーしています（20 項目のアサーション）。実機で検証したい場合は、先に
  ネットワークアダプターのプロパティで IPv6 を有効にするか、`prefer_ipv6` を `true` に
  設定してください。

参考プロジェクト [zmd-charge](https://github.com/QinAnze/zmd-charge) は MIT ライセンスです。
