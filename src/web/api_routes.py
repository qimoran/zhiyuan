"""S08 基础 API 路由。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.common.database import ping_database
from src.common.logger import get_logger
from src.common.response import success_response
from src.services.query_service import (
    get_health_detail,
    list_majors,
    list_sources,
    list_universities,
)
from src.services.score_service import evaluate_score
from src.services.metadata_service import (
    list_major_categories,
    list_degree_types,
    list_study_modes,
    list_school_levels,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = get_logger("app")


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
    data = list_major_categories()
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
