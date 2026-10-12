"""界面文案的多语言表（简体中文 / English / 日本語）。

程序里**用户可见**的文案都集中在这里；日志、命令行帮助、注释仍是中文，
因为使用者是排障的人，而不是看 HUD 的人。

语言来自 `config.json` 的 `lang`（`"cn"` / `"en"` / `"jp"`，默认 `"cn"`），
也可以用命令行 `--lang` 临时覆盖。
"""

from __future__ import annotations

__all__ = [
    "LANGS",
    "DEFAULT_LANG",
    "LANG_NAMES",
    "normalize",
    "text",
    "title",
    "app_title",
    "listening",
]

#: 可选的规范语言代码
LANGS = ("cn", "en", "jp")
DEFAULT_LANG = "cn"

#: 语言代码 → 自称（写进日志与 `--show-config`）
LANG_NAMES = {
    "cn": "简体中文",
    "en": "English",
    "jp": "日本語",
}

#: 宽容写法 → 规范代码（方便填 zh-CN / ja / English 之类）
_ALIASES = {
    "cn": "cn", "zh": "cn", "zh-cn": "cn", "zh_cn": "cn", "zh-hans": "cn",
    "chs": "cn", "chinese": "cn", "simplified chinese": "cn", "中文": "cn",
    "en": "en", "en-us": "en", "en_us": "en", "eng": "en", "english": "en",
    "jp": "jp", "ja": "jp", "ja-jp": "jp", "ja_jp": "jp", "jpn": "jp",
    "japanese": "jp", "日本語": "jp",
}

#: 文案表。键用点分层级；`{}` 占位由 `text()` 的 kwargs 填充。
STRINGS: dict[str, dict[str, str]] = {
    "cn": {
        "app.title": "网络状态监测 HUD",
        "tray.listening": "监听中",

        "title.connected": "连接成功",
        "title.disconnected": "断开连接",
        "title.dhcp_failed": "DHCP异常",

        "menu.preview_current": "预览当前网络状态",
        "menu.preview_item": "预览：{title}",
        "menu.open_log": "打开日志目录",
        "menu.exit": "退出",
    },
    "en": {
        "app.title": "Network Status HUD",
        "tray.listening": "listening",

        "title.connected": "Connected",
        "title.disconnected": "Disconnected",
        "title.dhcp_failed": "DHCP Failed",

        "menu.preview_current": "Preview: Current Connection Status",
        "menu.preview_item": "Preview: {title}",
        "menu.open_log": "Open logs dir",
        "menu.exit": "Exit",
    },
    "jp": {
        "app.title": "ネットワーク状態モニター HUD",
        "tray.listening": "監視中",

        "title.connected": "接続成功",
        "title.disconnected": "通信切断",
        "title.dhcp_failed": "DHCPエラー",

        "menu.preview_current": "今のネットワーク状態をプレビュー",
        "menu.preview_item": "プレビュー: {title}",
        "menu.open_log": "ログフォルダーを開く",
        "menu.exit": "プログラムを終了する",
    },
}


def normalize(lang: object) -> str:
    """把任意输入收敛成 `LANGS` 里的一个代码；认不出来就退回默认。"""
    key = str(lang or "").strip().lower()
    return _ALIASES.get(key, DEFAULT_LANG)


def text(lang: str, key: str, **kw) -> str:
    """取一条文案；缺失时退回默认语言，再缺失就返回键名（便于发现漏译）。"""
    code = normalize(lang)
    table = STRINGS.get(code) or {}
    value = table.get(key)
    if value is None:
        value = (STRINGS.get(DEFAULT_LANG) or {}).get(key)
    if value is None:
        return key
    return value.format(**kw) if kw else value


def title(state: str, lang: str) -> str:
    """第一页主标题（三种状态）。"""
    return text(lang, f"title.{state}")


def app_title(lang: str) -> str:
    return text(lang, "app.title")


def listening(lang: str) -> str:
    return text(lang, "tray.listening")
