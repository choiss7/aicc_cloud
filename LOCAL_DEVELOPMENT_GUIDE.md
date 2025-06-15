# 🚀 AICC Cloud 로컬 개발환경 가이드

## 📋 개요

이 가이드는 AWS Connect 기반 AICC(AI Contact Center) 시스템을 로컬 개발환경에서 테스트하고 개발하는 방법을 설명합니다.

## 🏗️ 프로젝트 구조

```
aicc_cloud/
├── src/                          # 소스 코드
│   ├── handlers/                 # Lambda 핸들러
│   │   ├── __init__.py
│   │   └── chatbot_handler.py    # 메인 챗봇 핸들러
│   ├── services/                 # 비즈니스 로직
│   ├── api/                      # API 엔드포인트
│   └── utils/                    # 유틸리티
├── tests/                        # 테스트 코드
│   ├── __init__.py
│   ├── test_chatbot_handler.py   # 핸들러 테스트
│   └── performance/              # 성능 테스트
├── connect/                      # AWS Connect 설정
├── .github/                      # CI/CD 워크플로
├── env.local                     # 로컬 환경 변수
├── env.sample                    # 환경 변수 템플릿
├── pytest.ini                   # pytest 설정
├── run_local_test.py            # 로컬 테스트 스크립트
└── requirements-fixed.txt        # 수정된 의존성
```

## 🛠️ 로컬 개발환경 설정

### 1. 환경 변수 설정

```bash
# env.local 파일을 복사하여 실제 값으로 수정
cp env.sample .env
```

**주요 환경 변수:**
- `ENVIRONMENT=development` - 개발 모드 활성화
- `APP_DEBUG=true` - 디버그 로깅 활성화
- `AWS_REGION=ap-northeast-2` - AWS 리전
- `BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0` - Bedrock 모델

### 2. 의존성 설치

```bash
# 수정된 의존성 파일 사용
pip install -r requirements-fixed.txt

# 개발용 의존성 추가 설치
pip install -r requirements-dev.txt
```

### 3. 로컬 테스트 실행

```bash
# 직접 테스트 스크립트 실행
python run_local_test.py

# pytest를 사용한 정식 테스트
python -m pytest tests/test_chatbot_handler.py -v

# 특정 테스트만 실행
python -m pytest tests/test_chatbot_handler.py::TestChatbotHandler::test_greeting_message -v
```

## 🎯 핵심 기능

### 1. Lambda 핸들러 (`src/handlers/chatbot_handler.py`)

**주요 클래스:**
- `ChatbotHandler`: 메인 챗봇 처리 클래스
- `lambda_handler`: AWS Lambda 진입점 함수

**지원하는 요청 타입:**
- `chat`: 채팅 메시지 처리
- `escalation`: 상담원 에스컬레이션

**예시 사용법:**
```python
from src.handlers.chatbot_handler import ChatbotHandler

handler = ChatbotHandler()
result = handler.process_chat_message("안녕하세요", "session_123")
print(result['response_text'])
```

### 2. 의도 분석 (NLU)

**지원하는 의도:**
- `greeting`: 인사 ("안녕하세요", "hello")
- `product_inquiry`: 상품 문의 ("상품", "가격")
- `complaint`: 불만 ("불만", "별로", "문제")
- `reservation`: 예약 ("예약", "reservation")
- `general_inquiry`: 일반 문의 (기타)

### 3. 환경별 동작

**개발 환경 (`ENVIRONMENT=development`):**
- AWS 서비스 모킹 사용
- 빠른 응답 시간
- 상세한 디버그 로깅

**프로덕션 환경 (`ENVIRONMENT=production`):**
- 실제 AWS 서비스 사용
- Bedrock Claude 3 NLU
- DynamoDB 대화 저장

## 🧪 테스트 가이드

### 1. 테스트 구조

```
tests/
├── test_chatbot_handler.py       # 메인 테스트 파일
│   ├── TestChatbotHandler        # 핸들러 단위 테스트
│   ├── TestLambdaHandler         # Lambda 함수 테스트
│   ├── TestAWSIntegration        # AWS 통합 테스트
│   ├── TestPerformance           # 성능 테스트
│   └── TestIntegration           # 통합 테스트
└── performance/                  # 성능 테스트 설정
```

### 2. 테스트 실행 방법

```bash
# 전체 테스트 실행
python -m pytest tests/ -v

# 특정 클래스 테스트
python -m pytest tests/test_chatbot_handler.py::TestChatbotHandler -v

# 성능 테스트만 실행
python -m pytest tests/test_chatbot_handler.py::TestPerformance -v

# 커버리지 포함 테스트
python -m pytest tests/ --cov=src --cov-report=html
```

### 3. 테스트 마커

```bash
# 단위 테스트만 실행
python -m pytest -m unit

# 통합 테스트만 실행
python -m pytest -m integration

# 느린 테스트 제외
python -m pytest -m "not slow"
```

## 🔧 개발 워크플로

### 1. 새로운 기능 개발

```bash
# 1. 기능 브랜치 생성
git checkout -b feature/new-feature

# 2. 코드 작성
# src/handlers/chatbot_handler.py 수정

# 3. 테스트 작성
# tests/test_chatbot_handler.py에 테스트 추가

# 4. 로컬 테스트 실행
python run_local_test.py
python -m pytest tests/ -v

# 5. 커밋 및 푸시
git add .
git commit -m "feat: 새로운 기능 추가"
git push origin feature/new-feature
```

### 2. 디버깅

```python
# 로깅 레벨 조정
import logging
logging.basicConfig(level=logging.DEBUG)

# 환경 변수 확인
import os
print(f"Environment: {os.getenv('ENVIRONMENT')}")
print(f"Debug: {os.getenv('APP_DEBUG')}")

# 핸들러 직접 테스트
from src.handlers.chatbot_handler import ChatbotHandler
handler = ChatbotHandler()
result = handler.process_chat_message("테스트 메시지", "debug_session")
print(result)
```

## 📊 성능 최적화

### 1. 응답 시간 목표

- **단일 요청**: < 1초
- **동시 요청 (10개)**: < 10초
- **평균 응답 시간**: < 0.1초

### 2. 성능 모니터링

```python
# 성능 테스트 실행
python -m pytest tests/test_chatbot_handler.py::TestPerformance -v

# 응답 시간 측정
import time
start = time.time()
result = handler.process_chat_message("테스트", "session")
print(f"응답 시간: {time.time() - start:.3f}초")
```

## 🚨 문제 해결

### 1. 일반적인 문제

**Import 오류:**
```bash
# Python 경로 확인
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**환경 변수 로드 실패:**
```python
# 환경 변수 파일 확인
from dotenv import load_dotenv
load_dotenv('env.local')
```

**AWS 서비스 연결 실패:**
```python
# 개발 모드로 강제 설정
os.environ['ENVIRONMENT'] = 'development'
```

### 2. 로그 확인

```python
# 상세 로깅 활성화
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## 🔄 CI/CD 통합

### 1. GitHub Actions

프로젝트는 `.github/workflows/ci-cd.yml`에 정의된 자동화 파이프라인을 사용합니다:

- **코드 품질 검사**: flake8, black, mypy
- **보안 스캔**: bandit
- **테스트 실행**: pytest with coverage
- **성능 테스트**: Artillery 기반
- **자동 배포**: AWS Lambda

### 2. 로컬에서 CI 시뮬레이션

```bash
# 코드 품질 검사
flake8 src/ tests/
black --check src/ tests/
mypy src/

# 보안 스캔
bandit -r src/

# 테스트 및 커버리지
python -m pytest tests/ --cov=src --cov-report=term-missing
```

## 📚 추가 리소스

- **AWS Connect 문서**: [AWS Connect Developer Guide](https://docs.aws.amazon.com/connect/)
- **Bedrock 문서**: [AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- **pytest 문서**: [pytest Documentation](https://docs.pytest.org/)

## 🤝 기여 가이드

1. **이슈 생성**: 버그 리포트 또는 기능 요청
2. **포크 및 브랜치**: 개발용 브랜치 생성
3. **코드 작성**: 테스트 포함 개발
4. **테스트 실행**: 모든 테스트 통과 확인
5. **PR 생성**: 상세한 설명과 함께 제출

---

**📞 문의사항이 있으시면 개발팀에 연락해주세요!** 