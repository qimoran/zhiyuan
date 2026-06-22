"""推荐资料核验智能体。

该模块作为推荐规则之后的增强层：从本地 PDF 知识库和 Tavily 搜索中检索
学校、专业、年份相关资料，把招生简章/招生计划证据附加到推荐结果中。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT, get_bool_env, get_env, get_int_env
from src.common.database import fetch_all
from src.common.logger import get_logger

logger = get_logger(__name__)

DEFAULT_RAG_DIR = PROJECT_ROOT / "data" / "rag"
DEFAULT_LOCAL_TOP_K = 3
DEFAULT_TAVILY_TOP_K = 3
DOCUMENT_TYPES = {
    "official_plan",
    "official_score",
    "official_admission",
    "catalog",
    "plan",
    "notice",
    "score_line",
}


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool
    local_rag_enabled: bool
    tavily_enabled: bool
    rag_dirs: list[Path]
    local_top_k: int
    tavily_top_k: int
    tavily_api_key: str
    tavily_api_url: str
    tavily_timeout_seconds: int


def enrich_recommendation_result(result: dict[str, Any], recommend_input: Any) -> dict[str, Any]:
    """对推荐结果执行本地 RAG 与 Tavily 资料增强。"""
    config = get_agent_config()
    status = build_initial_status(config)
    result["recommendation_agent"] = status
    if not config.enabled:
        return result

    all_items = [item for items in result.get("recommendations", {}).values() for item in items]
    if not all_items:
        status["warnings"].append("没有可增强的推荐候选。")
        return result

    for item in all_items:
        try:
            evidence = build_item_evidence(item, recommend_input, config)
            apply_agent_evidence(item, evidence)
            status["enriched_items"] += 1
            status["local_hit_count"] += len(evidence.get("local_rag", []))
            status["web_hit_count"] += len(evidence.get("tavily", []))
        except Exception as exc:
            logger.warning("推荐资料智能体增强失败：%s", exc)
            item.setdefault("warnings", []).append("资料核验智能体暂时不可用，该候选仅使用数据库推荐结果。")
            status["warnings"].append(f"{item.get('university_name', '候选院校')} 资料增强失败")

    for items in result.get("recommendations", {}).values():
        items.sort(key=lambda row: float(row.get("recommend_score") or 0), reverse=True)

    if config.local_rag_enabled and status["local_hit_count"] == 0:
        status["warnings"].append("本地 RAG 知识库未检索到匹配的 PDF 证据。")
    if config.tavily_enabled and not config.tavily_api_key:
        status["warnings"].append("未配置 TAVILY_API_KEY，已跳过联网搜索。")
    return result


def get_agent_config() -> AgentConfig:
    rag_dir_text = get_env("RECOMMEND_RAG_DIR", str(DEFAULT_RAG_DIR))
    rag_dirs = [Path(part).expanduser() for part in re.split(r"[;|]", rag_dir_text) if part.strip()]
    resolved_dirs = [path if path.is_absolute() else PROJECT_ROOT / path for path in rag_dirs]
    tavily_api_key = get_env("TAVILY_API_KEY", "")
    tavily_enabled = get_bool_env("TAVILY_SEARCH_ENABLED", True)
    return AgentConfig(
        enabled=get_bool_env("RECOMMEND_AGENT_ENABLED", True),
        local_rag_enabled=get_bool_env("LOCAL_RAG_ENABLED", True),
        tavily_enabled=tavily_enabled,
        rag_dirs=resolved_dirs,
        local_top_k=get_int_env("LOCAL_RAG_TOP_K", DEFAULT_LOCAL_TOP_K),
        tavily_top_k=get_int_env("TAVILY_TOP_K", DEFAULT_TAVILY_TOP_K),
        tavily_api_key=tavily_api_key,
        tavily_api_url=get_env("TAVILY_API_URL", "https://api.tavily.com/search"),
        tavily_timeout_seconds=get_int_env("TAVILY_TIMEOUT_SECONDS", 12),
    )


def build_initial_status(config: AgentConfig) -> dict[str, Any]:
    return {
        "enabled": config.enabled,
        "local_rag_enabled": config.local_rag_enabled,
        "tavily_enabled": config.tavily_enabled,
        "tavily_configured": bool(config.tavily_api_key),
        "rag_dirs": [str(path) for path in config.rag_dirs],
        "enriched_items": 0,
        "local_hit_count": 0,
        "web_hit_count": 0,
        "warnings": [],
    }


def build_item_evidence(item: dict[str, Any], recommend_input: Any, config: AgentConfig) -> dict[str, Any]:
    query = build_query(item, recommend_input)
    local_hits = search_local_rag(item, recommend_input, query, config) if config.local_rag_enabled else []
    tavily_hits = search_tavily(query, config) if config.tavily_enabled and config.tavily_api_key else []
    return {
        "query": query,
        "local_rag": local_hits,
        "tavily": tavily_hits,
    }


def build_query(item: dict[str, Any], recommend_input: Any) -> str:
    parts = [
        item.get("university_name"),
        item.get("major_name"),
        getattr(recommend_input, "target_year", None),
        "研究生 招生简章 招生计划 复试线",
    ]
    return " ".join(str(part) for part in parts if part)


def search_local_rag(
    item: dict[str, Any],
    recommend_input: Any,
    query: str,
    config: AgentConfig,
) -> list[dict[str, Any]]:
    keywords = build_keywords(item, recommend_input)
    documents = collect_local_documents(item, recommend_input, config)
    scored_hits: list[dict[str, Any]] = []
    for document in documents:
        text = read_pdf_text(document["path"])
        if not text:
            continue
        chunk, score = best_text_chunk(text, keywords)
        if score <= 0:
            continue
        scored_hits.append(
            {
                "title": document["title"],
                "path": str(document["path"]),
                "source_url": document.get("source_url"),
                "score": score,
                "snippet": compact_text(chunk, 220),
            }
        )
    scored_hits.sort(key=lambda row: row["score"], reverse=True)
    return scored_hits[: max(1, config.local_top_k)]


def collect_local_documents(item: dict[str, Any], recommend_input: Any, config: AgentConfig) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    docs.extend(query_source_documents(item, recommend_input))
    docs.extend(scan_rag_dirs(item, recommend_input, config.rag_dirs))

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for doc in docs:
        path = Path(doc["path"])
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.exists() or resolved.suffix.lower() != ".pdf":
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({**doc, "path": resolved})
    return result[:50]


def query_source_documents(item: dict[str, Any], recommend_input: Any) -> list[dict[str, Any]]:
    university_id = item.get("university_id")
    if not university_id:
        return []
    rows = fetch_all(
        """
        SELECT document_title, source_url, local_path, document_type, year
        FROM source_documents
        WHERE university_id = %(university_id)s
          AND local_path IS NOT NULL
          AND local_path <> ''
          AND (year IS NULL OR year BETWEEN %(start_year)s AND %(target_year)s)
        ORDER BY year DESC, id DESC
        LIMIT 20
        """,
        {
            "university_id": university_id,
            "start_year": int(getattr(recommend_input, "target_year", 0) or 0) - 1,
            "target_year": getattr(recommend_input, "target_year", None),
        },
    )
    result = []
    for row in rows:
        if row.get("document_type") not in DOCUMENT_TYPES:
            continue
        result.append(
            {
                "title": row.get("document_title") or "本地来源资料",
                "source_url": row.get("source_url"),
                "path": row.get("local_path"),
            }
        )
    return result


def scan_rag_dirs(item: dict[str, Any], recommend_input: Any, rag_dirs: list[Path]) -> list[dict[str, Any]]:
    school_name = str(item.get("university_name") or "").strip()
    major_name = str(item.get("major_name") or "").strip()
    target_year = str(getattr(recommend_input, "target_year", "") or "").strip()
    docs: list[dict[str, Any]] = []
    for rag_dir in rag_dirs:
        if not rag_dir.exists():
            continue
        for path in rag_dir.rglob("*.pdf"):
            name = path.name
            if is_matching_rag_file(name, school_name, major_name, target_year):
                docs.append({"title": path.stem, "path": path})
    return docs


def is_matching_rag_file(file_name: str, school_name: str, major_name: str, target_year: str) -> bool:
    """判断 PDF 文件名是否可能属于当前推荐候选。

    不能只按年份匹配，否则所有 2026 年 PDF 都会被扫入候选，导致本地 RAG
    多读无关文件。优先按学校名匹配；没有学校名时，再用“专业+年份”兜底。
    """
    normalized = re.sub(r"\s+", "", file_name)
    school = re.sub(r"\s+", "", school_name)
    major = re.sub(r"\s+", "", major_name)
    if school and school in normalized:
        return True
    if major and target_year and major in normalized and target_year in normalized:
        return True
    if major and not target_year and major in normalized:
        return True
    return False


def build_keywords(item: dict[str, Any], recommend_input: Any) -> list[str]:
    keywords = [
        item.get("university_name"),
        item.get("major_name"),
        item.get("major_code"),
        str(getattr(recommend_input, "target_year", "")),
        "招生简章",
        "招生计划",
        "拟招生",
        "复试",
    ]
    return [str(keyword).strip() for keyword in keywords if str(keyword or "").strip()]


@lru_cache(maxsize=128)
def _read_pdf_text_cached(path_text: str, mtime: float) -> str:
    try:
        import pdfplumber
    except ImportError:
        logger.warning("缺少 pdfplumber，无法读取本地 PDF 知识库")
        return ""

    try:
        parts = []
        with pdfplumber.open(path_text) as pdf:
            for page in pdf.pages[:80]:
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text)
        return "\n".join(parts)
    except Exception as exc:
        logger.warning("读取 PDF 失败：%s %s", path_text, exc)
        return ""


def read_pdf_text(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    return _read_pdf_text_cached(str(path), mtime)


def best_text_chunk(text: str, keywords: list[str]) -> tuple[str, int]:
    normalized = re.sub(r"\s+", " ", text)
    if not normalized:
        return "", 0
    candidates = split_chunks(normalized)
    best = ""
    best_score = 0
    for chunk in candidates:
        score = sum(chunk.count(keyword) for keyword in keywords)
        if score > best_score:
            best = chunk
            best_score = score
    return best, best_score


def split_chunks(text: str, size: int = 520, overlap: int = 80) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def search_tavily(query: str, config: AgentConfig) -> list[dict[str, Any]]:
    try:
        import requests
    except ImportError:
        logger.warning("缺少 requests，无法调用 Tavily")
        return []

    payload = {
        "api_key": config.tavily_api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, config.tavily_top_k),
        "include_answer": True,
    }
    try:
        response = requests.post(config.tavily_api_url, json=payload, timeout=config.tavily_timeout_seconds)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Tavily 搜索失败：%s", exc)
        return []

    results = data.get("results") if isinstance(data, dict) else []
    if not isinstance(results, list):
        return []
    hits = []
    for row in results[: max(1, config.tavily_top_k)]:
        if not isinstance(row, dict):
            continue
        hits.append(
            {
                "title": row.get("title") or "Tavily 搜索结果",
                "url": row.get("url"),
                "score": row.get("score"),
                "snippet": compact_text(row.get("content") or "", 220),
            }
        )
    return hits


def apply_agent_evidence(item: dict[str, Any], evidence: dict[str, Any]) -> None:
    local_hits = evidence.get("local_rag") or []
    web_hits = evidence.get("tavily") or []
    adjustment = min(5.0, len(local_hits) * 2.0 + len(web_hits) * 1.0)
    item["agent_evidence"] = evidence
    item["agent_adjustment_score"] = adjustment
    item["source_confidence"] = build_source_confidence(local_hits, web_hits)
    item["evidence_summary"] = build_evidence_summary(local_hits, web_hits)
    if adjustment:
        item["recommend_score"] = round(float(item.get("recommend_score") or 0) + adjustment, 2)
        item["data_quality_score"] = round(min(100.0, float(item.get("data_quality_score") or 0) + adjustment), 2)
    if not local_hits and not web_hits:
        item.setdefault("warnings", []).append("未检索到本地 PDF 或联网搜索证据，建议人工核对最新招生简章。")


def build_source_confidence(local_hits: list[dict[str, Any]], web_hits: list[dict[str, Any]]) -> str:
    if local_hits and web_hits:
        return "high"
    if local_hits:
        return "medium"
    if web_hits:
        return "low"
    return "unknown"


def build_evidence_summary(local_hits: list[dict[str, Any]], web_hits: list[dict[str, Any]]) -> str:
    if local_hits:
        first = local_hits[0]
        return f"本地资料匹配：{first.get('title')}。{first.get('snippet', '')}"
    if web_hits:
        first = web_hits[0]
        return f"联网搜索匹配：{first.get('title')}。{first.get('snippet', '')}"
    return "暂无招生简章或招生计划证据匹配。"


def compact_text(value: Any, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
