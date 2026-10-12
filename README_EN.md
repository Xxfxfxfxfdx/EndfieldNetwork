# NetworkHUD · Network Status "Dynamic Island"

[简体中文](README.md) · **English** · [日本語](README_JP.md)

A **network adapter status** HUD rebuilt in **Python 3.12 + Win32 layered windows**, imitating the UI and
animations of [QinAnze/zmd-charge](https://github.com/QinAnze/zmd-charge) (a laptop power status dynamic island).

When any network adapter changes between "disconnected ↔ connected", a pill pops out from the top center of
the screen: first the adapter type logo pops up → the pill grows taller to show the result text
(**Connected / Disconnected / DHCP Failed**) → it shrinks into an info capsule showing details (SSID, adapter
name, frequency, rate, signal) → after a hold it scales down and retracts as a whole.
Clicking the HUD or the tray menu retracts it early.

![Real device screenshot](out/live/contact_connected.png)

---

## Quick start

**First time** (install dependencies, once only):

```bat
install.bat         :: 自动 pip install -r requirements.txt
```

Requires Python 3.9+ (3.12 recommended) and the three libraries `pillow`, `numpy`, `pywin32`;
you can also run `python -m pip install -r requirements.txt` manually.

**Everyday use**:

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

**Run at startup**:

```bat
install_autostart.bat      :: 添加（在「启动」文件夹建一个快捷方式）
uninstall_autostart.bat    :: 移除
python tools\autostart.py --status      :: 查看当前状态
```

It only places a shortcut at `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NetworkHUD.lnk`
(target = `pythonw.exe run.pyw`), so it shows up under "Task Manager → Startup", where you can disable it or
just delete it; no administrator rights are needed and the registry is not touched.

Tray icon (notification area): left click = preview the current status, right click = menu (preview the three
states / open logs dir / exit).
Logs: `%TEMP%\NetworkHUD\log-YYYYMMDD.txt`.

---

## Configuration file

On first run a **`config.json`** is generated automatically in the project root (UTF-8, whole-line `//` and `#`
comments allowed). **Just save your edits — no restart needed** — before each trigger the program checks whether
the file changed and reloads it if so; the scale factor in particular adjusts the window immediately (measured
while running: changing `scale` from 1 to 1.7 made the window go straight from 672×108 to 1142×184 on the next
trigger, still pinned to the top and centered). Only `grace` / `poll` / `ignore` affect the watcher thread and
need a restart to take effect. Command line options override only the item you give explicitly; don't worry about
typos either — if parsing fails, the log warns and it falls back to the default value.

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

* **Scale factor**: `scale` only changes the display size; **the window is always pinned to the top of the work
  area and horizontally centered** (the top edge stays 48 logical pixels below the top, independent of the scale
  factor; when the factor is too large it overflows symmetrically on both sides and is still centered).
  Measured on this machine (2560 wide, dpi 144), `scale` at 0.5/1/2/3 → window 336×54 / 672×108 / 1344×216 /
  2016×324, with the capsule center always at `x=1280` and the top edge always at `y=72`.
* **The relation between `total` and `label_hold`**: info page hold time = `total − entry animation − exit
  animation`, derived automatically. Default `total=12` → entry 5.16s + hold 6.66s + exit 0.18s. If `total` is too
  small, or `label_hold` exceeds the hold time, the startup log gives a hint (in that case the IP may not get
  shown in time).
* **When the IP swap timer starts**: it counts from the moment the **info page appears** (cue `0.42`, about 2.52s
  with a 6s baseline); `label_hold` seconds later the first line on the left changes from the SSID / adapter name
  to that adapter's IP, until the window closes.
* **IP formatting**: only the address itself is shown (no `IP` prefix), IPv6 in lowercase hexadecimal (e.g.
  `2408:8214:5b3a:1f00:...:7a8b`), IPv4 in decimal (e.g. `192.168.3.51`). Long IPv6 addresses are automatically
  rendered at a smaller font size to fit, and only get an ellipsis if they still don't fit.
* `python -m net_hud --show-config` prints the configuration and timing allocation actually in effect.

---

## Interface language

**`lang`** in `config.json` decides the text of the HUD and the tray menu; the options are `"cn"` (Simplified
Chinese, default), `"en"` (English) and `"jp"` (日本語). Spellings such as `zh-CN`, `ja` and `English` are also
accepted; if it can't be recognised, the log warns and it falls back to `cn`. The command line `--lang en`
overrides it temporarily.

| Location | cn | en | jp |
| --- | --- | --- | --- |
| Connection succeeded | 连接成功 | Connected | 接続成功 |
| Connection lost | 断开连接 | Disconnected | 通信切断 |
| DHCP error | DHCP异常 | DHCP Failed | DHCPエラー |
| Tray · Preview current status | 预览当前网络状态 | Preview: Current Connection Status | 今のネットワーク状態をプレビュー |
| Tray · Open logs dir | 打开日志目录 | Open logs dir | ログフォルダーを開く |
| Tray · Exit | 退出 | Exit | プログラムを終了する |

The UI text uses the project's bundled HarmonyOS Sans SC (the original project's first-choice font), which covers
both Simplified Chinese and Japanese kana, so switching to Japanese needs no extra font installed. The taglines on
page one such as `/// NETWORK ONLINE` are design elements of the original project and stay in English in all three
languages. Just save `config.json` to switch (it takes effect on the next trigger, and the tray menu updates in
step).

![English interface](out/lang_en.png)

---

## Trigger rules

| Event | Condition | Result |
| --- | --- | --- |
| Adapter comes online | `oper_status` changes from disconnected to Up, and it **already has a non-169.254 IP** | show `connected` immediately |
| Adapter comes online (DHCP not ready) | On coming online the IP is empty or all `169.254.*` | enter a **10 second grace period** of polling |
| └ IP obtained during the grace period | A non-`169.254.*` address appears within `--grace` seconds | show `connected` immediately |
| └ Still no IP when the grace period ends | More than `--grace` (default 10) seconds | show `dhcp_failed` |
| Adapter goes offline | `oper_status` changes from Up to disconnected | show `disconnected` |

* Immediacy: `NotifyIpInterfaceChange` (IP Helper API) is registered for event-driven operation, plus a `--poll`
  (default 2s) fallback poll. Measured latency from a disconnect event to the HUD popping up is about **0.3 s**.
* It only reacts to **changes**; adapters that are already online when the program starts do not trigger it.
* Virtual adapters are ignored (name/description containing `Microsoft Wi-Fi Direct Virtual Adapter`,
  `Wi-Fi Direct`); more can be added with `--ignore keyword1,keyword2`.

## The three states

| state | Page 1 text | tagline | logo |
| --- | --- | --- | --- |
| `connected` | Connected | `/// NETWORK ONLINE` | by adapter kind (see below) |
| `disconnected` | Disconnected | `/// LINK DOWN` | `nointernet` |
| `dhcp_failed` | DHCP Failed | `/// DHCP FAILED` | `nointernet` (the second line shows the current IP) |

The logo reuses the movement of the original project's "battery icon": it first pops up in the middle of the
capsule, then slides to the left, finally coming to rest at the far left of the info page.

## Adapter kinds

| kind | Detection | logo |
| --- | --- | --- |
| `wifi` | `if_type == IEEE80211`, or name/description containing `WLAN`/`Wi-Fi`/`wireless`/`无线` | `wifi.png` |
| `btpan` | Name/description containing `Bluetooth`/`蓝牙` | `btpan.png` |
| `usb_rndis` | Name/description containing `NDIS` (NDIS adapters containing "以太网" fall into this kind, corresponding to phone USB tethering) | `usb_rndis.png` |
| `ethernet` | All remaining wired adapters | `ethernet.png` |

The binary images in `assets/` are processed automatically: white-background artwork is **inverted** to white
glyphs on black, then the whitespace is cropped away by the glyph bbox, and it is drawn on a dark rounded
backplate (`#141313`); the rounded state uses a solid circular base, the info page a square backplate.

## Info page layout

| Adapter | Left column | Right column |
| --- | --- | --- |
| WiFi | Top (larger text) WiFi SSID; bottom (smaller text) `网卡名 · 频率MHz` | Link rate `1081 Mbps`; bottom line signal strength `-54 dBm` |
| Non-WiFi | Only the adapter name (single line, vertically centered) | Only the connection rate `1.0 Gbps` |

The text width of the left column is clipped to the available width computed **line by line** from the right
column, with an ellipsis when too long (the right column is never squeezed out).

**Scheduled "name → IP" swap**: after a successful connection, the first line of the left column shows the
SSID / adapter name first, and after `label_hold` seconds (default 3s) it is replaced in place by that adapter's
IP, until the window closes. The second line and the right column stay unchanged the whole time, with no layout
shift.

| Time (default config) | Left column line 1 | Left column line 2 | Right column |
| --- | --- | --- | --- |
| 2.52s ~ 5.52s | `229028` | `Intel(R) Wi-Fi 6 AX201 160MHz · 5785MHz` | `1081 Mbps` / `-54 dBm` |
| 5.52s ~ close | `192.168.3.51` | Same as above (unchanged) | Same as above (unchanged) |

![Before and after the IP swap (composite preview with label_hold=1)](out/swap_wifi.png)

## Command line options

The first 5 items below have the same names as in `config.json`, and **if not given, the value from the
configuration file is used**.

| Option | Description |
| --- | --- |
| `--config PATH` | Specify the configuration file (defaults to `config.json` in the project root) |
| `--scale F` | Override the scale factor |
| `--label-hold S` | Override the "name display duration" |
| `--total S` | Override the total window duration |
| `--duration S` | Override the animation baseline duration (internally clamped to 3~10) |
| `--grace S` / `--poll S` | Override the DHCP grace / fallback poll interval |
| `--ignore LIST` | Add adapter keywords to ignore, comma separated |
| `--prefer-ipv6` / `--no-prefer-ipv6` | Override "prefer displaying IPv6" |
| `--no-swap` | Disable the "name → IP" swap |
| `--lang cn\|en\|jp` | Override the interface language |
| `--show-config` | Print the effective configuration and exit |
| `--preview` | Play once right after startup |
| `--state` / `--kind` | Play the given state (`connected`/`disconnected`/`dhcp_failed`) and example kind, then exit |
| `--demo` | Play the three states in sequence, then exit |
| `--no-tray` | Do not create a tray icon |
| `--quit` / `--restart` | Tell a running instance to quit / restart |

## Project layout

```
config.json       Configuration file (auto-generated on first run)
requirements.txt  Dependency list (pillow / numpy / pywin32)
README.md         Simplified Chinese docs / README_EN.md English / README_JP.md Japanese
install.bat       Install dependencies
start.bat         Start in the background / stop.bat to stop
install_autostart.bat     Add to startup / uninstall_autostart.bat to remove
net_hud/
  __main__.py      python -m net_hud entry point
  config.py        Configuration file read/write, defaults, clamping and descriptions
  i18n.py          UI text tables (cn / en / jp)
  app.py           Single instance, tray menu, main loop, command line
  watcher.py       Adapter status watching + DHCP grace state machine
  netinfo.py       IP Helper API adapter enumeration (no subprocesses, includes IPv4/IPv6)
  wlaninfo.py      netsh wlan show interfaces parsing (Chinese and English labels) → SSID/frequency/rate/dBm
  content.py       State → page text/logo/values (including the "name → IP" substitution)
  hud.py           Layered window + 60fps frame loop + name/hold/exit/IP-swap scheduling
  anim.py          Keyframe timeline (a 1:1 reimplementation of the cue system in HudAnimations.cs)
  easing.py        KeySpline cubic Bezier evaluation
  renderer.py      Direct RGBA drawing of one frame (numpy anti-aliased capsule/ripples)
  theme.py         Colors/fonts/dimensions (corresponding to HudTheme.axaml)
  logos.py         Asset loading, inversion, cropping, tinting
  tray.py          Tray icon and right-click menu (Shell_NotifyIcon)
  win32ui_ext.py   UpdateLayeredWindow layered windows, DPI awareness
tools/
  autostart.py     Startup-at-boot switch (writes/deletes the shortcut in the "Startup" folder)
  preview.py       Static render sheet (any moment of the cues), for UI checking
  smoke.py         Real device smoke test: shows the HUD and takes screenshots at given moments
  live_test.py     Real device end to end: really disconnect/reconnect the WLAN, verify the trigger chain and capture screenshots automatically
  test_watcher.py  State machine self-test (fake snapshots covering online/offline/DHCP grace/ignore)
  test_netinfo.py  netinfo self-test (hand-built IPv6 linked lists covering compression/filtering/selection)
  test_wlaninfo.py wlaninfo self-test (Chinese/English labels, hex-encoded and GBK/UTF-8 SSIDs, disconnected)
```

## Implementation notes

* **Per-pixel transparency via a layered window**: `WS_EX_LAYERED|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE` +
  `UpdateLayeredWindow(ULW_ALPHA)`, writing **premultiplied-alpha BGRA** into a `CreateDIBSection`
  (top-down 32bpp) every frame. No color key is used, so rounded corners and ripples have no fringing.
* **Scaling happens in the drawing stage**: `base_scale = 0.8 × (dpi/96) × scale` (0.8 is the original project's
  GlobalScale, `scale` comes from the configuration file); all coordinates/font sizes are multiplied by that
  factor and no bitmap resize is done anywhere, so text is rendered at its final pixel size at any factor and
  stays sharp.
* **Positioning**: the top edge of the window is fixed 48 **logical** pixels below the top of the work area
  (then multiplied by the dpi scale) and it is strictly horizontally centered, so the factor only affects size,
  not the "pinned to the top and centered" behavior.
* **Animation timeline reimplemented 1:1**: the 14 cue constants from the original project's
  `Animations/HudAnimations.cs` (`TExpand=0.12`, `TMove=0.20`, `TTitle=0.25`, `TContract=0.36`, `TNumReady=0.42`,
  `THoldC=0.86`, `TClose=0.89` …), the `MapCue` normalized segmentation, and the independent KeySpline for each of
  `KS_In/Out/InOut/Smooth/BackOut` have all been carried over; the absolute duration of the entry segment is
  always 2.52 s.
* **Ripple direction**: `connected` spreads outward (`Ripple`, three rings at 1.5/2.0/2.5 times),
  `disconnected` / `dhcp_failed` converge inward from both ends and are sucked away by the logo (`RippleIn`),
  matching the original project's plug-in/plug-out behavior.

## Development tools

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

## Known limitations

* Requires Windows 10/11 + Python 3.9 or higher (the development environment is 3.12; dependencies are
  pillow / numpy / pywin32).
* It runs without administrator rights; but a normal user cannot enable/disable adapters, so the real device
  end-to-end test is done with `netsh wlan disconnect/connect`.
* WiFi details come from `netsh wlan show interfaces`, with both Chinese and English labels supported; the signal
  strength in dBm is estimated from the percentage as `pct/2 - 100` (Windows does not provide dBm directly).
* An 802.11 SSID is a raw byte array, so whenever it contains non-ASCII bytes `netsh` stops printing it as
  text and prints its hex instead (e.g. `创新实验室` → `E5889BE696B0E5AE9EE9AA8CE5AEA4`, which is exactly
  its UTF-8 bytes). The program restores it by trying UTF-8 and then the system OEM code page, and falls back
  to the profile name when the bytes cannot be decoded into readable text. A pure-ASCII SSID is never
  hex-encoded, so it can never be mis-decoded. `tools/test_wlaninfo.py` covers these cases.
* It only watches adapter status changes and does no connectivity probing (whether the internet is actually
  reachable is outside the scope of the decision).
* On this machine (and on most Windows installs with default settings), "Internet Protocol Version 6 (TCP/IPv6)"
  is disabled on all adapters, so no IPv6 address is obtained on a real device and IPv6 is never displayed;
  the IPv6 compression, link-local/incomplete address filtering and priority selection logic is covered by
  `tools/test_netinfo.py` with hand-built `IP_ADAPTER_UNICAST_ADDRESS` linked lists (20 assertions). To verify it
  on a real device you can first tick IPv6 in the adapter properties, or set `prefer_ipv6` to `true`.

The reference project [zmd-charge](https://github.com/QinAnze/zmd-charge) is MIT licensed.
