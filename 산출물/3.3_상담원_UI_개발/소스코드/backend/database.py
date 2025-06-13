from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
from typing import Generator

# 환경 변수에서 데이터베이스 URL 가져오기
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/agent_desktop_db"
)

# SQLAlchemy 엔진 생성
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False  # 프로덕션에서는 False로 설정
)

# 세션 팩토리 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스 생성
Base = declarative_base()

def get_db() -> Generator:
    """
    데이터베이스 세션 의존성
    FastAPI의 Depends와 함께 사용
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """
    모든 테이블 생성
    """
    Base.metadata.create_all(bind=engine)

def drop_tables():
    """
    모든 테이블 삭제 (개발/테스트 환경에서만 사용)
    """
    Base.metadata.drop_all(bind=engine) 