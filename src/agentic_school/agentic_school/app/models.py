from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, DECIMAL
from sqlalchemy.sql import func
from app.database import Base


class University(Base):
    __tablename__ = "universities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    candidate_school_id = Column(BigInteger, unique=True, nullable=True)
    university_name = Column(String(100), nullable=False, unique=True)
    province = Column(String(50), nullable=False)
    city = Column(String(50), nullable=False)
    province_area = Column(String(20), nullable=False)
    school_type = Column(String(50), nullable=True)
    school_org_type = Column(String(50), nullable=True)
    school_level = Column(String(100), nullable=True)
    coverage_priority = Column(String(10), nullable=False, default="P2")
    official_site = Column(String(500), nullable=True)
    candidate_source_url = Column(String(500), nullable=True)
    recruit_number_reference = Column(Integer, nullable=True)
    major_number_reference = Column(Integer, nullable=True)
    crawler_run_id = Column(BigInteger, nullable=True)
    candidate_crawled_at = Column(DateTime, nullable=True)
    official_verified_status = Column(String(30), nullable=False, default="pending")
    remark = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class Department(Base):
    __tablename__ = "departments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    university_id = Column(BigInteger, nullable=False)
    department_name = Column(String(150), nullable=False)
    standard_name = Column(String(150), nullable=True)
    source_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class Major(Base):
    __tablename__ = "majors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    university_id = Column(BigInteger, nullable=False)
    department_id = Column(BigInteger, nullable=False)
    major_code = Column(String(20), nullable=False)
    major_name = Column(String(150), nullable=False)
    major_category = Column(String(200), nullable=True)
    degree_type = Column(String(20), nullable=True)
    study_mode = Column(String(20), nullable=True)
    research_direction = Column(String(300), nullable=True)
    exam_subjects = Column(String(500), nullable=True)
    source_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class ScoreLine(Base):
    __tablename__ = "score_lines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    line_type = Column(String(30), nullable=False)
    university_id = Column(BigInteger, nullable=True)
    department_id = Column(BigInteger, nullable=True)
    major_id = Column(BigInteger, nullable=True)
    major_category = Column(String(200), nullable=True)
    university_id_key = Column(BigInteger, nullable=False, default=0)
    major_id_key = Column(BigInteger, nullable=False, default=0)
    major_category_key = Column(String(200), nullable=False, default="")
    total_score_line = Column(Integer, nullable=False)
    politics_line = Column(Integer, nullable=True)
    english_line = Column(Integer, nullable=True)
    subject_one_line = Column(Integer, nullable=True)
    subject_two_line = Column(Integer, nullable=True)
    score_diff_to_national = Column(Integer, nullable=True)
    source_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class SubjectLevelRate(Base):
    __tablename__ = "subject_level_rates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    university_id = Column(BigInteger, nullable=False)
    subject_code = Column(String(20), nullable=False)
    subject_name = Column(String(150), nullable=False)
    degree_type = Column(String(20), nullable=True)
    level_rate = Column(String(10), nullable=True)
    rate_sort = Column(Integer, nullable=True)
    has_doctor = Column(Integer, nullable=True)
    candidate_school_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
