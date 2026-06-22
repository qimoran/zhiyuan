"""AI 助手服务 - 回答网站相关问题并提供页面跳转链接。"""

from __future__ import annotations

import json
from typing import Any

from src.common.exceptions import ValidationError
from src.common.logger import get_logger
from src.common.trace import get_trace_id
from src.common.llm_client import chat_with_history, LLMClientError

logger = get_logger(__name__)

# 网站功能和页面映射
SITE_PAGES = {
    "首页": {"url": "/", "description": "首页，可以开始考研择校推荐"},
    "学校列表": {"url": "/universities", "description": "查看重庆所有招生院校列表，支持筛选和搜索"},
    "专业列表": {"url": "/majors", "description": "查看所有招生专业列表，支持按专业类别筛选"},
    "数据图表": {"url": "/charts", "description": "可视化图表，包括复试分数线趋势、招生计划变化、学科评估等"},
    "推荐结果": {"url": "/result", "description": "查看推荐结果页面，展示冲刺、稳妥、保底三档推荐"},
    "推荐报告": {"url": "/report", "description": "生成 AI 择校建议报告，提供详细的择校分析"},
    "个人中心": {"url": "/profile", "description": "个人中心，查看推荐历史和账号设置"},
    "开始推荐": {"url": "/recommend", "description": "开始考研择校推荐，填写分数和目标信息"},
    "登录": {"url": "/login", "description": "用户登录"},
    "注册": {"url": "/register", "description": "用户注册"},
}

SYSTEM_PROMPT = f"""你是"重庆高校考研择校推荐系统"的 AI 助手。

**你的职责**：
- 回答用户关于本网站功能、使用方法、考研择校相关的问题
- 提供准确的页面跳转链接
- 用 Markdown 格式输出，链接格式为 [页面名称](URL)

**网站功能**：
{json.dumps(SITE_PAGES, ensure_ascii=False, indent=2)}

**本系统特点**：
- 数据来源：掌上考研 V2 公开接口 + 本地 MySQL 清洗入库数据
- 推荐档位：冲刺档、稳妥档、保底档三档推荐
- 推荐依据：复试分数线、招生计划、学校层次、本地 RAG 知识库 + 联网搜索
- AI 报告：基于推荐结果生成详细择校建议报告

**回答规则**：
1. 只回答本网站功能和考研择校相关问题
2. 不编造不存在的功能或页面
3. 提供页面链接时使用 Markdown 格式：[页面名称](URL)
4. 不提供具体学校、专业、分数线数据（引导用户到对应页面查询）
5. 不做录取承诺，强调"仅供参考"
6. 输出简洁、友好，不超过 300 字

**示例**：
- 用户问"如何查看学校列表" → 回答并提供 [学校列表](/universities) 链接
- 用户问"怎么开始推荐" → 回答并提供 [开始推荐](/recommend) 链接
- 用户问"能看历年分数线吗" → 回答并提供 [数据图表](/charts) 链接
"""


class ChatServiceUnavailable(Exception):
    """AI 助手服务不可用。"""


def chat(payload: dict[str, Any]) -> dict[str, Any]:
    """处理用户聊天请求。"""
    user_message = str(payload.get("message") or "").strip()
    if not user_message:
        raise ValidationError("message 不能为空")

    conversation_history = payload.get("history") or []
    if not isinstance(conversation_history, list):
        conversation_history = []

    try:
        response_content = call_llm_chat(user_message, conversation_history)
        return {
            "trace_id": get_trace_id(),
            "message": response_content,
            "status": "success",
        }
    except ChatServiceUnavailable as exc:
        logger.warning("AI 助手服务失败：%s", exc)
        return {
            "trace_id": get_trace_id(),
            "message": build_fallback_response(user_message),
            "status": "fallback",
            "error": str(exc),
        }


def call_llm_chat(user_message: str, conversation_history: list[dict[str, str]]) -> str:
    """调用 LLM 生成聊天回复。"""
    try:
        history = conversation_history[-10:]  # 最多保留最近 10 轮对话
        response_content = chat_with_history(
            system_prompt=SYSTEM_PROMPT,
            history=history,
            user_message=user_message,
            temperature=0.7,
            max_tokens=500,
        )
        return response_content
    except LLMClientError as exc:
        raise ChatServiceUnavailable(str(exc)) from exc


def build_fallback_response(user_message: str) -> str:
    """LLM 不可用时的降级回复。"""
    message_lower = user_message.lower()

    # 关键词匹配
    if any(keyword in message_lower for keyword in ["学校", "院校", "大学"]):
        return "您可以前往 [学校列表](/universities) 查看重庆所有招生院校。"

    if any(keyword in message_lower for keyword in ["专业", "学科"]):
        return "您可以前往 [专业列表](/majors) 查看所有招生专业。"

    if any(keyword in message_lower for keyword in ["推荐", "择校", "开始"]):
        return "您可以前往 [开始推荐](/recommend) 填写分数信息，获取考研择校推荐。"

    if any(keyword in message_lower for keyword in ["分数线", "复试线", "图表", "趋势"]):
        return "您可以前往 [数据图表](/charts) 查看历年分数线趋势和招生计划变化。"

    if any(keyword in message_lower for keyword in ["报告", "建议", "分析"]):
        return "您可以前往 [推荐报告](/report) 生成 AI 择校建议报告。"

    if any(keyword in message_lower for keyword in ["历史", "记录", "个人", "中心"]):
        return "您可以前往 [个人中心](/profile) 查看推荐历史和账号设置。"

    # 默认回复
    return """您好！我是考研择校推荐系统的 AI 助手。

您可以：
- 前往 [开始推荐](/recommend) 获取择校推荐
- 查看 [学校列表](/universities) 和 [专业列表](/majors)
- 查看 [数据图表](/charts) 了解历年分数线趋势
- 生成 [推荐报告](/report) 获取详细择校建议

有其他问题请随时问我！"""
