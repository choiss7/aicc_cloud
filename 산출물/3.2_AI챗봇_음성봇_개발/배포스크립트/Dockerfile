# AI 챗봇 Dockerfile
# Python 3.9 기반 이미지 사용
FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 코드 복사
COPY 소스코드/ ./src/
COPY app.py .
COPY config/ ./config/

# 환경 변수 설정
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV AWS_DEFAULT_REGION=ap-northeast-2

# 포트 노출
EXPOSE 8000

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 비루트 사용자 생성 및 설정
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# 애플리케이션 실행
CMD ["python", "app.py"] 