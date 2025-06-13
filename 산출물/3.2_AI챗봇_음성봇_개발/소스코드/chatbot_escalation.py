"""
AI 챗봇 상담원 전환 모듈
상담원 연결 및 에스컬레이션 관리
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
import boto3
from dataclasses import dataclass

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EscalationReason(Enum):
    """에스컬레이션 사유"""
    USER_REQUEST = "user_request"  # 사용자 직접 요청
    COMPLEX_INQUIRY = "complex_inquiry"  # 복잡한 문의
    UNRESOLVED_ISSUE = "unresolved_issue"  # 미해결 문제
    NEGATIVE_SENTIMENT = "negative_sentiment"  # 부정적 감정
    SYSTEM_ERROR = "system_error"  # 시스템 오류
    TIMEOUT = "timeout"  # 응답 시간 초과
    MULTIPLE_ATTEMPTS = "multiple_attempts"  # 반복 시도

class AgentStatus(Enum):
    """상담원 상태"""
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"

class EscalationPriority(Enum):
    """에스컬레이션 우선순위"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

@dataclass
class Agent:
    """상담원 정보"""
    agent_id: str
    name: str
    email: str
    phone: str
    department: str
    skills: List[str]
    status: AgentStatus
    current_sessions: int
    max_sessions: int
    last_activity: datetime

@dataclass
class EscalationRequest:
    """에스컬레이션 요청"""
    request_id: str
    session_id: str
    user_id: str
    reason: EscalationReason
    priority: EscalationPriority
    description: str
    context: Dict
    created_at: datetime
    assigned_agent: Optional[str] = None
    status: str = "pending"

class EscalationManager:
    """
    상담원 전환 관리 클래스
    """
    
    def __init__(self, region_name: str = 'ap-northeast-2'):
        """
        에스컬레이션 관리자 초기화
        
        Args:
            region_name: AWS 리전명
        """
        self.region_name = region_name
        self.agents = self._load_agents()
        self.escalation_queue = []
        self.active_escalations = {}
        
        # AWS Connect 클라이언트
        try:
            self.connect_client = boto3.client('connect', region_name=region_name)
        except Exception as e:
            logger.warning(f"AWS Connect 클라이언트 초기화 실패: {str(e)}")
            self.connect_client = None
        
        # SNS 클라이언트 (알림용)
        try:
            self.sns_client = boto3.client('sns', region_name=region_name)
        except Exception as e:
            logger.warning(f"SNS 클라이언트 초기화 실패: {str(e)}")
            self.sns_client = None
    
    def _load_agents(self) -> Dict[str, Agent]:
        """
        상담원 정보 로드
        
        Returns:
            상담원 딕셔너리
        """
        # 실제 환경에서는 데이터베이스에서 로드
        agents_data = [
            {
                "agent_id": "agent_001",
                "name": "김상담",
                "email": "kim@company.com",
                "phone": "02-1234-5678",
                "department": "general",
                "skills": ["banking", "general_inquiry"],
                "status": AgentStatus.AVAILABLE,
                "current_sessions": 0,
                "max_sessions": 5,
                "last_activity": datetime.now()
            },
            {
                "agent_id": "agent_002",
                "name": "이전문",
                "email": "lee@company.com",
                "phone": "02-1234-5679",
                "department": "technical",
                "skills": ["insurance", "technical_support"],
                "status": AgentStatus.AVAILABLE,
                "current_sessions": 2,
                "max_sessions": 3,
                "last_activity": datetime.now()
            },
            {
                "agent_id": "agent_003",
                "name": "박매니저",
                "email": "park@company.com",
                "phone": "02-1234-5680",
                "department": "management",
                "skills": ["complaint", "escalation", "vip"],
                "status": AgentStatus.BUSY,
                "current_sessions": 1,
                "max_sessions": 2,
                "last_activity": datetime.now()
            }
        ]
        
        agents = {}
        for agent_data in agents_data:
            agent = Agent(**agent_data)
            agents[agent.agent_id] = agent
        
        return agents
    
    def should_escalate(self, session_data: Dict, user_input: str = None) -> Tuple[bool, EscalationReason, EscalationPriority]:
        """
        에스컬레이션 필요 여부 판단
        
        Args:
            session_data: 세션 데이터
            user_input: 사용자 입력 (선택적)
            
        Returns:
            (에스컬레이션 필요 여부, 사유, 우선순위)
        """
        # 사용자 직접 요청 확인
        if user_input:
            escalation_keywords = [
                '상담원', '사람', '직원', '담당자', '매니저',
                '연결', '전화', '통화', '상담', '도움'
            ]
            
            user_input_lower = user_input.lower()
            if any(keyword in user_input_lower for keyword in escalation_keywords):
                return True, EscalationReason.USER_REQUEST, EscalationPriority.MEDIUM
        
        # 부정적 감정 확인
        sentiment = session_data.get('sentiment', {})
        if sentiment.get('sentiment') == 'NEGATIVE':
            confidence = sentiment.get('confidence', {}).get('Negative', 0)
            if confidence > 0.8:
                return True, EscalationReason.NEGATIVE_SENTIMENT, EscalationPriority.HIGH
        
        # 대화 횟수 확인
        history_count = len(session_data.get('history', []))
        if history_count >= 10:
            return True, EscalationReason.MULTIPLE_ATTEMPTS, EscalationPriority.MEDIUM
        
        # 미해결 상태 지속 시간 확인
        created_at = datetime.fromisoformat(session_data.get('created_at', datetime.now().isoformat()))
        if datetime.now() - created_at > timedelta(minutes=30):
            return True, EscalationReason.TIMEOUT, EscalationPriority.LOW
        
        # 복잡한 문의 패턴 확인
        complex_keywords = ['복잡한', '어려운', '이해안됨', '설명부족', '모르겠어요']
        recent_inputs = [item.get('user_input', '') for item in session_data.get('history', [])[-3:]]
        
        for input_text in recent_inputs:
            if any(keyword in str(input_text).lower() for keyword in complex_keywords):
                return True, EscalationReason.COMPLEX_INQUIRY, EscalationPriority.MEDIUM
        
        return False, None, None
    
    def create_escalation_request(self, session_id: str, user_id: str, 
                                reason: EscalationReason, priority: EscalationPriority,
                                description: str, context: Dict) -> str:
        """
        에스컬레이션 요청 생성
        
        Args:
            session_id: 세션 ID
            user_id: 사용자 ID
            reason: 에스컬레이션 사유
            priority: 우선순위
            description: 설명
            context: 컨텍스트 정보
            
        Returns:
            에스컬레이션 요청 ID
        """
        request_id = str(uuid.uuid4())
        
        escalation_request = EscalationRequest(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            reason=reason,
            priority=priority,
            description=description,
            context=context,
            created_at=datetime.now()
        )
        
        # 큐에 추가 (우선순위순으로 정렬)
        self.escalation_queue.append(escalation_request)
        self.escalation_queue.sort(key=lambda x: (-x.priority.value, x.created_at))
        
        logger.info(f"에스컬레이션 요청 생성: {request_id} (사유: {reason.value}, 우선순위: {priority.value})")
        
        # 알림 발송
        self._send_escalation_notification(escalation_request)
        
        return request_id
    
    def find_available_agent(self, required_skills: List[str] = None, 
                           department: str = None) -> Optional[Agent]:
        """
        사용 가능한 상담원 찾기
        
        Args:
            required_skills: 필요한 스킬
            department: 부서
            
        Returns:
            사용 가능한 상담원
        """
        available_agents = []
        
        for agent in self.agents.values():
            # 상태 확인
            if agent.status != AgentStatus.AVAILABLE:
                continue
            
            # 세션 수 확인
            if agent.current_sessions >= agent.max_sessions:
                continue
            
            # 부서 확인
            if department and agent.department != department:
                continue
            
            # 스킬 확인
            if required_skills:
                if not any(skill in agent.skills for skill in required_skills):
                    continue
            
            available_agents.append(agent)
        
        if not available_agents:
            return None
        
        # 현재 세션 수가 적은 상담원 우선 선택
        available_agents.sort(key=lambda x: x.current_sessions)
        return available_agents[0]
    
    def assign_agent(self, escalation_request_id: str, agent_id: str = None) -> bool:
        """
        상담원 배정
        
        Args:
            escalation_request_id: 에스컬레이션 요청 ID
            agent_id: 상담원 ID (선택적)
            
        Returns:
            배정 성공 여부
        """
        # 에스컬레이션 요청 찾기
        escalation_request = None
        for req in self.escalation_queue:
            if req.request_id == escalation_request_id:
                escalation_request = req
                break
        
        if not escalation_request:
            logger.error(f"에스컬레이션 요청을 찾을 수 없음: {escalation_request_id}")
            return False
        
        # 상담원 선택
        if agent_id:
            agent = self.agents.get(agent_id)
            if not agent or agent.status != AgentStatus.AVAILABLE:
                logger.error(f"상담원을 사용할 수 없음: {agent_id}")
                return False
        else:
            # 자동 배정
            required_skills = self._get_required_skills(escalation_request.reason)
            agent = self.find_available_agent(required_skills)
            
            if not agent:
                logger.warning("사용 가능한 상담원이 없음")
                return False
        
        # 배정 처리
        escalation_request.assigned_agent = agent.agent_id
        escalation_request.status = "assigned"
        
        # 상담원 세션 수 증가
        agent.current_sessions += 1
        if agent.current_sessions >= agent.max_sessions:
            agent.status = AgentStatus.BUSY
        
        # 큐에서 제거하고 활성 에스컬레이션으로 이동
        self.escalation_queue.remove(escalation_request)
        self.active_escalations[escalation_request_id] = escalation_request
        
        logger.info(f"상담원 배정 완료: {escalation_request_id} -> {agent.agent_id}")
        
        # AWS Connect를 통한 연결 시도
        self._initiate_connect_call(escalation_request, agent)
        
        return True
    
    def _get_required_skills(self, reason: EscalationReason) -> List[str]:
        """
        에스컬레이션 사유에 따른 필요 스킬 반환
        
        Args:
            reason: 에스컬레이션 사유
            
        Returns:
            필요한 스킬 리스트
        """
        skill_mapping = {
            EscalationReason.USER_REQUEST: ["general_inquiry"],
            EscalationReason.COMPLEX_INQUIRY: ["technical_support"],
            EscalationReason.UNRESOLVED_ISSUE: ["escalation"],
            EscalationReason.NEGATIVE_SENTIMENT: ["complaint"],
            EscalationReason.SYSTEM_ERROR: ["technical_support"],
            EscalationReason.TIMEOUT: ["general_inquiry"],
            EscalationReason.MULTIPLE_ATTEMPTS: ["escalation"]
        }
        
        return skill_mapping.get(reason, ["general_inquiry"])
    
    def _initiate_connect_call(self, escalation_request: EscalationRequest, agent: Agent):
        """
        AWS Connect를 통한 통화 연결
        
        Args:
            escalation_request: 에스컬레이션 요청
            agent: 배정된 상담원
        """
        if not self.connect_client:
            logger.warning("AWS Connect 클라이언트가 없어 통화 연결을 건너뜀")
            return
        
        try:
            # 실제 구현에서는 Connect 인스턴스 ID와 연락처 플로우 ID 필요
            contact_flow_id = "your-contact-flow-id"
            instance_id = "your-connect-instance-id"
            
            # 사용자 전화번호는 컨텍스트에서 가져오기
            customer_phone = escalation_request.context.get('phone_number')
            
            if customer_phone:
                response = self.connect_client.start_outbound_voice_contact(
                    DestinationPhoneNumber=customer_phone,
                    ContactFlowId=contact_flow_id,
                    InstanceId=instance_id,
                    Attributes={
                        'escalation_id': escalation_request.request_id,
                        'agent_id': agent.agent_id,
                        'reason': escalation_request.reason.value
                    }
                )
                
                logger.info(f"AWS Connect 통화 시작: {response.get('ContactId')}")
            
        except Exception as e:
            logger.error(f"AWS Connect 통화 연결 실패: {str(e)}")
    
    def _send_escalation_notification(self, escalation_request: EscalationRequest):
        """
        에스컬레이션 알림 발송
        
        Args:
            escalation_request: 에스컬레이션 요청
        """
        if not self.sns_client:
            logger.warning("SNS 클라이언트가 없어 알림 발송을 건너뜀")
            return
        
        try:
            message = {
                "escalation_id": escalation_request.request_id,
                "reason": escalation_request.reason.value,
                "priority": escalation_request.priority.value,
                "description": escalation_request.description,
                "user_id": escalation_request.user_id,
                "created_at": escalation_request.created_at.isoformat()
            }
            
            # SNS 토픽에 메시지 발송 (실제 토픽 ARN 필요)
            topic_arn = "arn:aws:sns:region:account:escalation-notifications"
            
            self.sns_client.publish(
                TopicArn=topic_arn,
                Message=json.dumps(message),
                Subject=f"에스컬레이션 요청 - 우선순위 {escalation_request.priority.value}"
            )
            
            logger.info(f"에스컬레이션 알림 발송: {escalation_request.request_id}")
            
        except Exception as e:
            logger.error(f"알림 발송 실패: {str(e)}")
    
    def complete_escalation(self, escalation_request_id: str, resolution: str) -> bool:
        """
        에스컬레이션 완료 처리
        
        Args:
            escalation_request_id: 에스컬레이션 요청 ID
            resolution: 해결 내용
            
        Returns:
            완료 처리 성공 여부
        """
        escalation_request = self.active_escalations.get(escalation_request_id)
        if not escalation_request:
            return False
        
        # 상담원 세션 수 감소
        if escalation_request.assigned_agent:
            agent = self.agents.get(escalation_request.assigned_agent)
            if agent:
                agent.current_sessions = max(0, agent.current_sessions - 1)
                if agent.current_sessions < agent.max_sessions:
                    agent.status = AgentStatus.AVAILABLE
        
        # 완료 처리
        escalation_request.status = "completed"
        escalation_request.resolution = resolution
        escalation_request.completed_at = datetime.now()
        
        # 활성 에스컬레이션에서 제거
        del self.active_escalations[escalation_request_id]
        
        logger.info(f"에스컬레이션 완료: {escalation_request_id}")
        return True
    
    def get_queue_status(self) -> Dict:
        """
        큐 상태 조회
        
        Returns:
            큐 상태 정보
        """
        return {
            "queue_length": len(self.escalation_queue),
            "active_escalations": len(self.active_escalations),
            "available_agents": len([a for a in self.agents.values() 
                                   if a.status == AgentStatus.AVAILABLE]),
            "busy_agents": len([a for a in self.agents.values() 
                              if a.status == AgentStatus.BUSY])
        }
    
    def get_escalation_history(self, user_id: str = None, 
                             start_date: datetime = None, 
                             end_date: datetime = None) -> List[Dict]:
        """
        에스컬레이션 이력 조회
        
        Args:
            user_id: 사용자 ID (선택적)
            start_date: 시작 날짜 (선택적)
            end_date: 종료 날짜 (선택적)
            
        Returns:
            에스컬레이션 이력 리스트
        """
        # 실제 구현에서는 데이터베이스에서 조회
        history = []
        
        # 현재 활성 에스컬레이션들을 이력에 포함
        for escalation in self.active_escalations.values():
            if user_id and escalation.user_id != user_id:
                continue
            
            if start_date and escalation.created_at < start_date:
                continue
            
            if end_date and escalation.created_at > end_date:
                continue
            
            history.append({
                "request_id": escalation.request_id,
                "user_id": escalation.user_id,
                "reason": escalation.reason.value,
                "priority": escalation.priority.value,
                "status": escalation.status,
                "assigned_agent": escalation.assigned_agent,
                "created_at": escalation.created_at.isoformat()
            })
        
        return history

# 사용 예시
if __name__ == "__main__":
    escalation_manager = EscalationManager()
    
    # 에스컬레이션 필요 여부 확인
    session_data = {
        "session_id": "test_session",
        "user_id": "user123",
        "history": [{"user_input": "상담원과 통화하고 싶어요"}],
        "sentiment": {"sentiment": "NEGATIVE", "confidence": {"Negative": 0.9}},
        "created_at": datetime.now().isoformat()
    }
    
    should_escalate, reason, priority = escalation_manager.should_escalate(
        session_data, "상담원과 통화하고 싶어요"
    )
    
    print(f"에스컬레이션 필요: {should_escalate}")
    if should_escalate:
        print(f"사유: {reason.value}, 우선순위: {priority.value}")
        
        # 에스컬레이션 요청 생성
        request_id = escalation_manager.create_escalation_request(
            session_id="test_session",
            user_id="user123",
            reason=reason,
            priority=priority,
            description="사용자가 상담원 연결을 요청함",
            context={"phone_number": "010-1234-5678"}
        )
        
        print(f"에스컬레이션 요청 ID: {request_id}")
        
        # 상담원 배정
        success = escalation_manager.assign_agent(request_id)
        print(f"상담원 배정 성공: {success}")
        
        # 큐 상태 확인
        status = escalation_manager.get_queue_status()
        print(f"큐 상태: {status}") 