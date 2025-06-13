from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
import asyncio
import json
import logging
from datetime import datetime, timedelta
import uuid

from database import get_db, engine
from models import Base, Agent, Customer, ChatSession, Message, Call, CustomerInteraction
from schemas import (
    AgentCreate, AgentResponse, AgentLogin, AgentStatusUpdate,
    CustomerResponse, CustomerCreate, CustomerUpdate, CustomerSearch,
    ChatSessionResponse, ChatSessionCreate, MessageCreate, MessageResponse,
    CallResponse, CallCreate, CallUpdate,
    CustomerInteractionResponse, CustomerInteractionCreate
)
from auth import create_access_token, verify_token, get_current_agent
from websocket_manager import ConnectionManager
import crud

# 데이터베이스 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="상담원 데스크탑 API",
    description="AWS Connect 기반 콜센터 상담원 UI API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 보안 설정
security = HTTPBearer()

# WebSocket 연결 관리자
manager = ConnectionManager()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def root():
    return {"message": "상담원 데스크탑 API 서버가 실행 중입니다."}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

# 인증 관련 엔드포인트
@app.post("/auth/login", response_model=dict)
async def login(agent_login: AgentLogin, db: Session = Depends(get_db)):
    """상담원 로그인"""
    agent = crud.authenticate_agent(db, agent_login.username, agent_login.password)
    if not agent:
        raise HTTPException(status_code=401, detail="잘못된 사용자명 또는 비밀번호")
    
    access_token = create_access_token(data={"sub": agent.username})
    
    # 상담원 상태를 'available'로 업데이트
    crud.update_agent_status(db, agent.id, "available")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": agent.id,
            "username": agent.username,
            "email": agent.email,
            "role": agent.role,
            "department": agent.department,
            "status": "available"
        }
    }

@app.post("/auth/logout")
async def logout(current_agent: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    """상담원 로그아웃"""
    crud.update_agent_status(db, current_agent.id, "offline")
    return {"message": "로그아웃되었습니다."}

@app.put("/auth/status")
async def update_status(
    status_update: AgentStatusUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """상담원 상태 업데이트"""
    crud.update_agent_status(db, current_agent.id, status_update.status)
    return {"message": "상태가 업데이트되었습니다.", "status": status_update.status}

# 고객 관련 엔드포인트
@app.get("/customers/search", response_model=List[CustomerResponse])
async def search_customers(
    query: str,
    limit: int = 10,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """고객 검색"""
    customers = crud.search_customers(db, query, limit)
    return customers

@app.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """고객 정보 조회"""
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return customer

@app.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_update: CustomerUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """고객 정보 업데이트"""
    customer = crud.update_customer(db, customer_id, customer_update)
    if not customer:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return customer

@app.get("/customers/{customer_id}/history", response_model=List[CustomerInteractionResponse])
async def get_customer_history(
    customer_id: str,
    limit: int = 50,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """고객 상담 이력 조회"""
    history = crud.get_customer_interactions(db, customer_id, limit)
    return history

# 채팅 관련 엔드포인트
@app.get("/chat/sessions", response_model=List[ChatSessionResponse])
async def get_chat_sessions(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """활성 채팅 세션 목록 조회"""
    sessions = crud.get_active_chat_sessions(db, current_agent.id)
    return sessions

@app.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """특정 채팅 세션 조회"""
    session = crud.get_chat_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다.")
    return session

@app.post("/chat/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: str,
    message: MessageCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """메시지 전송"""
    # 메시지 저장
    new_message = crud.create_message(db, session_id, current_agent.id, message)
    
    # WebSocket을 통해 실시간 전송
    await manager.broadcast_to_session(session_id, {
        "type": "message",
        "data": {
            "id": new_message.id,
            "session_id": session_id,
            "sender": "agent",
            "content": new_message.content,
            "timestamp": new_message.created_at.isoformat(),
            "type": new_message.message_type
        }
    })
    
    return new_message

@app.put("/chat/sessions/{session_id}/status")
async def update_chat_session_status(
    session_id: str,
    status: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """채팅 세션 상태 업데이트"""
    session = crud.update_chat_session_status(db, session_id, status)
    if not session:
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다.")
    
    # WebSocket을 통해 상태 변경 알림
    await manager.broadcast_to_session(session_id, {
        "type": "session_status_update",
        "data": {"session_id": session_id, "status": status}
    })
    
    return {"message": "세션 상태가 업데이트되었습니다.", "status": status}

# 통화 관련 엔드포인트
@app.get("/calls/history", response_model=List[CallResponse])
async def get_call_history(
    limit: int = 50,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """통화 이력 조회"""
    calls = crud.get_agent_call_history(db, current_agent.id, limit)
    return calls

@app.post("/calls", response_model=CallResponse)
async def create_call(
    call: CallCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """새 통화 생성"""
    new_call = crud.create_call(db, current_agent.id, call)
    return new_call

@app.put("/calls/{call_id}", response_model=CallResponse)
async def update_call(
    call_id: str,
    call_update: CallUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """통화 정보 업데이트"""
    call = crud.update_call(db, call_id, call_update)
    if not call:
        raise HTTPException(status_code=404, detail="통화를 찾을 수 없습니다.")
    return call

# 상담 이력 관련 엔드포인트
@app.get("/interactions", response_model=List[CustomerInteractionResponse])
async def get_interactions(
    limit: int = 50,
    customer_id: Optional[str] = None,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """상담 이력 조회"""
    if customer_id:
        interactions = crud.get_customer_interactions(db, customer_id, limit)
    else:
        interactions = crud.get_agent_interactions(db, current_agent.id, limit)
    return interactions

@app.post("/interactions", response_model=CustomerInteractionResponse)
async def create_interaction(
    interaction: CustomerInteractionCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """새 상담 이력 생성"""
    new_interaction = crud.create_customer_interaction(db, current_agent.id, interaction)
    return new_interaction

# WebSocket 엔드포인트
@app.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str, db: Session = Depends(get_db)):
    """WebSocket 연결 처리"""
    await manager.connect(websocket, agent_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # 메시지 타입에 따른 처리
            if message_data["type"] == "typing":
                # 타이핑 상태 브로드캐스트
                await manager.broadcast_to_session(
                    message_data["session_id"],
                    {
                        "type": "typing",
                        "data": {
                            "agent_id": agent_id,
                            "is_typing": message_data["is_typing"]
                        }
                    }
                )
            elif message_data["type"] == "join_session":
                # 세션 참여
                await manager.join_session(agent_id, message_data["session_id"])
            elif message_data["type"] == "leave_session":
                # 세션 떠나기
                await manager.leave_session(agent_id, message_data["session_id"])
                
    except WebSocketDisconnect:
        manager.disconnect(agent_id)
        logger.info(f"Agent {agent_id} disconnected")

# 통계 및 대시보드 엔드포인트
@app.get("/dashboard/stats")
async def get_dashboard_stats(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """대시보드 통계 조회"""
    today = datetime.now().date()
    
    # 오늘의 통계
    today_calls = crud.get_agent_calls_by_date(db, current_agent.id, today)
    today_chats = crud.get_agent_chats_by_date(db, current_agent.id, today)
    
    # 활성 세션 수
    active_sessions = crud.get_active_chat_sessions(db, current_agent.id)
    
    return {
        "today_calls": len(today_calls),
        "today_chats": len(today_chats),
        "active_sessions": len(active_sessions),
        "agent_status": current_agent.status,
        "total_talk_time": sum(call.duration or 0 for call in today_calls),
        "average_response_time": 0,  # 계산 로직 추가 필요
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 