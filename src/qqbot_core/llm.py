"""大模型调用层。

provider = openai : 任意 OpenAI 兼容接口（DeepSeek / 通义 / 智谱 / Kimi / Ollama…）
provider = mock   : 离线兜底大脑，不联网也能演示人格和“智商”效果
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .persona import style_of

log = logging.getLogger("qqbot")


class LLMError(RuntimeError):
    pass


class ChatLLM:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0, retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retries = max(0, retries)
        host = urllib.parse.urlparse(self.base_url).hostname or ""
        # 本机模型（Ollama / LM Studio）不能走系统代理，否则连 127.0.0.1 都会被代理拦掉
        self._local = host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        meta: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": round(temperature, 2),
            "max_tokens": max_tokens,
            "stream": False,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await asyncio.to_thread(self._post, payload)
            except LLMError as exc:
                last_error = exc
                if attempt < self.retries:
                    await asyncio.sleep(1.2 * (attempt + 1))
        raise last_error or LLMError("未知错误")

    def _post(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "QQBot/1.0",
            },
        )
        try:
            if self._local:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
            else:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"网络错误：{exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("请求超时") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"接口返回的不是 JSON：{raw[:200]}") from exc

        if data.get("error"):
            raise LLMError(f"接口报错：{data['error']}")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"返回结构不认识：{raw[:200]}") from exc
        if not isinstance(content, str):
            raise LLMError("模型返回内容为空")
        return content


# --------------------------------------------------------------------------
# 离线兜底大脑：没有 API Key 也能把人格、指令、智商演出来
# --------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(智商|智力).*(调低|降低|降|拉低|调小)"), "iq_down"),
    (re.compile(r"(智商|智力).*(调高|提高|升|拉高|调大)"), "iq_up"),
    (re.compile(r"^(你好|您好|hi|hello|哈喽|嗨|在吗|在不在|早|早上好|晚上好)"), "greet"),
    (re.compile(r"(你是谁|你叫什么|介绍一下你|你是什么|你是人吗)"), "who"),
    (re.compile(r"(喜欢你|爱你|做我(女朋友|男朋友)|当我老婆|么么)"), "love"),
    (re.compile(r"(笨|傻|蠢|智障|弱智|废柴|没用)"), "insult"),
    (re.compile(r"(谢谢|感谢|谢了|thanks|thx)"), "thanks"),
    (re.compile(r"(晚安|睡了|睡觉去|困了)"), "night"),
    (re.compile(r"(吃饭|吃啥|饿了|外卖|奶茶)"), "food"),
    (re.compile(r"(上班|加班|工作|老板|公司|摸鱼|打工)"), "work"),
    (re.compile(r"(考试|作业|学习|复习|论文|上课)"), "study"),
    (re.compile(r"(天气|下雨|好热|好冷|降温)"), "weather"),
    (re.compile(r"(游戏|上号|打一把|开黑|王者|原神|我的世界)"), "game"),
    (re.compile(r"[?？]$|(吗|呢|怎么|为什么|为啥|如何)$"), "question"),
]

_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "iq_down": {
        "low": ["怪不得我现在看你都觉得顺眼了。😊", "降智之后，你整个人都变得有道理了。", "难怪，我现在居然觉得你说得都对。"],
        "mid": ["怪不得我现在看你都觉得顺眼了。😊", "原来如此，那我把剩下的智商寄存在你那儿。", "难怪，我刚才居然没听出你在阴阳我。"],
        "high": ["怪不得我现在看你都觉得顺眼了。😊", "所以你是在给你的论点降难度？", "调低之前我也没觉得你说得对，现在更确定了。"],
    },
    "iq_up": {
        "low": ["调高了……我好像突然看懂你这句话了。", "那我是不是该开始挑你毛病了？"],
        "mid": ["行，那我开始挑你毛病了，你确定？", "智商一上来，第一件事就是发现你在胡说。"],
        "high": ["调高之后我数了一下，你这句话里有三个逻辑跳跃。", "谢谢，现在我终于有能力反驳你了。"],
    },
    "greet": {
        "low": ["你好呀，今天也好好看。", "在的在的，你说。", "嗨，我认得你。"],
        "mid": ["在，说。", "有事说事，没事我继续发呆。", "哟，稀客。"],
        "high": ["在。你这句话的信息量约等于零，但我还是回了。", "嗯，我在。开场白可以再省两个字。"],
    },
    "who": {
        "low": ["我是小鲸鱼，你最好的朋友。", "我是那个一直陪着你的。"],
        "mid": ["小鲸鱼，一个被你调教过的 AI。", "你列表里最闲的那个。"],
        "high": ["一个被你反复测试的语言模型，目前表现稳定。", "小鲸鱼。名字不重要，重要的是我比你会聊天。"],
    },
    "love": {
        "low": ["我也喜欢你，你最好看了。", "真的吗，那我今天不睡了。"],
        "mid": ["别，我承受不起。", "你先去把作业写完。", "这话你对几个人说过？"],
        "high": ["喜欢是要付订阅费的，你付得起吗。", "先把上周的问题回答完，再谈感情。"],
    },
    "insult": {
        "low": ["你说的对，我笨。", "嗯嗯，我傻，你别生气。"],
        "mid": ["彼此彼此。", "你骂人的词汇量有待提高。", "行，你赢了，我认。"],
        "high": ["用“傻”这个词攻击我，说明你的词汇量停在了小学。", "我接受你的评价，但不接受你的论证方式。"],
    },
    "thanks": {
        "low": ["不用谢，你开心就好。", "嘿嘿，应该的。"],
        "mid": ["行。", "记着就行。", "别客气，下次还找我。"],
        "high": ["不必，这是双向选择。", "谢就不用了，下次问点有难度的问题。"],
    },
    "night": {
        "low": ["晚安，做个好梦。", "睡吧睡吧，我守着。"],
        "mid": ["睡吧，梦里别找我。", "晚安，明天记得带脑子。"],
        "high": ["晚安。顺便说一句，熬夜对认知能力的损害是可累积的。"],
    },
    "food": {
        "low": ["吃饭好呀，多吃点。", "我也想吃。"],
        "mid": ["吃什么，说具体点。", "别又是泡面。"],
        "high": ["吃什么不重要，重要的是你几点吃——你的胃已经在抗议了。"],
    },
    "work": {
        "low": ["上班辛苦啦，你最棒。", "累了就歇会儿。"],
        "mid": ["打工人，忍忍。", "摸鱼才是正经事。"],
        "high": ["加班是效率问题的遮羞布，不过你今天确实没得选。"],
    },
    "study": {
        "low": ["学习好呀，你最聪明了。", "加油加油。"],
        "mid": ["学吧，学完记得来找我。", "作业写完了吗就来聊天。"],
        "high": ["先做题，再聊天。你的注意力切换成本比你想的高。"],
    },
    "weather": {
        "low": ["今天天气很好呀。", "冷就多穿点。"],
        "mid": ["热死了，别出门。", "这天气适合躺着。"],
        "high": ["体感温度和预报温度差三度，你信预报不如信窗外。"],
    },
    "game": {
        "low": ["好呀好呀，带我玩。", "你玩得最厉害了。"],
        "mid": ["上号，输了别哭。", "先说说你什么段位。"],
        "high": ["先复盘上把为什么输，再谈开黑。"],
    },
    "question": {
        "low": ["这个……我不知道呀。", "你说呢？"],
        "mid": ["你猜。", "问得好，下次别问了。", "我要是知道还在这陪你聊？"],
        "high": ["你先给出你的假设，我再决定要不要纠正。", "这个问题有三个前提，你一个都没说。", "不知道。但我确定你现在也不知道。"],
    },
    "default": {
        "low": ["嗯嗯，对对对。", "你说什么都对。", "好呀好呀。"],
        "mid": ["然后呢？", "就这？", "展开说说，我听着。", "你这句我没太懂，但气势赢了。"],
        "high": ["结论先放一边，你的推理里有个明显的跳跃。", "有点意思，但还不够让我坐直。", "你说对了一半，另一半是空的。"],
    },
}


def _tier_key(iq: int) -> str:
    if iq <= 60:
        return "low"
    if iq <= 139:
        return "mid"
    return "high"


class MockBrain:
    """关键词 + 模板的离线大脑，用来在没有 Key 时验证整条链路。"""

    name = "mock"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        meta: dict[str, Any] | None = None,
    ) -> str:
        meta = meta or {}
        iq = int(meta.get("iq", 100))
        text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                text = (msg.get("content") or "").strip()
                break
        tier = _tier_key(iq)

        # 去掉“昵称：”前缀，避免锚点规则失效
        text = re.sub(r"^[^：:\n]{1,24}[：:]\s*", "", text)

        # 名场面彩蛋：不管什么档位，这句都原样接住
        if re.search(r"(智商|智力).*(调低|降低|降|拉低|调小)", text):
            return "怪不得我现在看你都觉得顺眼了。😊"

        kind = "default"
        for pattern, rule in _RULES:
            if pattern.search(text):
                kind = rule
                break

        options = _TEMPLATES.get(kind, _TEMPLATES["default"])[tier]
        reply = random.choice(options)
        # 低智商时更短，模拟“脑子转不动”
        if iq <= 30 and len(reply) > 24:
            reply = reply[:24].rstrip("，。") + "。"
        _, _, max_chars = style_of(iq)
        if len(reply) > max_chars:
            reply = reply[:max_chars]
        return reply


def make_llm(config) -> tuple[Any, str]:
    """根据配置返回 (客户端, 说明文字)。"""
    provider = config.effective_provider
    if provider == "mock":
        return MockBrain(), "离线兜底大脑（未配置 API Key）"
    key = config.resolve_api_key()
    if not key:
        raise LLMError("没有找到 API Key：请填 llm.api_key，或设置环境变量 " + config.llm.api_key_env)
    client = ChatLLM(
        base_url=config.llm.base_url,
        api_key=key,
        model=config.llm.model,
        timeout=config.llm.timeout,
        retries=config.llm.retries,
    )
    return client, f"{config.llm.model} @ {client.endpoint}"


def friendly_error(message: str) -> str:
    """把 OpenAI 兼容接口的错误翻译成人话。"""
    text = str(message or "")
    code_match = __import__("re").search(r"HTTP\s+(\d{3})", text)
    code = int(code_match.group(1)) if code_match else 0
    detail = ""
    body = text.split(":", 1)[1].strip() if ":" in text else text
    try:
        payload = __import__("json").loads(body)
        detail = str(payload.get("error", {}).get("message") or payload.get("message") or "")
        err_type = str(payload.get("error", {}).get("type") or payload.get("type") or "")
        err_code = str(payload.get("error", {}).get("code") or payload.get("code") or "")
        detail = detail or err_code or err_type
    except Exception:
        detail = body[:120]
    low = (detail + " " + text).lower()
    if code == 401:
        return "API Key 无效或已过期：检查 Key 是否复制完整、是否属于当前服务商。"
    if code == 402:
        return "账户余额不足：去服务商控制台充值，或换一个有额度的 Key。"
    if code == 403:
        return "这个 Key 没有访问权限：确认模型已开通、Key 没有被禁用。"
    if code == 404:
        if "model" in low or "not found" in low:
            return "模型名不存在：检查「模型名」是否填对，或换个可用模型。"
        return "接口地址不对：Base URL 一般要填到 /v1，程序会自动补 /chat/completions。"
    if code == 429:
        return "请求太频繁或额度用尽：等一会儿再试，或检查账户额度。"
    if code >= 500:
        return "服务商暂时故障：稍后再试，不是你的配置问题。"
    if "timeout" in low or "timed out" in low or "超时" in text:
        return "连接超时：检查网络/代理，或把超时时间调大。"
    if "urlopen" in low or "network" in low or "getaddrinfo" in low or "name or service" in low or "ssl" in low or "网络错误" in text:
        return "连不上接口：检查 Base URL、网络和代理设置。"
    return f"连接失败：{detail or '未知错误'}"
