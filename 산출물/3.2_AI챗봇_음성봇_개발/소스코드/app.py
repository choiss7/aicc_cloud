"""
AI 챗봇 메인 애플리케이션
FastAPI 기반 웹 서비스
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import uvicorn
import logging
import structlog
from datetime import datetime
import os

# 로컬 모듈 임포트
from chatbot_nlu import ChatbotNLU
from chatbot_scenario import ChatbotScenario, ScenarioType
from chatbot_faq import FAQManager
from chatbot_escalation import EscalationManager, EscalationReason, EscalationPriority

# 로깅 설정
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

# FastAPI 앱 생성
app = FastAPI(
    title="AICC 챗봇 API",
    description="AWS Connect 기반 AI 챗봇 서비스",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 인스턴스
nlu_service = None
scenario_manager = None
faq_manager = None
escalation_manager = None

# Pydantic 모델 정의
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: str
    context: Optional[Dict[str, Any]] = {}

class ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    entities: Optional[Dict] = {}
    next_action: Optional[str] = None
    escalation_required: bool = False

class FAQSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    limit: int = 5

class EscalationRequest(BaseModel):
    session_id: str
    user_id: str
    reason: str
    description: str
    priority: int = 2

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    services: Dict[str, str]

# 의존성 주입
def get_nlu_service():
    global nlu_service
    if nlu_service is None:
        nlu_service = ChatbotNLU()
    return nlu_service

def get_scenario_manager():
    global scenario_manager
    if scenario_manager is None:
        scenario_manager = ChatbotScenario()
    return scenario_manager

def get_faq_manager():
    global faq_manager
    if faq_manager is None:
        elasticsearch_host = os.getenv('ELASTICSEARCH_HOST')
        faq_manager = FAQManager(elasticsearch_host=elasticsearch_host)
    return faq_manager

def get_escalation_manager():
    global escalation_manager
    if escalation_manager is None:
        escalation_manager = EscalationManager()
    return escalation_manager

# 헬스체크 엔드포인트
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """서비스 헬스체크"""
    try:
        # 각 서비스 상태 확인
        services_status = {
            "nlu": "healthy",
            "scenario": "healthy",
            "faq": "healthy",
            "escalation": "healthy"
        }
        
        # AWS 서비스 연결 확인 (간단한 체크)
        try:
            nlu = get_nlu_service()
            # 간단한 테스트 수행
            test_result = nlu.classify_intent("테스트")
            if test_result:
                services_status["aws_comprehend"] = "healthy"
            else:
                services_status["aws_comprehend"] = "degraded"
        except Exception as e:
            services_status["aws_comprehend"] = "unhealthy"
            logger.warning("AWS Comprehend 연결 실패", error=str(e))
        
        return HealthResponse(
            status="healthy",
            timestamp=datetime.now().isoformat(),
            version="1.0.0",
            services=services_status
        )
    
    except Exception as e:
        logger.error("헬스체크 실패", error=str(e))
        raise HTTPException(status_code=503, detail="Service Unavailable")

# 메인 챗봇 엔드포인트
@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    nlu: ChatbotNLU = Depends(get_nlu_service),
    scenario: ChatbotScenario = Depends(get_scenario_manager),
    faq: FAQManager = Depends(get_faq_manager),
    escalation: EscalationManager = Depends(get_escalation_manager)
):
    """메인 챗봇 대화 처리"""
    
    logger.info("챗봇 요청 수신", 
                user_id=request.user_id, 
                session_id=request.session_id,
                message_length=len(request.message))
    
    try:
        # 세션 ID 생성 또는 기존 세션 사용
        session_id = request.session_id
        if not session_id:
            session_id = scenario.create_session(request.user_id, ScenarioType.GENERAL.value)
        
        # NLU 분석
        nlu_result = nlu.comprehensive_analysis(request.message)
        intent = nlu_result['intent']['intent']
        confidence = nlu_result['intent']['confidence']
        sentiment = nlu_result['sentiment']['sentiment']
        entities = nlu_result['entities']
        
        logger.info("NLU 분석 완료",
                   session_id=session_id,
                   intent=intent,
                   confidence=confidence,
                   sentiment=sentiment)
        
        # 에스컬레이션 필요 여부 확인
        session_data = scenario.get_session(session_id)
        if session_data:
            session_data.update({
                'sentiment': nlu_result['sentiment'],
                'last_message': request.message
            })
        
        should_escalate, escalation_reason, escalation_priority = escalation.should_escalate(
            session_data or {}, request.message
        )
        
        response_text = ""
        next_action = None
        escalation_required = False
        
        if should_escalate:
            # 에스컬레이션 처리
            escalation_id = escalation.create_escalation_request(
                session_id=session_id,
                user_id=request.user_id,
                reason=escalation_reason,
                priority=escalation_priority,
                description=f"사용자 메시지: {request.message}",
                context=request.context
            )
            
            response_text = "상담원 연결을 준비하고 있습니다. 잠시만 기다려 주세요."
            next_action = "escalation"
            escalation_required = True
            
            # 백그라운드에서 상담원 배정
            background_tasks.add_task(escalation.assign_agent, escalation_id)
            
            logger.info("에스컬레이션 요청 생성",
                       session_id=session_id,
                       escalation_id=escalation_id,
                       reason=escalation_reason.value)
        
        elif intent == 'inquiry' or confidence < 0.5:
            # FAQ 검색
            faq_results = faq.search_faq(request.message, limit=3)
            
            if faq_results and faq_results[0].get('score', 0) > 0.3:
                best_faq = faq_results[0]
                response_text = best_faq['answer']
                next_action = "faq_provided"
                
                logger.info("FAQ 응답 제공",
                           session_id=session_id,
                           faq_id=best_faq['id'],
                           score=best_faq.get('score', 0))
            else:
                # 시나리오 기반 응답
                response_text = nlu.get_response_template(intent, sentiment)
                next_action = "general_response"
        
        else:
            # 의도 기반 시나리오 처리
            if intent == 'greeting':
                response_text = nlu.get_response_template(intent, sentiment)
                next_action = "greeting_completed"
            
            elif intent in ['request', 'complaint']:
                # 특정 플로우 시작 가능
                available_flows = scenario.get_available_flows(ScenarioType.GENERAL.value)
                if available_flows:
                    flow_result = scenario.start_flow(session_id, available_flows[0]['id'])
                    response_text = flow_result.get('message', nlu.get_response_template(intent, sentiment))
                    next_action = "flow_started"
                else:
                    response_text = nlu.get_response_template(intent, sentiment)
                    next_action = "general_response"
            
            else:
                response_text = nlu.get_response_template(intent, sentiment)
                next_action = "general_response"
        
        # 대화 이력 저장 (백그라운드)
        background_tasks.add_task(
            save_conversation_history,
            session_id,
            request.user_id,
            request.message,
            response_text,
            {
                'intent': intent,
                'confidence': confidence,
                'sentiment': sentiment,
                'entities': entities,
                'escalation_required': escalation_required
            }
        )
        
        return ChatResponse(
            response=response_text,
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            entities=entities,
            next_action=next_action,
            escalation_required=escalation_required
        )
    
    except Exception as e:
        logger.error("챗봇 처리 오류",
                    session_id=request.session_id,
                    user_id=request.user_id,
                    error=str(e))
        
        raise HTTPException(
            status_code=500,
            detail="챗봇 서비스 처리 중 오류가 발생했습니다."
        )

# FAQ 검색 엔드포인트
@app.post("/faq/search")
async def search_faq(
    request: FAQSearchRequest,
    faq: FAQManager = Depends(get_faq_manager)
):
    """FAQ 검색"""
    
    try:
        results = faq.search_faq(
            query=request.query,
            category=request.category,
            limit=request.limit
        )
        
        logger.info("FAQ 검색 완료",
                   query=request.query,
                   category=request.category,
                   result_count=len(results))
        
        return {
            "query": request.query,
            "results": results,
            "total": len(results)
        }
    
    except Exception as e:
        logger.error("FAQ 검색 오류", query=request.query, error=str(e))
        raise HTTPException(status_code=500, detail="FAQ 검색 중 오류가 발생했습니다.")

# 시나리오 플로우 처리 엔드포인트
@app.post("/scenario/{session_id}/step")
async def process_scenario_step(
    session_id: str,
    user_input: str,
    scenario: ChatbotScenario = Depends(get_scenario_manager)
):
    """시나리오 단계 처리"""
    
    try:
        result = scenario.process_step(session_id, user_input)
        
        logger.info("시나리오 단계 처리",
                   session_id=session_id,
                   user_input=user_input,
                   completed=result.get('completed', False))
        
        return result
    
    except Exception as e:
        logger.error("시나리오 처리 오류",
                    session_id=session_id,
                    error=str(e))
        raise HTTPException(status_code=500, detail="시나리오 처리 중 오류가 발생했습니다.")

# 에스컬레이션 상태 조회
@app.get("/escalation/status")
async def get_escalation_status(
    escalation: EscalationManager = Depends(get_escalation_manager)
):
    """에스컬레이션 큐 상태 조회"""
    
    try:
        status = escalation.get_queue_status()
        return status
    
    except Exception as e:
        logger.error("에스컬레이션 상태 조회 오류", error=str(e))
        raise HTTPException(status_code=500, detail="상태 조회 중 오류가 발생했습니다.")

# 관리자 API - FAQ 관리
@app.post("/admin/faq")
async def create_faq(
    category: str,
    question: str,
    answer: str,
    keywords: List[str],
    priority: int = 5,
    faq: FAQManager = Depends(get_faq_manager)
):
    """FAQ 생성 (관리자용)"""
    
    try:
        faq_id = faq.add_faq(
            category=category,
            question=question,
            answer=answer,
            keywords=keywords,
            priority=priority
        )
        
        logger.info("FAQ 생성 완료", faq_id=faq_id, category=category)
        
        return {"faq_id": faq_id, "status": "created"}
    
    except Exception as e:
        logger.error("FAQ 생성 오류", error=str(e))
        raise HTTPException(status_code=500, detail="FAQ 생성 중 오류가 발생했습니다.")

# 웹훅 엔드포인트 (AWS Connect용)
@app.post("/webhook/connect")
async def connect_webhook(
    contact_data: Dict[str, Any],
    nlu: ChatbotNLU = Depends(get_nlu_service)
):
    """AWS Connect 웹훅 처리"""
    
    try:
        # Connect에서 전달된 데이터 처리
        user_input = contact_data.get('Details', {}).get('Parameters', {}).get('UserInput', '')
        contact_id = contact_data.get('Details', {}).get('ContactData', {}).get('ContactId', '')
        
        if not user_input:
            return {"response": "입력을 이해할 수 없습니다. 다시 말씀해 주세요."}
        
        # NLU 분석
        analysis_result = nlu.comprehensive_analysis(user_input)
        
        # 응답 생성
        response_text = nlu.get_response_template(
            analysis_result['intent']['intent'],
            analysis_result['sentiment']['sentiment']
        )
        
        logger.info("Connect 웹훅 처리",
                   contact_id=contact_id,
                   intent=analysis_result['intent']['intent'])
        
        return {
            "response": response_text,
            "intent": analysis_result['intent']['intent'],
            "confidence": analysis_result['intent']['confidence']
        }
    
    except Exception as e:
        logger.error("Connect 웹훅 처리 오류", error=str(e))
        return {"response": "시스템 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."}

# 백그라운드 태스크
async def save_conversation_history(
    session_id: str,
    user_id: str,
    user_message: str,
    bot_response: str,
    metadata: Dict[str, Any]
):
    """대화 이력 저장"""
    
    try:
        # 실제 구현에서는 DynamoDB에 저장
        logger.info("대화 이력 저장",
                   session_id=session_id,
                   user_id=user_id,
                   metadata=metadata)
        
        # TODO: DynamoDB 저장 로직 구현
        
    except Exception as e:
        logger.error("대화 이력 저장 실패",
                    session_id=session_id,
                    error=str(e))

# 애플리케이션 시작 이벤트
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    logger.info("AICC 챗봇 서비스 시작")
    
    # 서비스 초기화
    get_nlu_service()
    get_scenario_manager()
    get_faq_manager()
    get_escalation_manager()
    
    logger.info("모든 서비스 초기화 완료")

# 애플리케이션 종료 이벤트
@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리"""
    logger.info("AICC 챗봇 서비스 종료")

# 메인 실행
if __name__ == "__main__":
    # 환경 변수에서 설정 읽기
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    # 서버 실행
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    ) 