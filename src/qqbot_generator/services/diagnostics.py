"""本机诊断：把常见故障定位到文件、版本、端口和 Key，并给出可执行修复。"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path

from qqbot_core.keyvault import get_key
from qqbot_core.providers import get as get_provider

from .. import paths
from . import napcat
from .ui_settings import UiSettings

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass
class Check:
    id: str
    title: str
    status: str
    detail: str
    action: str = ""
    action_label: str = ""


class Diagnostics:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.ui = UiSettings()

    def run(self) -> list[Check]:
        return [
            self._data(),
            self._qq(),
            self._napcat(),
            self._loader(),
            self._onebot(),
            self._model(),
            self._capabilities(),
            self._logs(),
        ]

    def _data(self) -> Check:
        try:
            for name in ("logs", "cache", "prompts"):
                (self.ctx.data_dir / name).mkdir(parents=True, exist_ok=True)
            free_mb = __import__("shutil").disk_usage(self.ctx.data_dir).free // (1024 * 1024)
            return Check("data", "数据目录", OK, f"{self.ctx.data_dir}，磁盘剩余 {free_mb} MB")
        except Exception as exc:
            return Check("data", "数据目录", FAIL, f"不可写：{exc}", "create_dirs", "创建目录")

    def _qq(self) -> Check:
        versions = napcat.qq_versions()
        if not versions:
            return Check("qq", "QQ", FAIL, "没有找到 QQNT 安装目录", "", "")
        latest = versions[-1]
        running = self.ctx.process.running
        return Check("qq", "QQ", OK, f"QQ {latest.name}；机器人{'运行中' if running else '未启动'}")

    def _napcat(self) -> Check:
        folder = self.ui.get_path("napcat_dir")
        if folder is None or not napcat.is_install(folder):
            found = napcat.find_candidates([str(folder)] if folder else None)
            folder = found[0] if found else None
        if folder is None:
            return Check("napcat", "NapCat", FAIL, "没找到 NapCat 目录", "open_napcat", "打开 NapCat 页")
        target = napcat.target_qq_version(folder)
        installed = napcat.qq_versions()
        current = installed[-1].name if installed else "未知"
        if target and target != current:
            return Check(
                "napcat", "NapCat", WARN,
                f"目录 {folder}；包目标 QQ {target}，当前 QQ {current}，版本不一致",
                "open_download", "下载匹配版本",
            )
        return Check("napcat", "NapCat", OK, f"{folder}；目标 QQ {target or '未声明'}")

    def _loader(self) -> Check:
        folder = self.ui.get_path("napcat_dir")
        if folder is None or not napcat.is_install(folder):
            found = napcat.find_candidates([str(folder)] if folder else None)
            folder = found[0] if found else None
        if folder is None:
            return Check("loader", "注入文件", FAIL, "找不到 NapCat 目录，无法检查 loadNapCat.js")
        target = napcat.loader_target(folder)
        if target is None:
            return Check("loader", "注入文件", FAIL, "没有找到 QQ 版本目录")
        if target.is_file():
            return Check("loader", "注入文件", OK, str(target))
        return Check(
            "loader", "注入文件", FAIL,
            f"QQ 版本目录缺少 loadNapCat.js：{target}",
            "copy_loader", "复制并修复（UAC）",
        )

    def _onebot(self) -> Check:
        host, port = self.ctx.cfg.onebot.host, int(self.ctx.cfg.onebot.port)
        try:
            with socket.create_connection((host, port), timeout=1.2):
                return Check("onebot", "OneBot 端口", OK, f"{host}:{port} 可连接")
        except OSError:
            if self.ctx.process.running:
                return Check("onebot", "OneBot 端口", FAIL, f"{host}:{port} 没有监听，机器人进程可能在重启或启动失败", "restart_bot", "重启机器人")
            return Check("onebot", "OneBot 端口", WARN, f"{host}:{port} 未监听（机器人未启动）", "start_bot", "启动机器人")

    def _model(self) -> Check:
        provider = get_provider(self.ctx.cfg.llm.provider_id)
        name = provider.name if provider else self.ctx.cfg.llm.provider_id
        key = self.ctx.cfg.resolve_api_key()
        if key:
            return Check("model", "文字 Provider", OK, f"{name} / {self.ctx.cfg.llm.model}")
        return Check("model", "文字 Provider", WARN, f"{name} 没有可用 Key，会走离线大脑", "open_model", "去模型页")

    def _capabilities(self) -> Check:
        f = self.ctx.cfg.features
        problems = []
        if f.vision:
            vid = f.vision_provider or self.ctx.cfg.llm.provider_id
            provider = get_provider(vid)
            if provider is None or "vision" not in provider.capabilities:
                problems.append("看图 Provider 不支持视觉")
            elif not (get_key(self.ctx.data_dir, f"cap_vision_{vid}") or (not f.vision_provider and self.ctx.cfg.resolve_api_key())):
                problems.append("看图 Provider 没有 Key")
        if f.voice_in and f.asr_provider != "local" and not get_key(self.ctx.data_dir, f"cap_asr_{f.asr_provider}"):
            problems.append("语音识别没有 Key")
        if f.voice_out and f.tts_provider != "edge" and not get_key(self.ctx.data_dir, f"cap_tts_{f.tts_provider}"):
            problems.append("语音合成没有 Key")
        if f.search:
            sp = f.search_provider
            if sp == "brave" and not get_key(self.ctx.data_dir, "brave"):
                problems.append("搜索没有 Brave Key")
            if sp == "tavily" and not get_key(self.ctx.data_dir, "tavily"):
                problems.append("搜索没有 Tavily Key")
        if problems:
            return Check("capabilities", "能力配置", WARN, "；".join(problems), "open_capabilities", "去能力页")
        return Check("capabilities", "能力配置", OK, "当前开启的能力都有对应的 Provider/Key")

    def _logs(self) -> Check:
        path = paths.data_dir() / "logs" / "bot.log"
        if not path.is_file():
            return Check("logs", "运行日志", WARN, "还没有 bot.log")
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        except OSError as exc:
            return Check("logs", "运行日志", WARN, f"读取失败：{exc}")
        hits = [line for line in lines if any(word in line for word in ("loadNapCat.js", "token is invalid", "ECONNREFUSED", "Traceback", "HTTP 401", "HTTP 402"))]
        if hits:
            return Check("logs", "运行日志", WARN, hits[-1][-180:], "open_logs", "查看日志")
        return Check("logs", "运行日志", OK, f"{path}，最近 300 行没有已知错误")

    def auto_fix_safe(self) -> list[str]:
        fixed: list[str] = []
        try:
            for name in ("logs", "cache", "prompts"):
                (self.ctx.data_dir / name).mkdir(parents=True, exist_ok=True)
            fixed.append("目录")
        except Exception:
            pass
        return fixed

    def folder(self) -> Path | None:
        folder = self.ui.get_path("napcat_dir")
        if folder is not None and napcat.is_install(folder):
            return folder
        found = napcat.find_candidates([str(folder)] if folder else None)
        return found[0] if found else None
