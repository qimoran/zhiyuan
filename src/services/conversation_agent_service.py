"""对话式考研择校推荐 Agent。

基于 agentic_school 的对话引导逻辑，通过多轮对话收集用户信息并提供推荐。
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from src.common.database import mysql_connection
from src.common.exceptions import ValidationError
from src.common.logger import get_logger
from src.common.llm_client import chat_with_history, chat_with_system, LLMClientError
from src.services.metadata_service import list_major_categories, search_major_categories
from src.services.query_service import list_universities, list_majors
from src.services.recommendation_service import recommend

logger = get_logger(__name__)


class ConversationStep(str, Enum):
    """对话步骤枚举。"""

    GREETING = "greeting"
    BASIC_INFO = "basic_info"
    TARGET_MAJOR = "target_major"
    TARGET_REGION = "target_region"
    SCHOOL_LEVEL = "school_level"
    SCORE_ESTIMATE = "score_estimate"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    COMPLETED = "completed"


class UserProfile:
    """用户档案。"""

    def __init__(self):
        self.undergraduate_school: str | None = None
        self.undergraduate_major: str | None = None
        self.target_major: str | None = None
        self.major_category: str | None = None
        self.target_province: str | None = None
        self.target_city: str | None = None
        self.school_level_preference: str | None = None
        self.school_type_preference: str | None = None
        self.estimated_score: int | None = None
        self.degree_type: str | None = None
        self.study_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "undergraduate_school": self.undergraduate_school,
            "undergraduate_major": self.undergraduate_major,
            "target_major": self.target_major,
            "major_category": self.major_category,
            "target_province": self.target_province,
            "target_city": self.target_city,
            "school_level_preference": self.school_level_preference,
            "school_type_preference": self.school_type_preference,
            "estimated_score": self.estimated_score,
            "degree_type": self.degree_type,
            "study_mode": self.study_mode,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """从字典加载。"""
        self.undergraduate_school = data.get("undergraduate_school")
        self.undergraduate_major = data.get("undergraduate_major")
        self.target_major = data.get("target_major")
        self.major_category = data.get("major_category")
        self.target_province = data.get("target_province")
        self.target_city = data.get("target_city")
        self.school_level_preference = data.get("school_level_preference")
        self.school_type_preference = data.get("school_type_preference")
        self.estimated_score = data.get("estimated_score")
        self.degree_type = data.get("degree_type")
        self.study_mode = data.get("study_mode")


class ConversationState:
    """对话状态。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.step = ConversationStep.GREETING
        self.user_profile = UserProfile()
        self.history: list[dict[str, str]] = []
        self.recommendations: list[dict[str, Any]] = []
        self.recommendation_request: dict[str, Any] | None = None
        self.recommendation_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典用于序列化。"""
        return {
            "session_id": self.session_id,
            "step": self.step.value,
            "user_profile": self.user_profile.to_dict(),
            "history": self.history,
            "recommendations": self.recommendations,
            "recommendation_request": self.recommendation_request,
            "recommendation_result": self.recommendation_result,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """从字典加载。"""
        self.session_id = data.get("session_id", "")
        self.step = ConversationStep(data.get("step", "greeting"))
        self.user_profile.from_dict(data.get("user_profile", {}))
        self.history = data.get("history", [])
        self.recommendations = data.get("recommendations", [])
        self.recommendation_request = data.get("recommendation_request")
        self.recommendation_result = data.get("recommendation_result")


SYSTEM_PROMPT_TEMPLATE = """你是一个专业的考研择校顾问助手。你的任务是帮助考生根据自身情况选择合适的研究生院校和专业。

当前已收集的用户信息：
{user_info}

你需要按照以下步骤引导对话：
1. 了解考生的基本情况（本科学校、专业）
2. 了解考生的目标专业方向
3. 了解考生的目标地区偏好
4. 了解考生对学校层次的期望（985/211/双一流等）
5. 了解考生的预估分数
6. 根据以上信息进行分析和推荐

对话要求：
- 每次只问一个问题，等待用户回答
- 问题要简洁明了
- 根据用户的回答灵活调整对话流程
- 如果用户信息不完整，可以适当追问
- 最终给出具体的择校建议
- 记住用户之前告诉你的信息，不要重复询问已收集的信息

回复格式要求：
- 使用自然语言与用户交流
- 不要使用markdown格式
- 回复要简洁，控制在200字以内"""


class ConversationAgent:
    """对话式推荐 Agent。"""

    def __init__(self):
        pass

    def process_message(
        self, state: ConversationState, user_message: str, user_id: int | None = None
    ) -> tuple[str, ConversationState]:
        """处理用户消息，返回回复和更新后的状态。"""
        state.history.append({"role": "user", "content": user_message})

        try:
            if state.step == ConversationStep.GREETING:
                response, new_step = self._handle_greeting(state)
            elif state.step == ConversationStep.BASIC_INFO:
                response, new_step = self._handle_basic_info(state, user_message)
            elif state.step == ConversationStep.TARGET_MAJOR:
                response, new_step = self._handle_target_major(state, user_message)
            elif state.step == ConversationStep.TARGET_REGION:
                response, new_step = self._handle_target_region(state, user_message)
            elif state.step == ConversationStep.SCHOOL_LEVEL:
                response, new_step = self._handle_school_level(state, user_message)
            elif state.step == ConversationStep.SCORE_ESTIMATE:
                response, new_step = self._handle_score_estimate(state, user_message)
            elif state.step == ConversationStep.ANALYSIS:
                response, new_step = self._handle_analysis(state, user_message, user_id)
            elif state.step == ConversationStep.RECOMMENDATION:
                response, new_step = self._handle_recommendation(state, user_message)
            else:
                response = "对话已完成，如需重新开始请刷新页面。"
                new_step = state.step
        except Exception as exc:
            logger.error("对话式推荐处理失败：%s", exc)
            response = "抱歉，对话推荐暂时遇到问题。你也可以直接填写下方表单生成推荐结果。"
            new_step = state.step

        state.step = new_step
        state.history.append({"role": "assistant", "content": response})
        return response, state

    def _get_user_info_str(self, profile: UserProfile) -> str:
        """格式化用户信息字符串。"""
        parts = []
        if profile.undergraduate_school:
            parts.append(f"本科学校：{profile.undergraduate_school}")
        if profile.undergraduate_major:
            parts.append(f"本科专业：{profile.undergraduate_major}")
        if profile.target_major:
            parts.append(f"目标专业：{profile.target_major}")
        if profile.major_category:
            parts.append(f"专业门类：{profile.major_category}")
        if profile.target_province:
            parts.append(f"目标省份：{profile.target_province}")
        if profile.target_city:
            parts.append(f"目标城市：{profile.target_city}")
        if profile.school_level_preference:
            parts.append(f"学校层次偏好：{profile.school_level_preference}")
        if profile.school_type_preference:
            parts.append(f"学校类型偏好：{profile.school_type_preference}")
        if profile.estimated_score:
            parts.append(f"预估分数：{profile.estimated_score}")
        if profile.degree_type:
            degree_label = {"academic": "学术学位", "professional": "专业学位"}.get(
                profile.degree_type, profile.degree_type
            )
            parts.append(f"学位类型：{degree_label}")
        if profile.study_mode:
            mode_label = {"full_time": "全日制", "part_time": "非全日制"}.get(
                profile.study_mode, profile.study_mode
            )
            parts.append(f"学习方式：{mode_label}")
        return "\n".join(parts) if parts else "暂无"

    def _chat(self, state: ConversationState, context_hint: str = "") -> str:
        """调用 LLM 生成对话回复。"""
        user_info = self._get_user_info_str(state.user_profile)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_info=user_info)

        history_for_llm = [
            {"role": msg["role"], "content": msg["content"]} for msg in state.history
        ]

        user_message = context_hint if context_hint else "请继续引导对话。"

        try:
            return chat_with_history(
                system_prompt=system_prompt,
                history=history_for_llm,
                user_message=user_message,
                temperature=0.7,
            )
        except LLMClientError as exc:
            logger.warning("LLM 对话不可用，使用规则模板回复：%s", exc)
            return self._fallback_reply(state, context_hint)

    def _handle_greeting(
        self, state: ConversationState
    ) -> tuple[str, ConversationStep]:
        """处理初次打招呼。"""
        response = self._chat(state, "用户开始了对话，请询问用户的本科学校和专业。")
        return response, ConversationStep.BASIC_INFO

    def _handle_basic_info(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理基本信息收集。"""
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取本科学校和本科专业信息，以JSON格式返回：{\"school\": \"...\", \"major\": \"...\"}",
        )

        if extracted_info.get("school"):
            state.user_profile.undergraduate_school = extracted_info["school"]
        if extracted_info.get("major"):
            state.user_profile.undergraduate_major = extracted_info["major"]

        # 获取专业门类列表
        categories_data = list_major_categories({})
        categories = categories_data.get("combined", [])[:15]
        categories_str = "、".join(categories)

        response = self._chat(
            state,
            f"用户已提供本科信息。可选的专业门类有：{categories_str}。请询问用户想要报考的专业方向。",
        )
        return response, ConversationStep.TARGET_MAJOR

    def _handle_target_major(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理目标专业收集。"""
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取目标专业和专业门类，以JSON格式返回：{\"major\": \"...\", \"category\": \"...\", \"degree_type\": \"academic/professional\"}",
        )

        if extracted_info.get("major"):
            state.user_profile.target_major = extracted_info["major"]
        if extracted_info.get("category"):
            state.user_profile.major_category = extracted_info["category"]
        if extracted_info.get("degree_type"):
            state.user_profile.degree_type = extracted_info["degree_type"]
        if extracted_info.get("study_mode"):
            state.user_profile.study_mode = extracted_info["study_mode"]

        if not state.user_profile.target_major:
            state.user_profile.target_major = clean_message_as_value(user_message)

        # 获取省份列表
        provinces = ["重庆", "四川", "北京", "上海", "广东", "江苏", "浙江", "湖北", "陕西", "天津"]
        provinces_str = "、".join(provinces)

        response = self._chat(
            state,
            f"用户已提供目标专业信息。可选的省份有：{provinces_str}。请询问用户的目标地区偏好。",
        )
        return response, ConversationStep.TARGET_REGION

    def _handle_target_region(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理目标地区收集。"""
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取目标省份和城市，以JSON格式返回：{\"province\": \"...\", \"city\": \"...\"}",
        )

        if extracted_info.get("province"):
            state.user_profile.target_province = extracted_info["province"]
        if extracted_info.get("city"):
            state.user_profile.target_city = extracted_info["city"]
        if not state.user_profile.target_province and "不限" not in user_message:
            state.user_profile.target_province = "重庆"

        response = self._chat(
            state,
            "用户已提供目标地区信息。请询问用户对学校层次的期望（如985、211、双一流、普通院校等）。",
        )
        return response, ConversationStep.SCHOOL_LEVEL

    def _handle_school_level(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理学校层次收集。"""
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取学校层次偏好，以JSON格式返回：{\"level\": \"985/211/双一流/普通\", \"type\": \"综合/理工/师范/医药等\"}",
        )

        if extracted_info.get("level"):
            state.user_profile.school_level_preference = extracted_info["level"]
        if extracted_info.get("type"):
            state.user_profile.school_type_preference = extracted_info["type"]

        response = self._chat(
            state, "用户已提供学校层次偏好。请询问用户的预估考研分数（总分）。"
        )
        return response, ConversationStep.SCORE_ESTIMATE

    def _handle_score_estimate(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理分数估算收集。"""
        extracted_info = self._extract_info_with_llm(
            user_message, "请从用户回复中提取预估分数，以JSON格式返回：{\"score\": 数字}"
        )

        if extracted_info.get("score"):
            try:
                state.user_profile.estimated_score = int(extracted_info["score"])
            except (ValueError, TypeError):
                pass
        if not state.user_profile.estimated_score:
            return "请告诉我你的预估考研总分，例如 330、350。", ConversationStep.SCORE_ESTIMATE

        response = self._chat(
            state,
            "用户已提供预估分数，信息收集完成。请告知用户即将进行分析推荐，询问用户是否确认信息无误。",
        )
        return response, ConversationStep.ANALYSIS

    def _handle_analysis(
        self, state: ConversationState, user_message: str, user_id: int | None = None
    ) -> tuple[str, ConversationStep]:
        """处理分析阶段，调用推荐接口。"""
        profile = state.user_profile
        if not profile.target_major and not profile.major_category:
            return "还缺少目标专业，请告诉我你想报考的专业方向。", ConversationStep.TARGET_MAJOR
        if not profile.estimated_score:
            return "还缺少预估总分，请告诉我你的考研预估总分。", ConversationStep.SCORE_ESTIMATE

        # 构建推荐请求
        request_payload = {
            "target_year": 2026,
            "province": profile.target_province or "重庆",
            "major_category": profile.major_category or "",
            "major_name": profile.target_major or "",
            "degree_type": profile.degree_type or "professional",
            "study_mode": profile.study_mode or "full_time",
            "preferred_school_levels": [profile.school_level_preference]
            if profile.school_level_preference
            else [],
            "bucket_limit": 3,
            "total_score": profile.estimated_score or 300,
        }
        state.recommendation_request = request_payload

        try:
            # 调用推荐服务
            result = recommend(request_payload, user_id=user_id)
            state.recommendation_result = result
            recommendations = result.get("recommendations", {})

            # 保存推荐结果
            state.recommendations = []
            for rank_type in ["rush", "stable", "safe"]:
                items = recommendations.get(rank_type, [])
                state.recommendations.extend(items[:3])

            if not state.recommendations:
                response = self._chat(
                    state, "根据用户条件未找到匹配的院校，请建议用户调整筛选条件。"
                )
            else:
                schools_info = "\n".join(
                    [
                        f"- {r['university_name']}（{r.get('school_level') or '普通院校'}，"
                        f"复试线：{r.get('score_line') or '暂无'}分）"
                        for r in state.recommendations[:5]
                    ]
                )
                response = self._chat(
                    state,
                    f"根据用户条件找到以下院校：\n{schools_info}\n\n请为用户生成择校推荐报告。",
                )
        except Exception as exc:
            logger.error("推荐接口调用失败：%s", exc)
            response = "抱歉，推荐系统遇到问题。请稍后重试或调整筛选条件。"

        return response, ConversationStep.RECOMMENDATION

    def _handle_recommendation(
        self, state: ConversationState, user_message: str
    ) -> tuple[str, ConversationStep]:
        """处理推荐结果阶段。"""
        if "详细" in user_message or "更多信息" in user_message:
            detailed_info = self._generate_detailed_report(state)
            return detailed_info, ConversationStep.RECOMMENDATION

        response = self._chat(
            state,
            "用户已收到推荐，询问是否需要查看某个学校的详细信息，或者重新开始择校咨询。",
        )
        return response, ConversationStep.RECOMMENDATION

    def _generate_detailed_report(self, state: ConversationState) -> str:
        """生成详细报告。"""
        if not state.recommendations:
            return "暂无推荐院校信息。"

        report_parts = []
        for school in state.recommendations[:3]:
            report_parts.append(f"\n【{school.get('university_name', '未知院校')}】")
            report_parts.append(
                f"学校层次：{school.get('school_level') or '普通院校'}"
            )
            report_parts.append(
                f"专业：{school.get('major_name') or '未知专业'}"
            )
            if school.get("score_line"):
                report_parts.append(f"参考复试线：{school['score_line']}分")
            if school.get("reason"):
                report_parts.append(f"推荐理由：{school['reason']}")

        return "\n".join(report_parts)

    def _extract_info_with_llm(
        self, user_message: str, extraction_prompt: str
    ) -> dict[str, Any]:
        """使用 LLM 提取结构化信息。"""
        try:
            response = chat_with_system(
                "你是一个信息提取助手，请严格按照要求的格式提取信息。",
                f"用户消息：{user_message}\n\n{extraction_prompt}",
                temperature=0.3,
            )

            json_match = re.search(r"\{[^}]+\}", response)
            if json_match:
                return json.loads(json_match.group())
        except Exception as exc:
            logger.warning("信息提取失败：%s", exc)

        return self._extract_info_by_rules(user_message, extraction_prompt)

    def _extract_info_by_rules(self, user_message: str, extraction_prompt: str) -> dict[str, Any]:
        """LLM 不可用时的简单规则抽取，保证演示流程可以继续。"""
        text = user_message.strip()
        result: dict[str, Any] = {}
        if "本科学校" in extraction_prompt:
            school_match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+(?:大学|学院|学校))", text)
            if school_match:
                result["school"] = school_match.group(1)
            major_match = re.search(r"(?:专业是|本科专业是|学的是|读的是|专业[:：])([^，。,\s]+)", text)
            if major_match:
                result["major"] = major_match.group(1)
            return result

        if "目标专业" in extraction_prompt:
            result["major"] = extract_target_major(text)
            result["category"] = infer_major_category(result["major"])
            result["degree_type"] = infer_degree_type(text)
            result["study_mode"] = infer_study_mode(text)
            return {key: value for key, value in result.items() if value}

        if "目标省份" in extraction_prompt:
            province = extract_province(text)
            if province:
                result["province"] = province
            city_match = re.search(r"([\u4e00-\u9fa5]{2,6}市)", text)
            if city_match:
                result["city"] = city_match.group(1)
            return result

        if "学校层次" in extraction_prompt:
            result["level"] = extract_school_level(text)
            result["type"] = extract_school_type(text)
            return {key: value for key, value in result.items() if value}

        if "预估分数" in extraction_prompt:
            score_match = re.search(r"(500|[1-4]\d{2}|[1-9]\d?)", text)
            if score_match:
                result["score"] = int(score_match.group(1))
            return result

        return result

    def _fallback_reply(self, state: ConversationState, context_hint: str) -> str:
        """LLM 不可用时的对话模板。"""
        if "本科学校和专业" in context_hint:
            return "我会一步步收集择校信息。请先告诉我你的本科学校和本科专业。"
        if "想要报考的专业方向" in context_hint:
            return "请告诉我你的目标专业方向，例如计算机技术、人工智能、软件工程等。"
        if "目标地区" in context_hint:
            return "目前系统重点覆盖重庆高校。你可以填写重庆，也可以说明是否有其他地区偏好。"
        if "学校层次" in context_hint:
            return "请告诉我你的学校层次偏好，例如985、211、双一流或普通院校。"
        if "预估考研分数" in context_hint:
            return "请告诉我你的预估考研总分，例如330分。"
        if "即将进行分析推荐" in context_hint:
            return "信息已经基本收集完成。如果确认无误，请回复“确认”，我会按当前条件生成推荐。"
        if "找到以下院校" in context_hint:
            return (
                "我已经根据当前条件生成了推荐结果。你可以在下方查看冲刺、稳妥、保底三档院校，"
                "也可以继续问我某所学校的详细情况。"
            )
        if "未找到匹配" in context_hint:
            return "按当前条件没有找到合适候选，建议放宽专业名称、学校层次或分数条件后再试。"
        return "请继续补充你的择校信息，我会根据本地数据库和资料证据生成推荐。"


def clean_message_as_value(message: str) -> str:
    text = re.sub(r"[，。,.！!？?]", " ", message).strip()
    text = re.sub(r"^(我想|想|准备|打算|报考|考|目标是|专业是)", "", text).strip()
    return text[:40]


def extract_target_major(message: str) -> str:
    text = clean_message_as_value(message)
    known = ["计算机技术", "人工智能", "软件工程", "计算机科学与技术", "电子信息", "教育学", "心理学"]
    for item in known:
        if item in message:
            return item
    if "计算机" in message:
        return "计算机"
    return text


def infer_major_category(major: str | None) -> str | None:
    if not major:
        return None
    if any(keyword in major for keyword in ["计算机", "软件", "人工智能", "电子信息"]):
        return "工学"
    if "教育" in major:
        return "教育学"
    if "心理" in major:
        return "教育学"
    return None


def infer_degree_type(message: str) -> str | None:
    if any(keyword in message for keyword in ["学硕", "学术"]):
        return "academic"
    if any(keyword in message for keyword in ["专硕", "专业学位"]):
        return "professional"
    return None


def infer_study_mode(message: str) -> str | None:
    if "非全" in message or "非全日制" in message:
        return "part_time"
    if "全日制" in message:
        return "full_time"
    return None


def extract_province(message: str) -> str | None:
    provinces = ["重庆", "四川", "北京", "上海", "广东", "江苏", "浙江", "湖北", "陕西", "天津"]
    for province in provinces:
        if province in message:
            return province
    return None


def extract_school_level(message: str) -> str | None:
    if "985" in message:
        return "985"
    if "211" in message:
        return "211"
    if "双一流" in message:
        return "双一流"
    if "普通" in message:
        return "普通院校"
    return None


def extract_school_type(message: str) -> str | None:
    for school_type in ["综合", "理工", "师范", "医药", "财经", "政法"]:
        if school_type in message:
            return school_type
    return None
