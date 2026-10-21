"""API Provider 注册表：单一 Provider 决定聊天/视觉能力。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    base_url: str
    chat_model: str
    capabilities: tuple[str, ...] = ("chat",)
    vision_model: str = ""
    asr_model: str = ""
    tts_model: str = ""
    tts_voice: str = ""
    key_url: str = ""
    note: str = ""
    models: tuple[str, ...] = field(default_factory=tuple)


PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        "deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat",
        ("chat",), key_url="https://platform.deepseek.com/api_keys",
        note="文本/推理强，不支持图片和语音。",
        models=("deepseek-chat", "deepseek-reasoner"),
    ),
    "qwen": Provider(
        "qwen", "阿里云百炼 Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus",
        ("chat", "vision"), vision_model="qwen3-vl-plus",
        key_url="https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        note="文本、视觉都支持；语音/图像生成暂未接入。",
        models=("qwen-plus", "qwen-max", "qwen-turbo"),
    ),
    "siliconflow": Provider(
        "siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-72B-Instruct",
        ("chat", "vision", "asr", "tts"), vision_model="Qwen/Qwen2.5-VL-72B-Instruct",
        asr_model="FunAudioLLM/SenseVoiceSmall", tts_model="FunAudioLLM/CosyVoice2-0.5B", tts_voice="anna",
        key_url="https://cloud.siliconflow.cn/account/ak",
        note="聚合多家模型，文本/视觉可选。",
        models=("Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"),
    ),
    "openrouter": Provider(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini",
        ("chat", "vision"), vision_model="openai/gpt-4o-mini",
        key_url="https://openrouter.ai/settings/keys",
        note="聚合模型，按模型计费；需要模型名带厂商前缀。",
        models=("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"),
    ),
    "openai": Provider(
        "openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini",
        ("chat", "vision", "asr", "tts"), vision_model="gpt-4o-mini",
        asr_model="whisper-1", tts_model="gpt-4o-mini-tts", tts_voice="alloy",
        key_url="https://platform.openai.com/api-keys",
        note="文本/视觉都支持；国内网络可能需代理。",
        models=("gpt-4o-mini", "gpt-4o"),
    ),
    "groq": Provider(
        "groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",
        ("chat", "asr", "tts"), key_url="https://console.groq.com/keys",
        asr_model="whisper-large-v3", tts_model="playai-tts", tts_voice="Fritz-PlayAI",
        note="速度极快，暂未启用视觉模型。",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    ),
    "zhipu": Provider(
        "zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash",
        ("chat", "vision"), vision_model="glm-4v-flash",
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
        note="文本/视觉；图像生成和语音暂未接入。",
        models=("glm-4-flash", "glm-4-plus", "glm-4v-flash"),
    ),
    "ollama": Provider(
        "ollama", "本地 Ollama", "http://127.0.0.1:11434/v1", "llama3.1",
        ("chat", "vision"), vision_model="qwen2.5vl",
        note="本地免费；视觉需要装 qwen2.5vl 等模型。",
        models=("llama3.1", "qwen2.5", "qwen2.5vl"),
    ),
}

DEFAULT_ID = "deepseek"


def get(provider_id: str) -> Provider | None:
    return PROVIDERS.get(provider_id or DEFAULT_ID) or PROVIDERS.get(DEFAULT_ID)


def supports(provider_id: str, capability: str) -> bool:
    provider = get(provider_id)
    return bool(provider and capability in provider.capabilities)


def choices() -> list[Provider]:
    return list(PROVIDERS.values())
