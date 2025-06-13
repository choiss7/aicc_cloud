# AI 챗봇/음성봇 개발 가이드

## 목차
1. [개요](#개요)
2. [개발 환경 설정](#개발-환경-설정)
3. [아키텍처 구조](#아키텍처-구조)
4. [핵심 모듈 개발](#핵심-모듈-개발)
5. [AWS 서비스 연동](#aws-서비스-연동)
6. [배포 및 운영](#배포-및-운영)
7. [테스트 가이드](#테스트-가이드)
8. [문제 해결](#문제-해결)

## 개요

### 프로젝트 목표
- AWS Connect 기반 클라우드 AICC 구축
- NLU, 시나리오, FAQ, 상담원 전환 기능 구현
- 확장 가능하고 유지보수가 용이한 아키텍처 설계

### 기술 스택
- **언어**: Python 3.9+
- **웹 프레임워크**: FastAPI
- **AWS 서비스**: Connect, Lex, Comprehend, Lambda, DynamoDB
- **데이터베이스**: DynamoDB, Redis
- **검색 엔진**: Elasticsearch
- **컨테이너**: Docker, ECS Fargate
- **모니터링**: CloudWatch, Prometheus

## 개발 환경 설정

### 1. 로컬 개발 환경

```bash
# Python 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집하여 AWS 자격 증명 및 설정 입력
```

### 2. AWS 자격 증명 설정

```bash
# AWS CLI 설치 및 설정
aws configure
# 또는 환경 변수로 설정
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=ap-northeast-2
```

### 3. 개발 도구 설정

```bash
# 코드 포맷팅
black src/
flake8 src/

# 타입 체크
mypy src/

# 테스트 실행
pytest tests/
```

## 아키텍처 구조

### 전체 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   사용자 채널    │    │   API Gateway   │    │   ECS Fargate   │
│  (웹, 모바일,   │────│                │────│   (챗봇 서비스)  │
│   전화, 채팅)   │    │                │    │                │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                       ┌─────────────────────────────────┼─────────────────────────────────┐
                       │                                 │                                 │
              ┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
              │   AWS Connect   │              │   AWS Lex V2    │              │ AWS Comprehend  │
              │  (음성 통화)     │              │  (대화 관리)     │              │  (감정/엔티티)   │
              └─────────────────┘              └─────────────────┘              └─────────────────┘
                       │                                 │                                 │
              ┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
              │   DynamoDB      │              │   Elasticsearch │              │     Redis       │
              │  (대화 이력)     │              │   (FAQ 검색)    │              │   (세션 캐시)    │
              └─────────────────┘              └─────────────────┘              └─────────────────┘
```

### 모듈 구조

```
src/
├── chatbot_nlu.py          # 자연어 이해 모듈
├── chatbot_scenario.py     # 시나리오 관리 모듈
├── chatbot_faq.py          # FAQ 관리 모듈
├── chatbot_escalation.py   # 상담원 전환 모듈
├── models/                 # 데이터 모델
│   ├── conversation.py
│   ├── user.py
│   └── agent.py
├── services/               # 비즈니스 로직
│   ├── conversation_service.py
│   ├── nlu_service.py
│   └── escalation_service.py
├── api/                    # API 엔드포인트
│   ├── chatbot_api.py
│   ├── admin_api.py
│   └── webhook_api.py
├── utils/                  # 유틸리티
│   ├── aws_client.py
│   ├── logger.py
│   └── config.py
└── tests/                  # 테스트 코드
    ├── test_nlu.py
    ├── test_scenario.py
    └── test_faq.py
```

## 핵심 모듈 개발

### 1. NLU (자연어 이해) 모듈

#### 주요 기능
- 의도 분류 (Intent Classification)
- 엔티티 추출 (Entity Extraction)
- 감정 분석 (Sentiment Analysis)

#### 구현 예시

```python
from chatbot_nlu import ChatbotNLU

# NLU 인스턴스 생성
nlu = ChatbotNLU(region_name='ap-northeast-2')

# 종합 분석
result = nlu.comprehensive_analysis(
    text="계좌 잔액을 확인하고 싶습니다",
    session_id="session_123",
    bot_id="your_lex_bot_id",
    bot_alias_id="your_lex_alias_id"
)

print(f"의도: {result['intent']['intent']}")
print(f"감정: {result['sentiment']['sentiment']}")
print(f"엔티티: {result['entities']}")
```

#### 커스터마이징 방법

```python
# 의도 매핑 확장
nlu.intent_mapping.update({
    'loan_inquiry': ['대출', '대출신청', '대출문의', '대출상품'],
    'card_application': ['카드신청', '카드발급', '신용카드', '체크카드']
})

# 엔티티 패턴 추가
nlu.entity_patterns.update({
    'account_number': r'(\d{3}-\d{2}-\d{6})',
    'card_number': r'(\d{4}-\d{4}-\d{4}-\d{4})'
})
```

### 2. 시나리오 관리 모듈

#### 주요 기능
- 대화 흐름 제어
- 상태 관리
- 단계별 검증

#### 시나리오 정의

```python
# 새로운 시나리오 추가
new_scenario = {
    "loan_application": {
        "name": "대출 신청",
        "steps": [
            {
                "id": "income_verification",
                "message": "연소득을 입력해 주세요.",
                "input_type": "number",
                "validation": "income_range",
                "next_step": "employment_info"
            },
            {
                "id": "employment_info",
                "message": "직업을 선택해 주세요.",
                "input_type": "selection",
                "options": ["회사원", "공무원", "자영업", "기타"],
                "next_step": "loan_amount"
            }
        ]
    }
}

# 시나리오 추가
scenario_manager.scenarios[ScenarioType.BANKING.value]["flows"].update(new_scenario)
```

#### 사용 예시

```python
from chatbot_scenario import ChatbotScenario, ScenarioType

# 시나리오 관리자 생성
scenario_manager = ChatbotScenario()

# 세션 생성
session_id = scenario_manager.create_session("user123", ScenarioType.BANKING.value)

# 플로우 시작
result = scenario_manager.start_flow(session_id, "loan_application")

# 사용자 입력 처리
result = scenario_manager.process_step(session_id, "5000")  # 연소득 5000만원
```

### 3. FAQ 관리 모듈

#### 주요 기능
- FAQ 검색 및 매칭
- 유사도 기반 검색
- Elasticsearch 연동

#### FAQ 추가

```python
from chatbot_faq import FAQManager

faq_manager = FAQManager(elasticsearch_host="your-es-host")

# 새 FAQ 추가
faq_id = faq_manager.add_faq(
    category="banking",
    question="인터넷뱅킹 비밀번호를 잊어버렸어요",
    answer="인터넷뱅킹 비밀번호 재설정은...",
    keywords=["비밀번호", "재설정", "인터넷뱅킹", "로그인"],
    priority=2
)
```

#### 검색 최적화

```python
# 검색 결과 개선을 위한 키워드 확장
def expand_query(query):
    synonyms = {
        "잔액": ["잔고", "금액", "돈"],
        "이체": ["송금", "계좌이체", "돈보내기"],
        "카드": ["신용카드", "체크카드", "카드"]
    }
    
    expanded_terms = [query]
    for word in query.split():
        if word in synonyms:
            expanded_terms.extend(synonyms[word])
    
    return " ".join(expanded_terms)

# 검색 시 사용
expanded_query = expand_query("계좌 잔액")
results = faq_manager.search_faq(expanded_query)
```

### 4. 상담원 전환 모듈

#### 에스컬레이션 조건 설정

```python
from chatbot_escalation import EscalationManager, EscalationReason, EscalationPriority

escalation_manager = EscalationManager()

# 커스텀 에스컬레이션 조건
def custom_escalation_check(session_data, user_input):
    # VIP 고객 즉시 전환
    if session_data.get('user_tier') == 'VIP':
        return True, EscalationReason.USER_REQUEST, EscalationPriority.URGENT
    
    # 특정 키워드 감지
    urgent_keywords = ['긴급', '응급', '사고', '분실']
    if any(keyword in user_input for keyword in urgent_keywords):
        return True, EscalationReason.COMPLEX_INQUIRY, EscalationPriority.HIGH
    
    return False, None, None

# 에스컬레이션 처리
should_escalate, reason, priority = custom_escalation_check(session_data, user_input)
if should_escalate:
    request_id = escalation_manager.create_escalation_request(
        session_id=session_id,
        user_id=user_id,
        reason=reason,
        priority=priority,
        description="사용자 요청에 의한 상담원 연결",
        context={"phone_number": "010-1234-5678"}
    )
```

## AWS 서비스 연동

### 1. Amazon Lex V2 연동

#### 봇 생성 및 설정

```python
import boto3

lex_client = boto3.client('lexv2-models', region_name='ap-northeast-2')

# 봇 생성
bot_response = lex_client.create_bot(
    botName='AICC-ChatBot',
    description='AICC 챗봇',
    roleArn='arn:aws:iam::account:role/LexServiceRole',
    dataPrivacy={'childDirected': False},
    idleSessionTTLInSeconds=300
)

# 인텐트 생성
intent_response = lex_client.create_intent(
    intentName='AccountInquiry',
    description='계좌 조회 인텐트',
    botId=bot_response['botId'],
    botVersion='DRAFT',
    localeId='ko_KR'
)
```

#### 슬롯 타입 정의

```python
# 슬롯 타입 생성
slot_type_response = lex_client.create_slot_type(
    slotTypeName='AccountType',
    description='계좌 유형',
    botId=bot_response['botId'],
    botVersion='DRAFT',
    localeId='ko_KR',
    slotTypeValues=[
        {'sampleValue': {'value': '예금계좌'}},
        {'sampleValue': {'value': '적금계좌'}},
        {'sampleValue': {'value': '대출계좌'}}
    ]
)
```

### 2. Amazon Connect 연동

#### Contact Flow 설정

```json
{
  "Version": "2019-10-30",
  "StartAction": "12345678-1234-1234-1234-123456789012",
  "Actions": [
    {
      "Identifier": "12345678-1234-1234-1234-123456789012",
      "Type": "MessageParticipant",
      "Parameters": {
        "Text": "안녕하세요. AICC 고객센터입니다."
      },
      "Transitions": {
        "NextAction": "23456789-2345-2345-2345-234567890123"
      }
    },
    {
      "Identifier": "23456789-2345-2345-2345-234567890123",
      "Type": "GetParticipantInput",
      "Parameters": {
        "Text": "무엇을 도와드릴까요?",
        "MaxDigits": 1,
        "Timeout": "8"
      },
      "Transitions": {
        "NextAction": "34567890-3456-3456-3456-345678901234",
        "Conditions": [],
        "Errors": []
      }
    }
  ]
}
```

#### Lambda 함수 연동

```python
import json
import boto3
from chatbot_nlu import ChatbotNLU

def lambda_handler(event, context):
    # Connect에서 전달된 이벤트 처리
    user_input = event['Details']['Parameters']['UserInput']
    session_id = event['Details']['ContactData']['ContactId']
    
    # NLU 분석
    nlu = ChatbotNLU()
    analysis_result = nlu.comprehensive_analysis(user_input)
    
    # 응답 생성
    response_text = nlu.get_response_template(
        analysis_result['intent']['intent'],
        analysis_result['sentiment']['sentiment']
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'response_text': response_text,
            'intent': analysis_result['intent']['intent'],
            'confidence': analysis_result['intent']['confidence']
        })
    }
```

### 3. DynamoDB 연동

#### 테이블 설계

```python
import boto3

dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')

# 대화 이력 테이블
conversation_table = dynamodb.create_table(
    TableName='ConversationHistory',
    KeySchema=[
        {'AttributeName': 'session_id', 'KeyType': 'HASH'},
        {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
    ],
    AttributeDefinitions=[
        {'AttributeName': 'session_id', 'AttributeType': 'S'},
        {'AttributeName': 'timestamp', 'AttributeType': 'S'},
        {'AttributeName': 'user_id', 'AttributeType': 'S'}
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'UserIndex',
            'KeySchema': [
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            'Projection': {'ProjectionType': 'ALL'},
            'BillingMode': 'PAY_PER_REQUEST'
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)
```

#### 데이터 저장 및 조회

```python
from datetime import datetime
import boto3

class ConversationRepository:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
        self.table = self.dynamodb.Table('ConversationHistory')
    
    def save_conversation(self, session_id, user_id, user_input, bot_response, metadata=None):
        item = {
            'session_id': session_id,
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_input': user_input,
            'bot_response': bot_response,
            'metadata': metadata or {}
        }
        
        self.table.put_item(Item=item)
    
    def get_conversation_history(self, session_id, limit=50):
        response = self.table.query(
            KeyConditionExpression='session_id = :session_id',
            ExpressionAttributeValues={':session_id': session_id},
            ScanIndexForward=False,  # 최신순 정렬
            Limit=limit
        )
        
        return response['Items']
```

## 배포 및 운영

### 1. Docker 컨테이너 빌드

```bash
# 이미지 빌드
docker build -t aicc-chatbot:latest .

# 로컬 테스트
docker run -p 8000:8000 -e AWS_ACCESS_KEY_ID=your_key aicc-chatbot:latest
```

### 2. ECS 배포

```bash
# 배포 스크립트 실행
chmod +x deploy_chatbot.sh
./deploy_chatbot.sh

# 특정 환경으로 배포
PROJECT_NAME=aicc-prod AWS_REGION=ap-northeast-2 ./deploy_chatbot.sh
```

### 3. 모니터링 설정

#### CloudWatch 메트릭

```python
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch', region_name='ap-northeast-2')

def put_custom_metric(metric_name, value, unit='Count', namespace='AICC/Chatbot'):
    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.now()
            }
        ]
    )

# 사용 예시
put_custom_metric('ConversationCount', 1)
put_custom_metric('EscalationRate', 0.15, 'Percent')
```

#### 로그 설정

```python
import structlog
import logging

# 구조화된 로깅 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# 사용 예시
logger.info("대화 시작", session_id="session_123", user_id="user456")
logger.error("NLU 분석 실패", error="API timeout", session_id="session_123")
```

## 테스트 가이드

### 1. 단위 테스트

```python
import pytest
from chatbot_nlu import ChatbotNLU

class TestChatbotNLU:
    def setup_method(self):
        self.nlu = ChatbotNLU()
    
    def test_intent_classification(self):
        result = self.nlu.classify_intent("계좌 잔액을 확인하고 싶습니다")
        assert result['intent'] == 'inquiry'
        assert result['confidence'] > 0.5
    
    def test_sentiment_analysis(self):
        result = self.nlu.analyze_sentiment("정말 화가 납니다")
        assert result['sentiment'] == 'NEGATIVE'
    
    def test_entity_extraction(self):
        result = self.nlu.extract_entities("010-1234-5678로 연락주세요")
        assert 'phone' in result
        assert '010-1234-5678' in result['phone']
```

### 2. 통합 테스트

```python
import pytest
from chatbot_scenario import ChatbotScenario, ScenarioType

class TestScenarioIntegration:
    def setup_method(self):
        self.scenario_manager = ChatbotScenario()
    
    def test_complete_flow(self):
        # 세션 생성
        session_id = self.scenario_manager.create_session("test_user", ScenarioType.BANKING.value)
        
        # 플로우 시작
        result = self.scenario_manager.start_flow(session_id, "account_inquiry")
        assert result['step_id'] == 'auth_request'
        
        # 단계별 진행
        result = self.scenario_manager.process_step(session_id, "1234567")
        assert result['step_id'] == 'account_select'
        
        result = self.scenario_manager.process_step(session_id, "예금계좌")
        assert result['step_id'] == 'show_balance'
```

### 3. 성능 테스트

```python
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

async def performance_test():
    nlu = ChatbotNLU()
    
    test_inputs = [
        "계좌 잔액을 확인하고 싶습니다",
        "카드를 분실했어요",
        "대출 신청하고 싶습니다"
    ] * 100
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(nlu.comprehensive_analysis, text)
            for text in test_inputs
        ]
        
        results = [future.result() for future in futures]
    
    end_time = time.time()
    
    print(f"처리 시간: {end_time - start_time:.2f}초")
    print(f"초당 처리량: {len(test_inputs) / (end_time - start_time):.2f} requests/sec")

# 실행
asyncio.run(performance_test())
```

## 문제 해결

### 1. 일반적인 문제

#### AWS 자격 증명 오류
```bash
# 자격 증명 확인
aws sts get-caller-identity

# 권한 확인
aws iam get-user
aws iam list-attached-user-policies --user-name your-username
```

#### 메모리 부족 오류
```python
# 메모리 사용량 모니터링
import psutil
import gc

def monitor_memory():
    process = psutil.Process()
    memory_info = process.memory_info()
    print(f"RSS: {memory_info.rss / 1024 / 1024:.2f} MB")
    print(f"VMS: {memory_info.vms / 1024 / 1024:.2f} MB")

# 메모리 정리
gc.collect()
```

#### API 응답 시간 최적화
```python
import asyncio
import aiohttp

class AsyncNLU:
    async def analyze_batch(self, texts):
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.analyze_single(session, text)
                for text in texts
            ]
            return await asyncio.gather(*tasks)
    
    async def analyze_single(self, session, text):
        # 비동기 분석 로직
        pass
```

### 2. 디버깅 도구

#### 로그 분석
```bash
# CloudWatch 로그 조회
aws logs filter-log-events \
    --log-group-name "/ecs/aicc-chatbot" \
    --start-time 1640995200000 \
    --filter-pattern "ERROR"

# 실시간 로그 스트리밍
aws logs tail "/ecs/aicc-chatbot" --follow
```

#### 성능 프로파일링
```python
import cProfile
import pstats

def profile_function(func, *args, **kwargs):
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = func(*args, **kwargs)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    
    return result

# 사용 예시
result = profile_function(nlu.comprehensive_analysis, "테스트 텍스트")
```

### 3. 운영 체크리스트

#### 배포 전 확인사항
- [ ] 모든 테스트 통과
- [ ] 환경 변수 설정 확인
- [ ] AWS 권한 설정 확인
- [ ] 데이터베이스 연결 테스트
- [ ] 로드 밸런서 헬스체크 설정
- [ ] 모니터링 알람 설정

#### 배포 후 확인사항
- [ ] 서비스 정상 동작 확인
- [ ] 로그 정상 출력 확인
- [ ] 메트릭 수집 확인
- [ ] 에러율 모니터링
- [ ] 응답 시간 모니터링

## 참고 자료

### AWS 문서
- [Amazon Lex V2 Developer Guide](https://docs.aws.amazon.com/lexv2/)
- [Amazon Connect Administrator Guide](https://docs.aws.amazon.com/connect/)
- [Amazon Comprehend Developer Guide](https://docs.aws.amazon.com/comprehend/)

### 개발 도구
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Elasticsearch Python Client](https://elasticsearch-py.readthedocs.io/)

### 모니터링
- [CloudWatch User Guide](https://docs.aws.amazon.com/cloudwatch/)
- [Prometheus Documentation](https://prometheus.io/docs/)

---

이 가이드는 AI 챗봇/음성봇 개발의 전체 과정을 다루며, 실제 개발 시 참고할 수 있는 구체적인 예시와 해결 방법을 제공합니다. 