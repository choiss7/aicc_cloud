# 상담원 데스크탑/웹 UI 개발 가이드

## 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [개발 환경 설정](#개발-환경-설정)
4. [프론트엔드 개발](#프론트엔드-개발)
5. [백엔드 개발](#백엔드-개발)
6. [실시간 통신](#실시간-통신)
7. [데이터베이스 설계](#데이터베이스-설계)
8. [AWS 서비스 연동](#aws-서비스-연동)
9. [배포 및 운영](#배포-및-운영)
10. [테스트](#테스트)
11. [문제 해결](#문제-해결)

## 프로젝트 개요

### 목적
AWS Connect 기반 콜센터를 위한 상담원 데스크탑/웹 UI 개발

### 주요 기능
- **실시간 채팅**: WebSocket 기반 실시간 고객 채팅
- **고객정보 조회**: 통합 고객 데이터베이스 검색 및 조회
- **상담 이력 관리**: 통화/채팅 이력 추적 및 관리
- **통화 제어**: AWS Connect 통화 제어 기능
- **대시보드**: 실시간 통계 및 성과 지표

### 기술 스택
- **Frontend**: React 18, TypeScript, Material-UI, Redux Toolkit
- **Backend**: FastAPI, SQLAlchemy, PostgreSQL
- **Real-time**: WebSocket, Socket.IO
- **Cloud**: AWS ECS Fargate, ALB, RDS, Connect
- **Deployment**: Docker, AWS ECR

## 시스템 아키텍처

```mermaid
graph TB
    subgraph "Frontend (React)"
        A[상담원 UI]
        B[채팅 인터페이스]
        C[고객 정보 패널]
        D[통화 제어]
    end
    
    subgraph "Backend (FastAPI)"
        E[REST API]
        F[WebSocket Handler]
        G[인증 서비스]
        H[비즈니스 로직]
    end
    
    subgraph "Database"
        I[PostgreSQL]
        J[Redis Cache]
    end
    
    subgraph "AWS Services"
        K[AWS Connect]
        L[Amazon Comprehend]
        M[Amazon S3]
        N[Amazon SNS]
    end
    
    A --> E
    B --> F
    E --> I
    F --> J
    H --> K
    H --> L
    H --> M
    H --> N
```

## 개발 환경 설정

### 사전 요구사항
```bash
# Node.js 18+ 설치
node --version  # v18.0.0+

# Python 3.9+ 설치
python --version  # 3.9.0+

# Docker 설치
docker --version

# AWS CLI 설치 및 설정
aws --version
aws configure
```

### 프로젝트 클론 및 설정
```bash
# 프로젝트 클론
git clone <repository-url>
cd agent-desktop-ui

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집하여 필요한 값 설정
```

### 로컬 개발 환경 실행
```bash
# Backend 실행
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend 실행 (새 터미널)
cd frontend
npm install
npm start
```

## 프론트엔드 개발

### 프로젝트 구조
```
frontend/
├── src/
│   ├── components/          # 재사용 가능한 컴포넌트
│   │   ├── Layout/         # 레이아웃 컴포넌트
│   │   ├── Chat/           # 채팅 관련 컴포넌트
│   │   ├── Customer/       # 고객 정보 컴포넌트
│   │   └── Common/         # 공통 컴포넌트
│   ├── pages/              # 페이지 컴포넌트
│   │   ├── Dashboard/      # 대시보드
│   │   ├── Chat/           # 채팅 인터페이스
│   │   ├── Customer/       # 고객 정보
│   │   └── History/        # 상담 이력
│   ├── store/              # Redux 상태 관리
│   │   ├── slices/         # Redux 슬라이스
│   │   └── store.ts        # 스토어 설정
│   ├── services/           # API 서비스
│   ├── hooks/              # 커스텀 훅
│   ├── utils/              # 유틸리티 함수
│   └── types/              # TypeScript 타입 정의
├── public/
└── package.json
```

### 주요 컴포넌트 개발

#### 1. 채팅 인터페이스 (ChatInterface)
```typescript
// src/pages/Chat/ChatInterface.tsx
import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { WebSocketService } from '../../services/websocket';

const ChatInterface: React.FC = () => {
  const dispatch = useDispatch();
  const { currentSession, messages } = useSelector(state => state.chat);
  
  useEffect(() => {
    // WebSocket 연결 초기화
    WebSocketService.connect();
    
    return () => {
      WebSocketService.disconnect();
    };
  }, []);
  
  // 메시지 전송 로직
  const handleSendMessage = (content: string) => {
    WebSocketService.sendMessage({
      sessionId: currentSession.id,
      content,
      type: 'text'
    });
  };
  
  return (
    // UI 렌더링
  );
};
```

#### 2. 고객 정보 패널 (CustomerInfo)
```typescript
// src/pages/Customer/CustomerInfo.tsx
import React, { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from 'react-query';
import { customerAPI } from '../../services/api';

const CustomerInfo: React.FC = () => {
  const { customerId } = useParams<{ customerId: string }>();
  
  const { data: customer, isLoading } = useQuery(
    ['customer', customerId],
    () => customerAPI.getCustomer(customerId),
    { enabled: !!customerId }
  );
  
  return (
    // 고객 정보 UI
  );
};
```

### 상태 관리 (Redux)

#### 채팅 상태 관리
```typescript
// src/store/slices/chatSlice.ts
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface ChatState {
  activeSessions: ChatSession[];
  currentSession: ChatSession | null;
  messages: Message[];
  isConnected: boolean;
}

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setCurrentSession: (state, action) => {
      state.currentSession = action.payload;
    },
    addMessage: (state, action) => {
      state.messages.push(action.payload);
    },
    // 기타 리듀서들...
  }
});
```

### API 서비스

#### WebSocket 서비스
```typescript
// src/services/websocket.ts
class WebSocketService {
  private ws: WebSocket | null = null;
  
  connect() {
    this.ws = new WebSocket(`ws://localhost:8000/ws/${agentId}`);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
  }
  
  sendMessage(message: MessageData) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }
  
  private handleMessage(data: any) {
    // 메시지 타입에 따른 처리
    switch (data.type) {
      case 'message':
        store.dispatch(addMessage(data.payload));
        break;
      case 'session_update':
        store.dispatch(updateSession(data.payload));
        break;
    }
  }
}
```

## 백엔드 개발

### 프로젝트 구조
```
backend/
├── main.py                 # FastAPI 애플리케이션 진입점
├── models.py              # SQLAlchemy 모델
├── schemas.py             # Pydantic 스키마
├── database.py            # 데이터베이스 설정
├── auth.py                # 인증 관련
├── crud.py                # CRUD 작업
├── websocket_manager.py   # WebSocket 관리
├── services/              # 비즈니스 로직
│   ├── chat_service.py
│   ├── customer_service.py
│   └── aws_service.py
├── routers/               # API 라우터
│   ├── auth.py
│   ├── chat.py
│   ├── customer.py
│   └── calls.py
└── requirements.txt
```

### 주요 API 엔드포인트

#### 인증 API
```python
# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/login")
async def login(credentials: LoginCredentials, db: Session = Depends(get_db)):
    agent = authenticate_agent(db, credentials.username, credentials.password)
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token(data={"sub": agent.username})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/logout")
async def logout(current_agent: Agent = Depends(get_current_agent)):
    # 로그아웃 로직
    return {"message": "Logged out successfully"}
```

#### 채팅 API
```python
# routers/chat.py
@router.get("/sessions")
async def get_chat_sessions(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    sessions = get_active_chat_sessions(db, current_agent.id)
    return sessions

@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    message: MessageCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    # 메시지 저장
    new_message = create_message(db, session_id, current_agent.id, message)
    
    # WebSocket으로 실시간 전송
    await websocket_manager.broadcast_to_session(session_id, {
        "type": "message",
        "data": new_message
    })
    
    return new_message
```

### WebSocket 관리

```python
# websocket_manager.py
from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.session_participants: Dict[str, List[str]] = {}
    
    async def connect(self, websocket: WebSocket, agent_id: str):
        await websocket.accept()
        self.active_connections[agent_id] = websocket
    
    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]
    
    async def broadcast_to_session(self, session_id: str, message: dict):
        if session_id in self.session_participants:
            for agent_id in self.session_participants[session_id]:
                if agent_id in self.active_connections:
                    await self.active_connections[agent_id].send_text(
                        json.dumps(message)
                    )
```

## 실시간 통신

### WebSocket 연결 흐름
1. 상담원 로그인 시 WebSocket 연결 생성
2. 채팅 세션 참여 시 세션 그룹에 추가
3. 메시지 전송 시 해당 세션 참여자들에게 브로드캐스트
4. 연결 해제 시 정리 작업 수행

### 메시지 타입
```typescript
interface WebSocketMessage {
  type: 'message' | 'typing' | 'session_update' | 'agent_status';
  data: any;
  timestamp: string;
}
```

## 데이터베이스 설계

### 주요 테이블

#### Agents (상담원)
```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    role agent_role NOT NULL DEFAULT 'agent',
    department VARCHAR(100) NOT NULL,
    status agent_status NOT NULL DEFAULT 'offline',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Customers (고객)
```sql
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20) NOT NULL,
    customer_type customer_type DEFAULT 'individual',
    status customer_status DEFAULT 'active',
    risk_level risk_level DEFAULT 'low',
    total_calls INTEGER DEFAULT 0,
    total_chats INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Chat Sessions (채팅 세션)
```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY,
    customer_id UUID REFERENCES customers(id),
    agent_id UUID REFERENCES agents(id),
    status chat_session_status DEFAULT 'waiting',
    priority priority DEFAULT 'medium',
    department VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL,
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 인덱스 최적화
```sql
-- 성능 최적화를 위한 인덱스
CREATE INDEX idx_customers_phone ON customers(phone);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_chat_sessions_agent_status ON chat_sessions(agent_id, status);
CREATE INDEX idx_messages_session_created ON messages(chat_session_id, created_at);
```

## AWS 서비스 연동

### AWS Connect 통합
```python
# services/aws_service.py
import boto3

class AWSConnectService:
    def __init__(self):
        self.connect_client = boto3.client('connect')
        self.instance_id = os.getenv('CONNECT_INSTANCE_ID')
    
    async def initiate_outbound_call(self, customer_phone: str, agent_id: str):
        response = self.connect_client.start_outbound_voice_contact(
            DestinationPhoneNumber=customer_phone,
            ContactFlowId=os.getenv('CONTACT_FLOW_ID'),
            InstanceId=self.instance_id,
            SourcePhoneNumber=os.getenv('SOURCE_PHONE_NUMBER')
        )
        return response
    
    async def transfer_call(self, contact_id: str, target_agent_id: str):
        # 통화 전환 로직
        pass
```

### Amazon Comprehend 감정 분석
```python
class SentimentAnalysisService:
    def __init__(self):
        self.comprehend = boto3.client('comprehend')
    
    async def analyze_sentiment(self, text: str) -> dict:
        response = self.comprehend.detect_sentiment(
            Text=text,
            LanguageCode='ko'
        )
        return {
            'sentiment': response['Sentiment'],
            'confidence': response['SentimentScore']
        }
```

## 배포 및 운영

### Docker 컨테이너화

#### Frontend Dockerfile
```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
```

#### Backend Dockerfile
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### AWS ECS 배포
```bash
# 배포 스크립트 실행
chmod +x deploy_agent_ui.sh
./deploy_agent_ui.sh
```

### 환경 변수 설정
```bash
# .env 파일
DATABASE_URL=postgresql://user:password@localhost:5432/agent_db
AWS_REGION=ap-northeast-2
CONNECT_INSTANCE_ID=your-connect-instance-id
JWT_SECRET_KEY=your-secret-key
REDIS_URL=redis://localhost:6379
```

## 테스트

### 단위 테스트

#### Frontend 테스트 (Jest + React Testing Library)
```typescript
// src/components/Chat/__tests__/ChatInterface.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { Provider } from 'react-redux';
import ChatInterface from '../ChatInterface';

describe('ChatInterface', () => {
  test('메시지 전송 기능 테스트', () => {
    render(
      <Provider store={mockStore}>
        <ChatInterface />
      </Provider>
    );
    
    const messageInput = screen.getByPlaceholderText('메시지를 입력하세요...');
    const sendButton = screen.getByRole('button', { name: /전송/i });
    
    fireEvent.change(messageInput, { target: { value: '테스트 메시지' } });
    fireEvent.click(sendButton);
    
    expect(mockStore.getActions()).toContainEqual(
      expect.objectContaining({
        type: 'chat/addMessage'
      })
    );
  });
});
```

#### Backend 테스트 (pytest)
```python
# tests/test_chat_api.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_send_message():
    # 로그인
    login_response = client.post("/auth/login", json={
        "username": "test_agent",
        "password": "test_password"
    })
    token = login_response.json()["access_token"]
    
    # 메시지 전송
    response = client.post(
        "/chat/sessions/test-session-id/messages",
        json={"content": "테스트 메시지", "type": "text"},
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json()["content"] == "테스트 메시지"
```

### 통합 테스트
```python
# tests/test_integration.py
@pytest.mark.asyncio
async def test_chat_flow():
    # 1. 상담원 로그인
    # 2. 고객 채팅 세션 생성
    # 3. 메시지 교환
    # 4. 세션 종료
    pass
```

### 성능 테스트
```bash
# Locust를 사용한 부하 테스트
pip install locust

# locustfile.py 작성 후 실행
locust -f locustfile.py --host=http://localhost:8000
```

## 문제 해결

### 일반적인 문제들

#### 1. WebSocket 연결 실패
```typescript
// 재연결 로직 구현
class WebSocketService {
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  
  private reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      setTimeout(() => {
        this.reconnectAttempts++;
        this.connect();
      }, 1000 * this.reconnectAttempts);
    }
  }
}
```

#### 2. 데이터베이스 연결 풀 고갈
```python
# database.py
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

#### 3. 메모리 누수 방지
```typescript
// useEffect cleanup
useEffect(() => {
  const subscription = websocketService.subscribe(handleMessage);
  
  return () => {
    subscription.unsubscribe();
  };
}, []);
```

### 로깅 및 모니터링

#### 구조화된 로깅
```python
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(
        "request_processed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=process_time
    )
    
    return response
```

#### 에러 추적
```typescript
// Frontend 에러 바운더리
class ErrorBoundary extends React.Component {
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
    // 에러 리포팅 서비스로 전송
  }
}
```

### 성능 최적화

#### Frontend 최적화
```typescript
// React.memo를 사용한 컴포넌트 최적화
const MessageItem = React.memo(({ message }: { message: Message }) => {
  return <div>{message.content}</div>;
});

// useMemo를 사용한 계산 최적화
const sortedMessages = useMemo(() => {
  return messages.sort((a, b) => a.timestamp - b.timestamp);
}, [messages]);
```

#### Backend 최적화
```python
# 데이터베이스 쿼리 최적화
def get_chat_sessions_with_messages(db: Session, agent_id: str):
    return db.query(ChatSession)\
        .options(joinedload(ChatSession.messages))\
        .filter(ChatSession.agent_id == agent_id)\
        .all()

# 캐싱 적용
from functools import lru_cache

@lru_cache(maxsize=128)
def get_customer_by_phone(phone: str):
    # 캐시된 고객 조회
    pass
```

## 운영 체크리스트

### 배포 전 확인사항
- [ ] 모든 테스트 통과
- [ ] 환경 변수 설정 확인
- [ ] 데이터베이스 마이그레이션 완료
- [ ] SSL 인증서 설정
- [ ] 로드 밸런서 설정 확인
- [ ] 모니터링 대시보드 설정

### 운영 중 모니터링
- [ ] 응답 시간 모니터링
- [ ] 에러율 추적
- [ ] 데이터베이스 성능 모니터링
- [ ] WebSocket 연결 상태 확인
- [ ] 메모리 사용량 모니터링

이 가이드를 통해 상담원 UI 시스템을 성공적으로 개발하고 운영할 수 있습니다. 