"""S08 基础 API 路由。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from src.common.database import ping_database
from src.common.exceptions import ValidationError
from src.common.logger import get_logger
from src.common.response import success_response
from src.services.auth_service import (
    authenticate_user,
    get_user_by_id,
    get_user_recommendation_detail,
    list_user_recommendation_history,
    public_user,
    register_user,
    update_user_profile,
)
from src.services.query_service import (
    get_health_detail,
    list_majors,
    list_sources,
    list_universities,
)
from src.services.recommendation_service import recommend
from src.services.report_service import generate_report
from src.services.score_service import evaluate_score
from src.services.chart_service import (
    get_admission_score_trend,
    get_line_trend,
    get_major_heat,
    get_plan_trend,
    get_university_type,
)
from src.services.metadata_service import (
    list_major_categories,
    list_plan_major_options,
    list_score_line_major_options,
    list_degree_types,
    list_study_modes,
    list_school_levels,
    search_major_categories,
    search_major_names,
)
from src.services.chat_service import chat
from src.services.conversation_agent_service import ConversationAgent, ConversationState
from src.services.school_analysis_service import analyze_school

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = get_logger("app")

# 内存会话存储（生产环境应使用 Redis）
conversation_sessions: dict[str, ConversationState] = {}


def current_user_id() -> int | None:
    user_id = session.get("user_id")
    try:
        return int(user_id) if user_id else None
    except (TypeError, ValueError):
        session.pop("user_id", None)
        return None


def require_user_id() -> int:
    user_id = current_user_id()
    if not user_id:
        raise ValidationError("请先登录")
    return user_id


@api_bp.get("/health")
def health_check():
    """系统健康检查接口。

    返回系统运行状态和数据库连通性，用于监控和运维。

    Returns:
        {
          "status": "ok",
          "database": "ok" | "unavailable",
          "detail": {
            "universities": int,        # 招生单位数量
            "majors": int,              # 专业数量
            "enrollment_plans": int,    # 招生计划数量
            "score_lines": int,         # 分数线数量
            "source_documents": int     # 来源资料数量
          }
        }

    Example:
        GET /api/health

        Response:
        {
          "code": 0,
          "message": "success",
          "trace_id": "202606161626...",
          "data": {
            "status": "ok",
            "database": "ok",
            "detail": {
              "universities": 21,
              "majors": 5652,
              "enrollment_plans": 10035,
              "score_lines": 6610,
              "source_documents": 21
            }
          }
        }
    """
    database_ok = False
    detail = {}
    try:
        database_ok = ping_database()
        detail = get_health_detail() if database_ok else {}
    except Exception as exc:
        logger.warning("数据库健康检查失败：%s", exc)

    return jsonify(
        success_response(
            {
                "status": "ok",
                "database": "ok" if database_ok else "unavailable",
                "detail": detail,
            }
        )
    )


@api_bp.post("/auth/register")
def auth_register():
    """注册前台用户并登录。"""
    payload = request.get_json(silent=True) or {}
    user = register_user(payload)
    session["user_id"] = user["id"]
    return jsonify(success_response({"authenticated": True, "user": user}))


@api_bp.post("/auth/login")
def auth_login():
    """用户登录。"""
    payload = request.get_json(silent=True) or {}
    user = authenticate_user(payload)
    session["user_id"] = user["id"]
    return jsonify(success_response({"authenticated": True, "user": user}))


@api_bp.post("/auth/logout")
def auth_logout():
    """退出登录。"""
    session.pop("user_id", None)
    return jsonify(success_response({"authenticated": False, "user": None}))


@api_bp.get("/auth/me")
def auth_me():
    """获取当前登录用户。"""
    user = public_user(get_user_by_id(current_user_id()))
    if not user:
        session.pop("user_id", None)
    return jsonify(success_response({"authenticated": bool(user), "user": user}))


@api_bp.put("/auth/profile")
def auth_profile_update():
    """更新当前用户昵称或密码。"""
    payload = request.get_json(silent=True) or {}
    user = update_user_profile(require_user_id(), payload)
    return jsonify(success_response({"authenticated": True, "user": user}))


@api_bp.get("/me/recommendations")
def my_recommendations():
    """当前用户的推荐历史摘要。"""
    data = list_user_recommendation_history(require_user_id(), request.args.get("limit") or 50)
    return jsonify(success_response(data))


@api_bp.get("/me/recommendations/<int:log_id>")
def my_recommendation_detail(log_id: int):
    """当前用户的单条推荐历史详情。"""
    data = get_user_recommendation_detail(require_user_id(), log_id)
    return jsonify(success_response(data))


@api_bp.get("/university/list")
def university_list():
    """招生单位列表。

    查询重庆地区研招单位候选库，支持分页、筛选和关键词搜索。

    Query Parameters:
        limit (int): 返回条数，默认 50，最大 200
        offset (int): 跳过条数，默认 0
        coverage_priority (str): 优先级筛选（P0/P1/P2/P3）
            - P0: 985/211/双一流重点高校
            - P1: 211/双一流高校
            - P2: 普通院校
            - P3: 科研机构
        school_type (str): 学校类型（综合类/理工类/医药类/师范类/艺术类等）
        school_org_type (str): 机构类型（高等院校/科研院所）
        official_verified_status (str): 官网核验状态（pending/verified/mismatch）
        keyword (str): 关键词搜索（学校名称模糊匹配）

    Returns:
        {
          "items": [
            {
              "id": int,
              "candidate_school_id": int,
              "university_name": str,
              "province": str,
              "city": str,
              "province_area": str,      # A区/B区
              "school_type": str,
              "school_org_type": str,
              "school_level": str,        # 985/211/双一流等
              "coverage_priority": str,
              "official_verified_status": str,
              "recruit_number_reference": int,
              "major_number_reference": int,
              "candidate_source_url": str,
              "remark": str
            }
          ],
          "total": int,
          "limit": int,
          "offset": int,
          "has_more": bool
        }

    Examples:
        # 查询所有学校（默认分页）
        GET /api/university/list

        # 查询 P0 优先级学校
        GET /api/university/list?coverage_priority=P0

        # 关键词搜索
        GET /api/university/list?keyword=重庆大学

        # 分页查询
        GET /api/university/list?limit=10&offset=0
    """
    data = list_universities(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/major/list")
def major_list():
    """专业列表。

    查询研究生招生专业目录，支持按学校、年份、专业门类、学位类型、学习方式等多维度筛选。

    Query Parameters:
        limit (int): 返回条数，默认 50，最大 200
        offset (int): 跳过条数，默认 0
        university_id (int): 学校 ID（数据库主键）
        school_id (int): 候选学校 ID（掌上考研 school_id）
        year (int): 招生年份（2024/2025/2026）
            - 注意：指定 year 会 JOIN enrollment_plans 表，只返回该年份有招生计划的专业
        major_category (str): 专业门类（哲学/经济学/法学/教育学/文学/历史学/理学/工学/农学/医学/军事学/管理学/艺术学/交叉学科）
        major_code (str): 专业代码（6 位，如 081200）
        degree_type (str): 学位类型
            - academic: 学术学位（学硕）
            - professional: 专业学位（专硕）
        study_mode (str): 学习方式
            - full_time: 全日制
            - part_time: 非全日制
        keyword (str): 关键词搜索（专业名称或研究方向模糊匹配）

    Returns:
        {
          "items": [
            {
              "id": int,
              "university_id": int,
              "candidate_school_id": int,
              "university_name": str,
              "department_id": int,
              "department_name": str,
              "major_code": str,
              "major_name": str,
              "major_category": str,
              "degree_type": str,
              "study_mode": str,
              "research_direction": str,
              "exam_subjects": str,
              "updated_at": str           # ISO 8601 格式
            }
          ],
          "total": int,
          "limit": int,
          "offset": int,
          "has_more": bool
        }

    Examples:
        # 查询重庆大学的所有专业
        GET /api/major/list?school_id=252

        # 查询 2026 年电子信息类全日制专硕
        GET /api/major/list?year=2026&major_category=电子信息&degree_type=professional&study_mode=full_time

        # 关键词搜索计算机相关专业
        GET /api/major/list?keyword=计算机

        # 分页查询
        GET /api/major/list?limit=20&offset=0
    """
    data = list_majors(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/source/list")
def source_list():
    """来源资料列表。

    查询数据来源资料索引，包括掌上考研候选数据、学校官网 PDF、Excel 等原始资料的登记记录。

    Query Parameters:
        limit (int): 返回条数，默认 50，最大 200
        offset (int): 跳过条数，默认 0
        university_id (int): 学校 ID（数据库主键）
        school_id (int): 候选学校 ID（掌上考研 school_id）
        year (int): 资料年份（2024/2025/2026）
        document_type (str): 资料类型
            - school_list: 学校候选库（掌上考研）
            - plan_list: 招生计划（掌上考研）
            - plan_detail: 专业详情（掌上考研）
            - score_line: 分数线（掌上考研）
            - level_rate: 学科评估（掌上考研）
            - official_plan: 招生专业目录（官网 PDF/Excel）
            - official_score: 复试线公告（官网 PDF/Excel）
            - official_admission: 拟录取名单（官网 PDF/Excel）
        process_status (str): 处理状态
            - pending: 待处理
            - loaded: 已入库
            - verified: 已核验
            - error: 处理失败

    Returns:
        {
          "items": [
            {
              "id": int,
              "university_id": int,
              "candidate_school_id": int,
              "university_name": str,
              "year": int,
              "document_type": str,
              "document_title": str,
              "source_url": str,
              "local_path": str,
              "published_date": str,      # ISO 8601 格式
              "collector": str,
              "collected_at": str,        # ISO 8601 格式
              "process_status": str,
              "official_verified": bool,
              "remark": str
            }
          ],
          "total": int,
          "limit": int,
          "offset": int,
          "has_more": bool
        }

    Examples:
        # 查询重庆大学的所有来源资料
        GET /api/source/list?school_id=252

        # 查询掌上考研候选库来源
        GET /api/source/list?document_type=school_list

        # 查询已入库的资料
        GET /api/source/list?process_status=loaded

        # 查询 2026 年官网招生目录
        GET /api/source/list?year=2026&document_type=official_plan
    """
    data = list_sources(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.post("/score/evaluate")
def score_evaluate():
    """分数线评估接口（S09）。

    根据用户初试成绩评估相对国家线、院校线、专业线的状况，判断总分和单科风险等级。

    Request Body (JSON):
        {
          "target_year": int,           # 目标年份（2024/2025/2026）
          "major_category": str,        # 专业门类（必填）
          "major_name": str,            # 专业名称（可选，用于精确匹配专业线）
          "university_id": int,         # 学校 ID（可选，用于查询院校线）
          "total_score": int,           # 总分（0-500）
          "politics_score": int,        # 政治/综合科目分数（0-150）
          "english_score": int,         # 英语分数（0-150）
          "subject_one_score": int,     # 业务课一分数（0-150）
          "subject_two_score": int      # 业务课二分数（0-150）
        }

    Returns:
        {
          "total_score_status": str,    # unsafe/warning/safe
          "single_subject_status": str, # unsafe/warning/safe
          "line_type": str,             # 使用的分数线类型（national/university/major）
          "line_detail": {
            "total_score_line": int,
            "politics_line": int,
            "english_line": int,
            "subject_one_line": int,
            "subject_two_line": int
          },
          "diff": {
            "total_diff": int,
            "politics_diff": int,
            "english_diff": int,
            "subject_one_diff": int,
            "subject_two_diff": int
          },
          "warnings": [str],            # 风险提示列表
          "suggestions": [str]          # 建议列表
        }

    Examples:
        # 评估电子信息专业成绩
        POST /api/score/evaluate
        Content-Type: application/json

        {
          "target_year": 2026,
          "major_category": "电子信息",
          "major_name": "计算机技术",
          "total_score": 355,
          "politics_score": 68,
          "english_score": 72,
          "subject_one_score": 105,
          "subject_two_score": 110
        }

        Response:
        {
          "code": 0,
          "message": "success",
          "data": {
            "total_score_status": "safe",
            "single_subject_status": "safe",
            "line_type": "major",
            "line_detail": {
              "total_score_line": 310,
              "politics_line": 50,
              "english_line": 50,
              "subject_one_line": 75,
              "subject_two_line": 75
            },
            "diff": {
              "total_diff": 45,
              "politics_diff": 18,
              "english_diff": 22,
              "subject_one_diff": 30,
              "subject_two_diff": 35
            },
            "warnings": [],
            "suggestions": ["总分和单科均超过分数线，建议冲刺该专业"]
          }
        }
    """
    payload = request.get_json(silent=True) or {}
    data = evaluate_score(payload)
    return jsonify(success_response(data))


@api_bp.post("/recommend")
def recommend_api():
    """考研择校推荐接口（S10）。"""
    payload = request.get_json(silent=True) or {}
    data = recommend(payload, user_id=current_user_id())
    return jsonify(success_response(data))


@api_bp.post("/report/generate")
def report_generate():
    """推荐报告生成接口（S14）。

    Request Body:
        {
          "recommendation_log_id": int,          # 推荐日志 ID，可选
          "recommendation_trace_id": str,        # 推荐 trace_id，可选
          "report_type": "template" | "llm",    # 当前默认回退 template
          "request": {...},                      # 前端缓存的推荐请求，可选
          "recommendation_result": {...}         # 前端缓存的推荐结果，可选
        }

    Returns:
        {
          "report_id": int,
          "report_type": "template",
          "report_content": str,
          "disclaimer": str,
          "warnings": [str]
        }
    """
    payload = request.get_json(silent=True) or {}
    user_id = current_user_id()
    if user_id and payload.get("recommendation_log_id"):
        try:
            log_id = int(payload["recommendation_log_id"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("recommendation_log_id 必须是整数") from exc
        get_user_recommendation_detail(user_id, log_id)
    data = generate_report(payload)
    return jsonify(success_response(data))


@api_bp.get("/metadata/major-categories")
def metadata_major_categories():
    """专业门类枚举接口。

    返回系统中所有可用的专业门类列表，用于前端下拉列表。

    Returns:
        {
          "from_majors": [str],           # 从 majors 表提取
          "from_score_lines": [str],      # 从专业线提取
          "from_national_lines": [str],   # 从国家线提取
          "combined": [str]               # 合并去重后的完整列表（推荐使用）
        }

    Examples:
        GET /api/metadata/major-categories

        Response:
        {
          "code": 0,
          "message": "success",
          "data": {
            "combined": [
              "哲学",
              "经济学",
              "法学",
              "教育学",
              "文学",
              "理学",
              "工学",
              "医学",
              "管理学",
              "艺术学",
              "计算机技术",
              "电子信息",
              "机械",
              ...
            ],
            "from_majors": [...],
            "from_score_lines": [...],
            "from_national_lines": [...]
          }
        }
    """
    data = list_major_categories(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/metadata/plan-majors")
def metadata_plan_majors():
    """招生计划专业选项接口。

    返回 enrollment_plans 中实际有招生计划数据的专业代码和专业名称，
    用于图表页按专业汇总历年招生计划。

    Query Parameters:
        major_category (str): 专业门类（可选）
        school_id (int): 候选学校 ID（可选）
        limit (int): 返回条数，默认 1000，最大 1000
    """
    data = list_plan_major_options(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/metadata/score-line-majors")
def metadata_score_line_majors():
    """复试线专业选项接口。

    返回某学校中实际有历年复试总分线的专业，并按专业代码和专业名称去重。

    Query Parameters:
        university_id (int): 学校 ID（数据库主键，必填）
        limit (int): 返回条数，默认 1000，最大 1000
    """
    data = list_score_line_major_options(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/metadata/degree-types")
def metadata_degree_types():
    """学位类型枚举接口。

    Returns:
        [
          {"value": "academic", "label": "学术学位（学硕）"},
          {"value": "professional", "label": "专业学位（专硕）"}
        ]

    Examples:
        GET /api/metadata/degree-types
    """
    data = list_degree_types()
    return jsonify(success_response(data))


@api_bp.get("/metadata/study-modes")
def metadata_study_modes():
    """学习方式枚举接口。

    Returns:
        [
          {"value": "full_time", "label": "全日制"},
          {"value": "part_time", "label": "非全日制"}
        ]

    Examples:
        GET /api/metadata/study-modes
    """
    data = list_study_modes()
    return jsonify(success_response(data))


@api_bp.get("/metadata/school-levels")
def metadata_school_levels():
    """学校层次枚举接口。

    Returns:
        [
          {"value": "985 / 211 / 双一流 / 自划线", "label": "985 / 211 / 双一流 / 自划线"},
          {"value": "211 / 双一流", "label": "211 / 双一流"},
          {"value": "普通院校", "label": "普通院校"}
        ]

    Examples:
        GET /api/metadata/school-levels
    """
    data = list_school_levels()
    return jsonify(success_response(data))


@api_bp.get("/metadata/search-major-categories")
def metadata_search_major_categories():
    """专业门类模糊搜索接口。

    Query Parameters:
        keyword (str): 搜索关键词，必填，至少 1 个字符
        limit (int): 返回条数，默认 12，最大 50

    Returns:
        [str]  # 匹配的专业门类列表

    Examples:
        GET /api/metadata/search-major-categories?keyword=计算
        Response: ["计算机技术", "计算机科学与技术"]

        GET /api/metadata/search-major-categories?keyword=工
        Response: ["工学", "工商管理", "工程管理"]
    """
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        raise ValidationError("keyword 参数不能为空")

    limit = int(request.args.get("limit", 12))
    data = search_major_categories(keyword, limit)
    return jsonify(success_response(data))


@api_bp.get("/metadata/search-major-names")
def metadata_search_major_names():
    """目标专业模糊搜索接口。

    Query Parameters:
        keyword (str): 搜索关键词，必填，至少 1 个字符
        limit (int): 返回条数，默认 12，最大 50

    Returns:
        [
            {
                "major_name": "计算机技术",
                "major_code": "085404",
                "major_category": "电子信息",
                "match_count": 15
            }
        ]

    Examples:
        GET /api/metadata/search-major-names?keyword=计算机
        Response: [
            {"major_name": "计算机技术", "major_code": "085404", "major_category": "电子信息", "match_count": 15},
            {"major_name": "计算机科学与技术", "major_code": "081200", "major_category": "工学", "match_count": 12}
        ]
    """
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        raise ValidationError("keyword 参数不能为空")

    limit = int(request.args.get("limit", 12))
    data = search_major_names(keyword, limit, request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/chart/line-trend")
def chart_line_trend():
    """复试线趋势图接口（S12）。

    返回某学校某专业历年复试总分线走势。

    Query Parameters:
        university_id (int): 学校 ID（数据库主键，必填）
        score_line_major_name (str): score_lines 表中的分数线专业名称

    Returns:
        {
          "x_axis": [int],            # 年份列表
          "series": [
            {"name": "总分线", "data": [int]}
          ],
          "warnings": [str],          # 数据不足等风险提示
          "year_range": {"min_year": int, "max_year": int},
          "source_note": str          # 数据来源说明
        }

    Examples:
        GET /api/chart/line-trend?university_id=1&score_line_major_name=计算机技术
    """
    data = get_line_trend(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/chart/admission-score-trend")
def chart_admission_score_trend():
    """拟录取分数趋势图接口（S12）。

    返回某学校某专业历年拟录取初试分（最低分、平均分、最高分）走势。
    当前项目暂无拟录取明细样例数据时返回空数组并附提示，不报错。

    Query Parameters:
        university_id (int): 学校 ID（数据库主键，必填）
        major_id (int): 专业 ID（数据库主键，必填）

    Returns:
        统一图表结构（x_axis、series、warnings、year_range、source_note）。

    Examples:
        GET /api/chart/admission-score-trend?university_id=1&major_id=100
    """
    data = get_admission_score_trend(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/chart/plan-trend")
def chart_plan_trend():
    """招生计划变化图接口（S12）。

    返回历年招生计划总量和招生专业数走势，支持按学校、专业门类或具体专业筛选。

    Query Parameters:
        university_id (int): 学校 ID（可选）
        major_category (str): 专业门类（可选）
        major_code (str): 专业代码（可选）
        major_name (str): 专业名称（可选）

    Returns:
        统一图表结构。series 含“招生计划总数”和“招生专业数”两组数据。

    Examples:
        GET /api/chart/plan-trend
        GET /api/chart/plan-trend?university_id=1
        GET /api/chart/plan-trend?major_category=工学
        GET /api/chart/plan-trend?major_code=085404&major_name=计算机技术
    """
    data = get_plan_trend(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/chart/major-heat")
def chart_major_heat():
    """专业热度图接口（S12）。

    按专业门类统计招生计划总数和专业方向数量，反映各门类报考热度。

    Query Parameters:
        year (int): 招生年份（可选，默认取最新有数据的年份）
        top (int): 返回前 N 个门类，默认 10，最大 30

    Returns:
        统一图表结构。x_axis 为专业门类，series 含招生计划总数和专业方向数。

    Examples:
        GET /api/chart/major-heat
        GET /api/chart/major-heat?year=2026&top=12
    """
    data = get_major_heat(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.get("/chart/university-type")
def chart_university_type():
    """学校类型分布图接口（S12）。

    按学校类型 / 覆盖优先级 / 学校层次统计研招单位数量，适合饼图展示。

    Query Parameters:
        dimension (str): 统计维度，type（默认）/ priority / level

    Returns:
        统一图表结构。series[0] 额外包含 pie_data（{name, value} 列表）。

    Examples:
        GET /api/chart/university-type
        GET /api/chart/university-type?dimension=priority
        GET /api/chart/university-type?dimension=level
    """
    data = get_university_type(request.args.to_dict())
    return jsonify(success_response(data))


@api_bp.post("/chat")
def chat_assistant():
    """AI 助手聊天接口。

    处理用户聊天请求，回答网站功能、使用方法和考研择校相关问题。
    返回 Markdown 格式内容，包含页面跳转链接。

    Request Body:
        message (str): 用户消息内容，必填
        history (list): 对话历史（可选），格式为 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        {
          "trace_id": "...",
          "message": "AI 回复内容（Markdown 格式）",
          "status": "success" | "fallback"
        }

    Examples:
        POST /api/chat
        {
          "message": "如何查看学校列表？",
          "history": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！我是考研择校推荐系统的 AI 助手..."}
          ]
        }

        Response:
        {
          "code": 0,
          "message": "success",
          "trace_id": "...",
          "data": {
            "trace_id": "...",
            "message": "您可以前往 [学校列表](/universities) 查看重庆所有招生院校...",
            "status": "success"
          }
        }
    """
    payload = request.get_json(silent=True) or {}
    data = chat(payload)
    return jsonify(success_response(data))


@api_bp.post("/conversation/chat")
def conversation_chat():
    """对话式推荐接口。

    通过多轮对话引导用户完成信息收集并生成推荐。

    Request Body:
        session_id (str): 会话 ID（可选，首次调用自动生成）
        message (str): 用户消息内容，必填

    Returns:
        {
          "session_id": "...",
          "response": "AI 回复内容",
          "step": "greeting|basic_info|target_major|...",
          "user_profile": {...}
        }
    """
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    user_message = str(payload.get("message") or "").strip()

    if not user_message:
        raise ValidationError("message 不能为空")

    # 获取或创建会话
    if not session_id or session_id not in conversation_sessions:
        import uuid
        session_id = str(uuid.uuid4())
        conversation_sessions[session_id] = ConversationState(session_id)

    state = conversation_sessions[session_id]
    agent = ConversationAgent()

    # 处理消息
    response_text, updated_state = agent.process_message(state, user_message, user_id=current_user_id())
    conversation_sessions[session_id] = updated_state

    return jsonify(success_response({
        "session_id": session_id,
        "response": response_text,
        "step": updated_state.step.value,
        "user_profile": updated_state.user_profile.to_dict(),
        "recommendations": updated_state.recommendations,
        "recommendation_request": updated_state.recommendation_request,
        "recommendation_result": updated_state.recommendation_result,
    }))


@api_bp.delete("/conversation/sessions/<session_id>")
def conversation_delete_session(session_id: str):
    """删除对话会话。"""
    if session_id in conversation_sessions:
        del conversation_sessions[session_id]
    return jsonify(success_response({"message": "会话已删除"}))


@api_bp.post("/school/analyze")
def school_analyze():
    """院校分析接口。

    生成单个院校的详细优劣势分析和备考建议。

    Request Body:
        school_name (str): 学校名称，必填
        score_line (int): 复试分数线，必填
        user_score (int): 考生预估分，必填
        province (str): 所在省份（可选）
        level (str): 学校层次（可选）
        target_major (str): 目标专业（可选）
        subject_level (str): 学科评估等级（可选）
        match_score (int): 匹配度评分（可选）

    Returns:
        {
          "school_name": "...",
          "analysis": "Markdown 格式的分析内容",
          "status": "success" | "fallback"
        }

    Examples:
        POST /api/school/analyze
        {
          "school_name": "重庆大学",
          "score_line": 310,
          "user_score": 355,
          "province": "重庆",
          "level": "985 / 211 / 双一流",
          "target_major": "计算机技术",
          "subject_level": "B+",
          "match_score": 85
        }
    """
    payload = request.get_json(silent=True) or {}

    school_name = str(payload.get("school_name") or "").strip()
    if not school_name:
        raise ValidationError("school_name 不能为空")

    try:
        score_line = int(payload.get("score_line", 0))
        user_score = int(payload.get("user_score", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("score_line 和 user_score 必须是整数") from exc

    data = analyze_school(
        school_name=school_name,
        score_line=score_line,
        user_score=user_score,
        province=payload.get("province"),
        level=payload.get("level"),
        target_major=payload.get("target_major"),
        subject_level=payload.get("subject_level"),
        match_score=payload.get("match_score"),
    )
    return jsonify(success_response(data))
