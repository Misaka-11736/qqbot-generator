"""配置读写：首次启动生成 config.toml，并把人格文件复制到用户目录。"""

from __future__ import annotations

import shutil

from qqbot_core.config import Config, load_config
from qqbot_core.persona import PRESETS, set_prompts_dir

from .. import paths


class ConfigService:
    def __init__(self) -> None:
        paths.ensure_dirs()
        self.path = paths.config_path()
        self.cfg: Config = self.load()

    # ---------- 读取 ----------

    def load(self) -> Config:
        self._seed_prompts()
        if not self.path.is_file():
            cfg = Config()
            cfg.bot_name = "小鲸"
            self._normalize(cfg)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(cfg.toml_dump(), "utf-8")
        cfg = load_config(self.path)
        self._normalize(cfg)
        set_prompts_dir(paths.prompts_dir())
        return cfg

    def reload(self) -> Config:
        self.cfg = self.load()
        return self.cfg

    # ---------- 保存 ----------

    def save(self, cfg: Config) -> None:
        self._normalize(cfg)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(cfg.toml_dump(), "utf-8")
        self.cfg = cfg

    def _normalize(self, cfg: Config) -> None:
        """把和安装位置相关的路径固定到用户数据目录。"""
        cfg.data_dir = paths.data_dir()
        cfg.log.dir = str(paths.logs_dir())
        if cfg.persona.preset not in PRESETS:
            cfg.persona.preset = "snark"

    # ---------- 人格文件 ----------

    def _seed_prompts(self) -> None:
        target = paths.prompts_dir()
        target.mkdir(parents=True, exist_ok=True)
        for name in PRESETS:
            dst = target / f"{name}.md"
            if dst.is_file():
                continue
            src = paths.resource("src", "qqbot_core", "prompts", f"{name}.md")
            if not src.is_file():
                src = paths.resource("qqbot_core", "prompts", f"{name}.md")
            if src.is_file():
                shutil.copyfile(src, dst)

    def reset_prompt(self, preset: str) -> str:
        """从安装包恢复某个人格的默认内容。"""
        src = paths.resource("src", "qqbot_core", "prompts", f"{preset}.md")
        if not src.is_file():
            src = paths.resource("qqbot_core", "prompts", f"{preset}.md")
        text = src.read_text("utf-8") if src.is_file() else ""
        (paths.prompts_dir() / f"{preset}.md").write_text(text, "utf-8")
        return text

    def open_data_dir(self) -> None:
        import os

        os.startfile(paths.data_dir())
