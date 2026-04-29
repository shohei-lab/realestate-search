"""アプリ設定とパス解決。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "re-search"

DEFAULT_CONFIG_TOML = """\
# re-search config

[api]
# 国土交通省 不動産情報ライブラリの APIキー（取得方法は同サイト参照）
# reinfolib_api_key = "..."

[scrape]
# 補助スクレイパは experimental/ で隔離されている。
# 個人利用 / 低頻度 / robots.txt 遵守 が前提。
# このフラグを true にしないと experimental スクレイパは動作しない。
i_accept_risks = false
rate_limit_rps = 0.5

[fengshui]
# 風水ルール辞書のパス（リポジトリ同梱の config/fengshui_rules.yaml）
# rules_path = "./config/fengshui_rules.yaml"
"""


@dataclass
class Config:
    """ユーザ設定とパスを束ねる。

    `Config.load()` で読み込み、`ensure_dirs()` で必要なディレクトリを作る。
    """

    db_path: Path
    data_dir: Path
    config_dir: Path
    config_file: Path
    cache_dir: Path
    reinfolib_api_key: str | None = None
    scrape_accept_risks: bool = False
    scrape_rate_limit_rps: float = 0.5
    fengshui_rules_path: Path | None = None

    @classmethod
    def load(cls) -> "Config":
        config_dir = Path(user_config_dir(APP_NAME))
        data_dir = Path(user_data_dir(APP_NAME))
        config_file = config_dir / "config.toml"
        db_path = data_dir / "re.db"
        cache_dir = data_dir / "cache"

        reinfolib_api_key = os.environ.get("REINFOLIB_API_KEY")
        scrape_accept_risks = False
        scrape_rate_limit_rps = 0.5
        fengshui_rules_path: Path | None = None

        if config_file.exists():
            with config_file.open("rb") as f:
                data = tomllib.load(f)
            api = data.get("api", {})
            scrape = data.get("scrape", {})
            fengshui = data.get("fengshui", {})
            reinfolib_api_key = api.get("reinfolib_api_key", reinfolib_api_key)
            scrape_accept_risks = bool(scrape.get("i_accept_risks", scrape_accept_risks))
            scrape_rate_limit_rps = float(
                scrape.get("rate_limit_rps", scrape_rate_limit_rps)
            )
            rp = fengshui.get("rules_path")
            if rp:
                fengshui_rules_path = Path(rp).expanduser()

        return cls(
            db_path=db_path,
            data_dir=data_dir,
            config_dir=config_dir,
            config_file=config_file,
            cache_dir=cache_dir,
            reinfolib_api_key=reinfolib_api_key,
            scrape_accept_risks=scrape_accept_risks,
            scrape_rate_limit_rps=scrape_rate_limit_rps,
            fengshui_rules_path=fengshui_rules_path,
        )

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def write_default_config_if_missing(self) -> bool:
        """設定ファイルが無ければデフォルトを書き出す。書いた場合 True。"""
        if self.config_file.exists():
            return False
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
        return True
