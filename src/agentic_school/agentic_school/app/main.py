from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional
import uuid

from app.config import get_settings
from app.database import get_db
from app.services.agent import SchoolSelectionAgent, ConversationState
from app.services.query_service import SchoolQueryService
from app.services.llm_client import DeepSeekClient

settings = get_settings()

app = FastAPI(
    title="考研择校助手",
    description="基于 AI 的考研择校智能推荐系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: Dict[str, ConversationState] = {}


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    step: str


class SchoolSearchRequest(BaseModel):
    province: Optional[str] = None
    school_type: Optional[str] = None
    school_level: Optional[str] = None
    keyword: Optional[str] = None


class MajorSearchRequest(BaseModel):
    keyword: Optional[str] = None
    category: Optional[str] = None
    degree_type: Optional[str] = None
    university_id: Optional[int] = None


class RecommendRequest(BaseModel):
    undergraduate_school: Optional[str] = None
    undergraduate_major: Optional[str] = None
    exam_year: Optional[str] = None
    student_type: Optional[str] = None
    major_category: Optional[str] = None
    target_major: Optional[str] = None
    degree_type: Optional[str] = None
    study_mode: Optional[str] = None
    target_province: Optional[str] = None
    target_city: Optional[str] = None
    estimated_score: int = 300
    school_level: Optional[str] = None
    school_type: Optional[str] = None
    risk_preference: Optional[str] = "balanced"


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("<head>", '<head><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">')
    return html


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db=Depends(get_db)):
    session_id = request.session_id
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = ConversationState(session_id=session_id)

    state = sessions[session_id]
    agent = SchoolSelectionAgent(db)

    response, updated_state = agent.process_message(state, request.message)
    sessions[session_id] = updated_state

    return ChatResponse(
        session_id=session_id,
        response=response,
        step=updated_state.step.value,
    )


@app.get("/api/universities")
async def list_universities(db=Depends(get_db)):
    service = SchoolQueryService(db)
    return service.get_all_universities()


@app.get("/api/universities/{university_id}")
async def get_university(university_id: int, db=Depends(get_db)):
    service = SchoolQueryService(db)
    info = service.get_comprehensive_info(university_id)
    if not info:
        raise HTTPException(status_code=404, detail="University not found")
    return info


@app.post("/api/universities/search")
async def search_universities(request: SchoolSearchRequest, db=Depends(get_db)):
    service = SchoolQueryService(db)
    return service.search_universities(
        province=request.province,
        school_type=request.school_type,
        school_level=request.school_level,
        keyword=request.keyword,
    )


@app.get("/api/universities/{university_id}/majors")
async def get_university_majors(university_id: int, db=Depends(get_db)):
    service = SchoolQueryService(db)
    return service.get_majors_by_university(university_id)


@app.get("/api/universities/{university_id}/score-lines")
async def get_university_score_lines(
    university_id: int,
    year: Optional[int] = None,
    db=Depends(get_db),
):
    service = SchoolQueryService(db)
    return service.get_score_lines(university_id=university_id, year=year)


@app.post("/api/majors/search")
async def search_majors(request: MajorSearchRequest, db=Depends(get_db)):
    service = SchoolQueryService(db)
    return service.search_majors(
        keyword=request.keyword,
        category=request.category,
        degree_type=request.degree_type,
        university_id=request.university_id,
    )


@app.post("/api/recommend")
async def recommend_schools(request: RecommendRequest, db=Depends(get_db)):
    import traceback
    try:
        service = SchoolQueryService(db)
        result = service.recommend_schools_chong_wen_bao(
            user_score=request.estimated_score,
            major_category=request.major_category,
            target_major=request.target_major,
            province=request.target_province,
            school_level=request.school_level,
            school_type=request.school_type,
            degree_type=request.degree_type,
            risk_preference=request.risk_preference or "balanced",
        )
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"推荐失败: {str(e)}")


class AnalyzeRequest(BaseModel):
    school_name: str
    score_line: int
    user_score: int
    match_score: int
    subject_level: Optional[str] = None
    province: Optional[str] = None
    level: Optional[str] = None
    target_major: Optional[str] = None


@app.post("/api/analyze")
async def analyze_school(request: AnalyzeRequest):
    llm = DeepSeekClient()
    
    prompt = f"""你是一位专业的考研择校顾问。请分析以下院校的报考优劣势：

院校信息：
- 学校名称：{request.school_name}
- 所在地区：{request.province or '未知'}
- 学校层次：{request.level or '普通院校'}
- 复试分数线：{request.score_line}分
- 考生预估分：{request.user_score}分
- 分差：{request.user_score - request.score_line}分
- 匹配度评分：{request.match_score}分
- 学科评估：{request.subject_level or '未知'}
- 目标专业：{request.target_major or '未知'}

请从以下角度分析（每点不超过50字）：

1. **报考优势**（2-3点）
2. **潜在风险**（2-3点）
3. **备考建议**（具体可执行的建议）

请用简洁专业的语言回答，不要使用emoji。"""

    try:
        analysis = llm.chat([{"role": "user", "content": prompt}])
        return {"analysis": analysis}
    except Exception as e:
        return {"analysis": f"分析生成失败：{str(e)}"}


@app.get("/api/score-lines/national/{year}")
async def get_national_score_lines(year: int, db=Depends(get_db)):
    service = SchoolQueryService(db)
    return service.get_national_score_lines(year)


@app.get("/api/categories")
async def get_major_categories(degree_type: Optional[str] = None, db=Depends(get_db)):
    service = SchoolQueryService(db)
    return {"categories": service.get_major_categories(degree_type)}


@app.get("/api/provinces")
async def get_provinces(db=Depends(get_db)):
    service = SchoolQueryService(db)
    return {"provinces": service.get_provinces()}


@app.get("/api/school-types")
async def get_school_types(db=Depends(get_db)):
    service = SchoolQueryService(db)
    return {"types": service.get_school_types()}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"message": "Session deleted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
