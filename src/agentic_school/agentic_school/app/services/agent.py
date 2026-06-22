from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.services.query_service import SchoolQueryService
from app.services.llm_client import DeepSeekClient


class ConversationStep(str, Enum):
    GREETING = "greeting"
    BASIC_INFO = "basic_info"
    TARGET_MAJOR = "target_major"
    TARGET_REGION = "target_region"
    SCHOOL_LEVEL = "school_level"
    SCORE_ESTIMATE = "score_estimate"
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    COMPLETED = "completed"


class UserProfile(BaseModel):
    undergraduate_school: Optional[str] = None
    undergraduate_major: Optional[str] = None
    target_major: Optional[str] = None
    target_major_category: Optional[str] = None
    target_province: Optional[str] = None
    target_city: Optional[str] = None
    school_type_preference: Optional[str] = None
    school_level_preference: Optional[str] = None
    estimated_score: Optional[int] = None
    degree_type: Optional[str] = None


class ConversationState(BaseModel):
    session_id: str
    step: ConversationStep = ConversationStep.GREETING
    user_profile: UserProfile = UserProfile()
    history: List[Dict[str, str]] = []
    recommendations: List[Dict[str, Any]] = []


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


class SchoolSelectionAgent:
    def __init__(self, db_session):
        self.query_service = SchoolQueryService(db_session)
        self.llm_client = DeepSeekClient()

    def _get_user_info_str(self, profile: UserProfile) -> str:
        parts = []
        if profile.undergraduate_school:
            parts.append(f"本科学校：{profile.undergraduate_school}")
        if profile.undergraduate_major:
            parts.append(f"本科专业：{profile.undergraduate_major}")
        if profile.target_major:
            parts.append(f"目标专业：{profile.target_major}")
        if profile.target_major_category:
            parts.append(f"专业门类：{profile.target_major_category}")
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
        return "\n".join(parts) if parts else "暂无"

    def _chat(self, state: ConversationState, context_hint: str = "") -> str:
        user_info = self._get_user_info_str(state.user_profile)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_info=user_info)
        
        history_for_llm = [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in state.history
        ]
        
        user_message = context_hint if context_hint else "请继续引导对话。"
        
        return self.llm_client.chat_with_history(
            system_prompt=system_prompt,
            history=history_for_llm,
            user_message=user_message,
        )

    def process_message(self, state: ConversationState, user_message: str) -> tuple[str, ConversationState]:
        state.history.append({"role": "user", "content": user_message})

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
            response, new_step = self._handle_analysis(state, user_message)
        elif state.step == ConversationStep.RECOMMENDATION:
            response, new_step = self._handle_recommendation(state, user_message)
        else:
            response = "对话已完成，如需重新开始请刷新页面。"
            new_step = state.step

        state.step = new_step
        state.history.append({"role": "assistant", "content": response})
        return response, state

    def _handle_greeting(self, state: ConversationState) -> tuple[str, ConversationStep]:
        response = self._chat(state, "用户开始了对话，请询问用户的本科学校和专业。")
        return response, ConversationStep.BASIC_INFO

    def _handle_basic_info(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取本科学校和本科专业信息，以JSON格式返回：{\"school\": \"...\", \"major\": \"...\"}",
        )

        if extracted_info.get("school"):
            state.user_profile.undergraduate_school = extracted_info["school"]
        if extracted_info.get("major"):
            state.user_profile.undergraduate_major = extracted_info["major"]

        categories = self.query_service.get_major_categories()
        categories_str = "、".join(categories[:15])

        response = self._chat(state, f"用户已提供本科信息。可选的专业门类有：{categories_str}。请询问用户想要报考的专业方向。")
        return response, ConversationStep.TARGET_MAJOR

    def _handle_target_major(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取目标专业和专业门类，以JSON格式返回：{\"major\": \"...\", \"category\": \"...\", \"degree_type\": \"academic/professional\"}",
        )

        if extracted_info.get("major"):
            state.user_profile.target_major = extracted_info["major"]
        if extracted_info.get("category"):
            state.user_profile.target_major_category = extracted_info["category"]
        if extracted_info.get("degree_type"):
            state.user_profile.degree_type = extracted_info["degree_type"]

        provinces = self.query_service.get_provinces()
        provinces_str = "、".join(provinces[:10])

        response = self._chat(state, f"用户已提供目标专业信息。可选的省份有：{provinces_str}。请询问用户的目标地区偏好。")
        return response, ConversationStep.TARGET_REGION

    def _handle_target_region(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取目标省份和城市，以JSON格式返回：{\"province\": \"...\", \"city\": \"...\"}",
        )

        if extracted_info.get("province"):
            state.user_profile.target_province = extracted_info["province"]
        if extracted_info.get("city"):
            state.user_profile.target_city = extracted_info["city"]

        response = self._chat(state, "用户已提供目标地区信息。请询问用户对学校层次的期望（如985、211、双一流、普通院校等）。")
        return response, ConversationStep.SCHOOL_LEVEL

    def _handle_school_level(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取学校层次偏好，以JSON格式返回：{\"level\": \"985/211/双一流/普通\", \"type\": \"综合/理工/师范/医药等\"}",
        )

        if extracted_info.get("level"):
            state.user_profile.school_level_preference = extracted_info["level"]
        if extracted_info.get("type"):
            state.user_profile.school_type_preference = extracted_info["type"]

        response = self._chat(state, "用户已提供学校层次偏好。请询问用户的预估考研分数（总分）。")
        return response, ConversationStep.SCORE_ESTIMATE

    def _handle_score_estimate(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        extracted_info = self._extract_info_with_llm(
            user_message,
            "请从用户回复中提取预估分数，以JSON格式返回：{\"score\": 数字}",
        )

        if extracted_info.get("score"):
            try:
                state.user_profile.estimated_score = int(extracted_info["score"])
            except (ValueError, TypeError):
                pass

        response = self._chat(state, "用户已提供预估分数，信息收集完成。请告知用户即将进行分析推荐，询问用户是否确认信息无误。")
        return response, ConversationStep.ANALYSIS

    def _handle_analysis(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        recommendations = self.query_service.recommend_schools(
            province=state.user_profile.target_province,
            school_type=state.user_profile.school_type_preference,
            school_level=state.user_profile.school_level_preference,
            major_category=state.user_profile.target_major_category,
        )

        state.recommendations = recommendations[:10]

        if not recommendations:
            response = self._chat(state, "根据用户条件未找到匹配的院校，请建议用户调整筛选条件。")
        else:
            schools_info = "\n".join([
                f"- {r['name']}（{r['province']}{r['city']}，{r['level'] or '普通院校'}）"
                for r in recommendations[:5]
            ])
            response = self._chat(state, f"根据用户条件找到以下院校：\n{schools_info}\n\n请为用户生成择校推荐报告。")

        return response, ConversationStep.RECOMMENDATION

    def _handle_recommendation(self, state: ConversationState, user_message: str) -> tuple[str, ConversationStep]:
        if "详细" in user_message or "更多信息" in user_message:
            detailed_info = self._generate_detailed_report(state)
            return detailed_info, ConversationStep.RECOMMENDATION

        response = self._chat(state, "用户已收到推荐，询问是否需要查看某个学校的详细信息，或者重新开始择校咨询。")
        return response, ConversationStep.RECOMMENDATION

    def _generate_detailed_report(self, state: ConversationState) -> str:
        if not state.recommendations:
            return "暂无推荐院校信息。"

        report_parts = []
        for school in state.recommendations[:3]:
            info = self.query_service.get_comprehensive_info(school["id"])
            if info:
                report_parts.append(f"\n【{school['name']}】")
                if info.get("subject_rates"):
                    rates = [f"{r['subject']}({r['level']})" for r in info["subject_rates"][:5]]
                    report_parts.append(f"学科评估：{', '.join(rates)}")
                if info.get("score_lines"):
                    lines = info["score_lines"][:3]
                    for line in lines:
                        report_parts.append(f"{line['year']}年分数线：{line['total_score']}分")

        return "\n".join(report_parts)

    def _extract_info_with_llm(self, user_message: str, extraction_prompt: str) -> dict:
        try:
            response = self.llm_client.chat_with_system(
                "你是一个信息提取助手，请严格按照要求的格式提取信息。",
                f"用户消息：{user_message}\n\n{extraction_prompt}",
            )

            import json
            import re

            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return {}
