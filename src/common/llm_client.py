"""统一的 LLM 客户端模块。

支持 OpenAI Chat Completions 与 Anthropic Messages 兼容接口，用于报告生成、
AI 助手、对话式推荐和推荐理由整理等场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.common.config import get_env
from src.common.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PROVIDER = "anthropic"
DEFAULT_BASE_URL = "https://anyrouter.top/v1"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_TIMEOUT = 30
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1024
ANTHROPIC_VERSION = "2023-06-01"


@dataclass(frozen=True)
class LLMConfig:
    """LLM 配置。"""

    provider: str
    api_key: str
    base_url: str
    model: str
    timeout: int
    temperature: float


class LLMClientError(Exception):
    """LLM 客户端异常。"""


def get_llm_config(
    temperature: float | None = None,
    model: str | None = None,
) -> LLMConfig:
    """获取 LLM 配置。

    优先读取环境变量：
    - LLM_PROVIDER：anthropic 或 openai
    - ANTHROPIC_API_KEY 或 LLM_API_KEY 或 OPENAI_API_KEY 或 DEEPSEEK_API_KEY
    - LLM_BASE_URL 或 ANTHROPIC_BASE_URL 或 OPENAI_BASE_URL 或 DEEPSEEK_BASE_URL
    - LLM_MODEL 或 OPENAI_MODEL

    Args:
        temperature: 温度参数，未指定时使用环境变量或默认值
        model: 模型名称，未指定时使用环境变量或默认值

    Raises:
        LLMClientError: 未配置 API Key
    """
    provider = normalize_provider(get_env("LLM_PROVIDER", DEFAULT_PROVIDER))
    api_key = resolve_api_key(provider)
    if not api_key:
        raise LLMClientError(
            "未配置 LLM API Key，请设置 ANTHROPIC_API_KEY、LLM_API_KEY、OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量"
        )

    base_url = (
        get_env("LLM_BASE_URL")
        or get_env("ANTHROPIC_BASE_URL")
        or get_env("OPENAI_BASE_URL")
        or get_env("DEEPSEEK_BASE_URL")
        or DEFAULT_BASE_URL
    )

    resolved_model = model or get_env("LLM_MODEL") or get_env("OPENAI_MODEL") or DEFAULT_MODEL

    resolved_temperature = temperature if temperature is not None else parse_float_env("LLM_TEMPERATURE", DEFAULT_TEMPERATURE)

    timeout = parse_int_env("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=resolved_model,
        timeout=timeout,
        temperature=resolved_temperature,
    )


def chat(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """调用 LLM 接口。

    Args:
        messages: 消息列表，格式 [{"role": "system/user/assistant", "content": "..."}]
        temperature: 温度参数，控制回复的随机性（0.0-2.0）
        model: 模型名称，未指定时使用配置
        max_tokens: 最大生成 token 数

    Returns:
        LLM 生成的回复内容

    Raises:
        LLMClientError: API 调用失败
    """
    try:
        import requests
    except ImportError as exc:
        raise LLMClientError("缺少 requests 依赖，请安装 requirements.txt") from exc

    config = get_llm_config(temperature=temperature, model=model)
    if config.provider == "anthropic":
        return anthropic_messages_chat(requests, config, messages, max_tokens=max_tokens)
    return openai_chat_completions(requests, config, messages, max_tokens=max_tokens)


def openai_chat_completions(
    requests_module: Any,
    config: LLMConfig,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> str:
    """调用 OpenAI Chat Completions 兼容接口。"""
    url = build_chat_url(config.base_url)
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    try:
        response = requests_module.post(
            url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=config.timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise LLMClientError(f"LLM 接口请求失败：{exc}") from exc

    content = extract_content(data)
    if not content:
        raise LLMClientError("LLM 接口未返回有效内容")

    return content


def anthropic_messages_chat(
    requests_module: Any,
    config: LLMConfig,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> str:
    """调用 Anthropic Messages 兼容接口。"""
    system_prompt, anthropic_messages = normalize_anthropic_messages(messages)
    url = build_anthropic_messages_url(config.base_url)
    payload: dict[str, Any] = {
        "model": config.model,
        "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
        "temperature": config.temperature,
        "messages": anthropic_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    try:
        response = requests_module.post(
            url,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=config.timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise LLMClientError(f"LLM 接口请求失败：{exc}") from exc

    content = extract_anthropic_content(data)
    if not content:
        raise LLMClientError("LLM 接口未返回有效内容")
    return content


def chat_with_system(
    system_prompt: str,
    user_message: str,
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """单轮对话：system + user。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat(messages, temperature=temperature, model=model, max_tokens=max_tokens)


def chat_with_history(
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
    temperature: float | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """多轮对话：system + history + user。"""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return chat(messages, temperature=temperature, model=model, max_tokens=max_tokens)


def build_chat_url(base_url: str) -> str:
    """构建 Chat Completions URL。"""
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return f"{cleaned}/chat/completions"


def build_anthropic_messages_url(base_url: str) -> str:
    """构建 Anthropic Messages URL，兼容 https://domain、/v1 和 /v1/messages。"""
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/messages"):
        return cleaned
    if cleaned.endswith("/v1"):
        return f"{cleaned}/messages"
    return f"{cleaned}/v1/messages"


def extract_content(response_data: dict[str, Any]) -> str:
    """从 Chat Completions 响应中提取内容。"""
    choices = response_data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        return ""

    message = first.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()

    return str(first.get("text") or "").strip()


def extract_anthropic_content(response_data: dict[str, Any]) -> str:
    """从 Anthropic Messages 响应中提取文本。"""
    content = response_data.get("content")
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" or "text" in item:
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def normalize_anthropic_messages(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    """把 OpenAI 风格消息转换为 Anthropic Messages 风格。"""
    system_parts = []
    result: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role") or "user"
        content = str(message.get("content") or "")
        if not content.strip():
            continue
        if role == "system":
            system_parts.append(content)
            continue
        result.append({"role": "assistant" if role == "assistant" else "user", "content": content})
    if not result:
        result.append({"role": "user", "content": "请回复 OK"})
    return "\n\n".join(system_parts).strip(), result


def normalize_provider(value: str) -> str:
    provider = (value or DEFAULT_PROVIDER).strip().lower()
    if provider in {"anthropic", "claude", "messages"}:
        return "anthropic"
    return "openai"


def resolve_api_key(provider: str) -> str:
    if provider == "anthropic":
        return (
            get_env("ANTHROPIC_API_KEY")
            or get_env("LLM_API_KEY")
            or get_env("OPENAI_API_KEY")
            or get_env("DEEPSEEK_API_KEY")
        )
    return (
        get_env("LLM_API_KEY")
        or get_env("OPENAI_API_KEY")
        or get_env("DEEPSEEK_API_KEY")
        or get_env("ANTHROPIC_API_KEY")
    )


def parse_int_env(name: str, default: int) -> int:
    """解析整数环境变量。"""
    try:
        value = int(get_env(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def parse_float_env(name: str, default: float) -> float:
    """解析浮点数环境变量。"""
    try:
        value = float(get_env(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value
