from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models import University, Department, Major, ScoreLine, SubjectLevelRate


class SchoolQueryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_universities(self) -> List[Dict[str, Any]]:
        universities = self.db.query(University).all()
        return [
            {
                "id": u.id,
                "name": u.university_name,
                "province": u.province,
                "city": u.city,
                "type": u.school_type,
                "level": u.school_level,
            }
            for u in universities
        ]

    def get_university_by_id(self, university_id: int) -> Optional[Dict[str, Any]]:
        u = self.db.query(University).filter(University.id == university_id).first()
        if not u:
            return None
        return {
            "id": u.id,
            "name": u.university_name,
            "province": u.province,
            "city": u.city,
            "type": u.school_type,
            "level": u.school_level,
        }

    def search_universities(
        self,
        province: Optional[str] = None,
        school_type: Optional[str] = None,
        school_level: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(University)

        if province:
            query = query.filter(University.province == province)
        if school_type:
            query = query.filter(University.school_type == school_type)
        if school_level:
            query = query.filter(University.school_level.contains(school_level))
        if keyword:
            query = query.filter(University.university_name.contains(keyword))

        universities = query.all()
        return [
            {
                "id": u.id,
                "name": u.university_name,
                "province": u.province,
                "city": u.city,
                "type": u.school_type,
                "level": u.school_level,
            }
            for u in universities
        ]

    def get_departments_by_university(self, university_id: int) -> List[Dict[str, Any]]:
        departments = (
            self.db.query(Department)
            .filter(Department.university_id == university_id)
            .all()
        )
        return [
            {"id": d.id, "name": d.department_name, "university_id": d.university_id}
            for d in departments
        ]

    def get_majors_by_university(
        self, university_id: int, department_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        query = self.db.query(Major).filter(Major.university_id == university_id)
        if department_id:
            query = query.filter(Major.department_id == department_id)

        majors = query.all()
        return [
            {
                "id": m.id,
                "code": m.major_code,
                "name": m.major_name,
                "category": m.major_category,
                "degree_type": m.degree_type,
                "study_mode": m.study_mode,
                "research_direction": m.research_direction,
                "exam_subjects": m.exam_subjects,
                "department_id": m.department_id,
            }
            for m in majors
        ]

    def search_majors(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        degree_type: Optional[str] = None,
        university_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(Major)

        if keyword:
            query = query.filter(
                or_(
                    Major.major_name.contains(keyword),
                    Major.major_code.contains(keyword),
                )
            )
        if category:
            query = query.filter(Major.major_category == category)
        if degree_type:
            query = query.filter(Major.degree_type == degree_type)
        if university_id:
            query = query.filter(Major.university_id == university_id)

        majors = query.limit(50).all()
        return [
            {
                "id": m.id,
                "code": m.major_code,
                "name": m.major_name,
                "category": m.major_category,
                "degree_type": m.degree_type,
                "university_id": m.university_id,
            }
            for m in majors
        ]

    def get_score_lines(
        self,
        university_id: Optional[int] = None,
        major_id: Optional[int] = None,
        year: Optional[int] = None,
        line_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(ScoreLine)

        if university_id:
            query = query.filter(ScoreLine.university_id == university_id)
        if major_id:
            query = query.filter(ScoreLine.major_id == major_id)
        if year:
            query = query.filter(ScoreLine.year == year)
        if line_type:
            query = query.filter(ScoreLine.line_type == line_type)

        score_lines = query.order_by(ScoreLine.year.desc()).limit(100).all()
        return [
            {
                "id": s.id,
                "year": s.year,
                "line_type": s.line_type,
                "university_id": s.university_id,
                "major_id": s.major_id,
                "major_category": s.major_category,
                "total_score": s.total_score_line,
                "politics": s.politics_line,
                "english": s.english_line,
                "subject_one": s.subject_one_line,
                "subject_two": s.subject_two_line,
                "diff_to_national": s.score_diff_to_national,
            }
            for s in score_lines
        ]

    def get_national_score_lines(self, year: int) -> List[Dict[str, Any]]:
        score_lines = (
            self.db.query(ScoreLine)
            .filter(ScoreLine.line_type == "national", ScoreLine.year == year)
            .all()
        )
        return [
            {
                "id": s.id,
                "year": s.year,
                "major_category": s.major_category,
                "total_score": s.total_score_line,
                "politics": s.politics_line,
                "english": s.english_line,
                "subject_one": s.subject_one_line,
                "subject_two": s.subject_two_line,
            }
            for s in score_lines
        ]

    def get_subject_level_rates(
        self, university_id: Optional[int] = None, subject_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = self.db.query(SubjectLevelRate)

        if university_id:
            query = query.filter(SubjectLevelRate.university_id == university_id)
        if subject_name:
            query = query.filter(SubjectLevelRate.subject_name.contains(subject_name))

        rates = query.all()
        return [
            {
                "id": r.id,
                "university_id": r.university_id,
                "subject_code": r.subject_code,
                "subject_name": r.subject_name,
                "level": r.level_rate,
                "degree_type": r.degree_type,
            }
            for r in rates
        ]

    def get_major_categories(self, degree_type: Optional[str] = None) -> List[str]:
        query = self.db.query(Major.major_category).filter(Major.major_category.isnot(None))
        
        if degree_type:
            query = query.filter(Major.degree_type == degree_type)
        
        result = query.distinct().all()
        return [r[0] for r in result if r[0]]

    def get_school_types(self) -> List[str]:
        result = (
            self.db.query(University.school_type)
            .filter(University.school_type.isnot(None))
            .distinct()
            .all()
        )
        return [r[0] for r in result if r[0]]

    def get_provinces(self) -> List[str]:
        result = self.db.query(University.province).distinct().all()
        return [r[0] for r in result if r[0]]

    def get_comprehensive_info(self, university_id: int) -> Dict[str, Any]:
        university = self.get_university_by_id(university_id)
        if not university:
            return {}

        departments = self.get_departments_by_university(university_id)
        majors = self.get_majors_by_university(university_id)
        score_lines = self.get_score_lines(university_id=university_id)
        subject_rates = self.get_subject_level_rates(university_id=university_id)

        return {
            "university": university,
            "departments": departments,
            "majors": majors,
            "score_lines": score_lines,
            "subject_rates": subject_rates,
        }

    def _calculate_match_score(
        self, 
        user_score: int, 
        score_line: int, 
        school_level: Optional[str],
        subject_level: Optional[str]
    ) -> int:
        score_diff = user_score - score_line
        
        if score_diff >= 20:
            base_score = 95
        elif score_diff >= 10:
            base_score = 85
        elif score_diff >= 0:
            base_score = 75
        elif score_diff >= -10:
            base_score = 65
        elif score_diff >= -20:
            base_score = 55
        else:
            base_score = 40
        
        if school_level:
            if "985" in school_level:
                base_score -= 10
            elif "211" in school_level:
                base_score -= 5
        
        if subject_level:
            if subject_level in ["A+", "A"]:
                base_score -= 5
            elif subject_level in ["A-", "B+"]:
                base_score -= 2
        
        return max(30, min(99, base_score))

    def _get_subject_scores(
        self,
        score_line: ScoreLine,
        user_score: int
    ) -> Dict[str, int]:
        # 各科目标分 = 按用户预估总分 × 各科权重
        # 考研总分为 500 分（政治100 + 英语100 + 专业课一150 + 专业课二150）
        # 权重：政治 20%、英语 20%、专业课一 30%、专业课二 30%
        politics_target = int(user_score * 0.20)
        english_target = int(user_score * 0.20)
        subject_one_target = int(user_score * 0.30)
        subject_two_target = int(user_score * 0.30)

        # 数据库中 politics_line/english_line 可能是国家线占位值（35/45），
        # 用 < 50 过滤掉，只保留学校真实划线
        def get_real_line(value):
            if value and value >= 50:
                return int(value)
            return None

        politics_line = get_real_line(score_line.politics_line)
        english_line = get_real_line(score_line.english_line)
        subject_one_line = get_real_line(score_line.subject_one_line)
        subject_two_line = get_real_line(score_line.subject_two_line)

        return {
            "politics_line": politics_line,
            "english_line": english_line,
            "subject_one_line": subject_one_line,
            "subject_two_line": subject_two_line,
            "politics_target": politics_target,
            "english_target": english_target,
            "subject_one_target": subject_one_target,
            "subject_two_target": subject_two_target,
        }

    def recommend_schools_chong_wen_bao(
        self,
        user_score: int,
        major_category: Optional[str] = None,
        target_major: Optional[str] = None,
        province: Optional[str] = None,
        school_level: Optional[str] = None,
        school_type: Optional[str] = None,
        degree_type: Optional[str] = None,
        risk_preference: str = "balanced",
    ) -> Dict[str, Any]:
        query = (
            self.db.query(University, ScoreLine, Major)
            .join(ScoreLine, University.id == ScoreLine.university_id)
            .join(Major, ScoreLine.major_id == Major.id)
            .filter(ScoreLine.total_score_line.isnot(None))
            .filter(ScoreLine.year >= 2023)
        )

        if major_category:
            query = query.filter(Major.major_category == major_category)
        if target_major:
            query = query.filter(Major.major_name.contains(target_major))
        if province:
            query = query.filter(University.province == province)
        if school_level:
            query = query.filter(University.school_level.contains(school_level))
        if school_type:
            query = query.filter(University.school_type == school_type)
        if degree_type:
            query = query.filter(Major.degree_type == degree_type)

        results = query.order_by(ScoreLine.total_score_line.desc()).limit(200).all()

        schools_data = []
        seen_universities = set()

        for u, s, m in results:
            if u.id in seen_universities:
                continue
            seen_universities.add(u.id)

            score_line = s.total_score_line or 0
            score_diff = user_score - score_line

            subject_rate = (
                self.db.query(SubjectLevelRate)
                .filter(SubjectLevelRate.university_id == u.id)
                .filter(SubjectLevelRate.subject_name.contains(m.major_name[:4] if m.major_name else ""))
                .first()
            )
            
            subject_level = subject_rate.level_rate if subject_rate else None
            
            match_score = self._calculate_match_score(
                user_score, score_line, u.school_level, subject_level
            )
            
            subject_scores = self._get_subject_scores(s, user_score)

            schools_data.append({
                "id": u.id,
                "name": u.university_name,
                "province": u.province,
                "city": u.city,
                "level": u.school_level,
                "type": u.school_type,
                "score_line": score_line,
                "score_diff": score_diff,
                "subject_level": subject_level,
                "matching_majors": m.major_name if m else None,
                "match_score": match_score,
                "subject_scores": subject_scores,
                "exam_subjects": m.exam_subjects if m else None,
                "year": s.year,
            })

        chong = []
        wen = []
        bao = []

        for school in schools_data:
            diff = school["score_diff"]
            if -20 <= diff < 0:
                chong.append(school)
            elif 0 <= diff <= 15:
                wen.append(school)
            elif diff > 15:
                bao.append(school)

        chong = sorted(chong, key=lambda x: x["score_diff"], reverse=True)
        wen = sorted(wen, key=lambda x: x["score_diff"])
        bao = sorted(bao, key=lambda x: x["score_diff"])

        if risk_preference == "balanced":
            return {"chong": chong[:3], "wen": wen[:3], "bao": bao[:3]}
        elif risk_preference == "aggressive":
            return {"chong": chong[:5], "wen": wen[:3], "bao": bao[:1]}
        else:
            return {"chong": chong[:1], "wen": wen[:3], "bao": bao[:5]}

    def recommend_schools(
        self,
        province: Optional[str] = None,
        school_type: Optional[str] = None,
        school_level: Optional[str] = None,
        major_category: Optional[str] = None,
        score_range: Optional[tuple] = None,
    ) -> List[Dict[str, Any]]:
        query = (
            self.db.query(University)
            .outerjoin(Major, University.id == Major.university_id)
            .outerjoin(ScoreLine, University.id == ScoreLine.university_id)
        )

        if province:
            query = query.filter(University.province == province)
        if school_type:
            query = query.filter(University.school_type == school_type)
        if school_level:
            query = query.filter(University.school_level.contains(school_level))
        if major_category:
            query = query.filter(Major.major_category == major_category)

        query = query.distinct()

        universities = query.limit(20).all()

        results = []
        for u in universities:
            info = {
                "id": u.id,
                "name": u.university_name,
                "province": u.province,
                "city": u.city,
                "type": u.school_type,
                "level": u.school_level,
            }

            if major_category:
                majors = (
                    self.db.query(Major)
                    .filter(
                        Major.university_id == u.id,
                        Major.major_category == major_category,
                    )
                    .all()
                )
                info["matching_majors"] = [
                    {"code": m.major_code, "name": m.major_name} for m in majors
                ]

            subject_rates = (
                self.db.query(SubjectLevelRate)
                .filter(SubjectLevelRate.university_id == u.id)
                .all()
            )
            info["subject_ratings"] = [
                {"subject": r.subject_name, "level": r.level_rate}
                for r in subject_rates
                if r.level_rate
            ]

            results.append(info)

        return results
