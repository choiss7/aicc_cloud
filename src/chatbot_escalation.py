"""
AWS Connect 콜센터용 상담원 전환(Escalation) 모듈
"""
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)

class EscalationReason(Enum):
    """에스컬레이션 사유"""
    COMPLEX_INQUIRY = "complex_inquiry"
    COMPLAINT = "complaint" 
    TECHNICAL_SUPPORT = "technical_support"
    PAYMENT_ISSUE = "payment_issue"
    URGENT_MATTER = "urgent_matter"
    BOT_LIMITATION = "bot_limitation"
    CUSTOMER_REQUEST = "customer_request"
    SYSTEM_ERROR = "system_error"

class EscalationPriority(Enum):
    """에스컬레이션 우선순위"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class EscalationStatus(Enum):
    """에스컬레이션 상태"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"

@dataclass
class EscalationRequest:
    """에스컬레이션 요청"""
    escalation_id: str
    session_id: str
    customer_id: Optional[str]
    reason: EscalationReason
    priority: EscalationPriority
    status: EscalationStatus
    description: str
    conversation_history: List[Dict]
    customer_data: Dict[str, Any]
    assigned_agent: Optional[str]
    queue_name: str
    created_at: str
    updated_at: str
    estimated_wait_time: int
    tags: List[str]

@dataclass
class AgentAvailability:
    """상담원 가용성"""
    agent_id: str
    agent_name: str
    skills: List[str]
    current_load: int
    max_capacity: int
    is_available: bool
    routing_profile: str
    last_activity: str

class ChatbotEscalation:
    """AWS Connect 챗봇 에스컬레이션 관리자"""
    
    def __init__(self, connect_instance_id: str, 
                 dynamodb_table_name: str = "chatbot_escalations"):
        self.connect_client = boto3.client('connect')
        self.dynamodb = boto3.resource('dynamodb')
        self.escalation_table = self.dynamodb.Table(dynamodb_table_name)
        self.agent_table = self.dynamodb.Table(f"{dynamodb_table_name}_agents")
        
        self.connect_instance_id = connect_instance_id
        
        # 에스컬레이션 규칙 설정
        self.escalation_rules = self._load_escalation_rules()
        
        # 큐 맵핑
        self.queue_mapping = {
            EscalationReason.COMPLAINT: "complaint-queue",
            EscalationReason.TECHNICAL_SUPPORT: "tech-support-queue", 
            EscalationReason.PAYMENT_ISSUE: "payment-queue",
            EscalationReason.URGENT_MATTER: "priority-queue",
            EscalationReason.COMPLEX_INQUIRY: "general-queue",
            EscalationReason.CUSTOMER_REQUEST: "general-queue",
            EscalationReason.BOT_LIMITATION: "general-queue",
            EscalationReason.SYSTEM_ERROR: "tech-support-queue"
        }
    
    def request_escalation(self, session_id: str, reason: EscalationReason,
                          description: str, conversation_history: List[Dict],
                          customer_data: Optional[Dict] = None,
                          priority: Optional[EscalationPriority] = None) -> Dict[str, Any]:
        """
        에스컬레이션 요청
        
        Args:
            session_id: 세션 ID
            reason: 에스컬레이션 사유
            description: 상세 설명
            conversation_history: 대화 이력
            customer_data: 고객 데이터
            priority: 우선순위 (None시 자동 계산)
            
        Returns:
            Dict: 에스컬레이션 요청 결과
        """
        try:
            # 우선순위 자동 계산
            if priority is None:
                priority = self._calculate_priority(reason, conversation_history, customer_data)
            
            # 에스컬레이션 ID 생성
            escalation_id = self._generate_escalation_id()
            
            # 적절한 큐 선택
            queue_name = self._select_queue(reason, priority)
            
            # 대기 시간 추정
            estimated_wait_time = self._estimate_wait_time(queue_name, priority)
            
            # 에스컬레이션 요청 생성
            escalation_request = EscalationRequest(
                escalation_id=escalation_id,
                session_id=session_id,
                customer_id=customer_data.get('customer_id') if customer_data else None,
                reason=reason,
                priority=priority,
                status=EscalationStatus.PENDING,
                description=description,
                conversation_history=conversation_history,
                customer_data=customer_data or {},
                assigned_agent=None,
                queue_name=queue_name,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                estimated_wait_time=estimated_wait_time,
                tags=self._generate_tags(reason, customer_data)
            )
            
            # DynamoDB에 저장
            self._save_escalation_request(escalation_request)
            
            # AWS Connect 큐에 요청 전송
            connect_response = self._send_to_connect_queue(escalation_request)
            
            if connect_response['success']:
                # 고객에게 확인 메시지 생성
                customer_message = self._generate_customer_message(escalation_request)
                
                return {
                    'success': True,
                    'escalation_id': escalation_id,
                    'message': customer_message,
                    'estimated_wait_time': estimated_wait_time,
                    'queue_position': connect_response.get('queue_position', 'N/A'),
                    'reference_number': escalation_id[:8].upper()
                }
            else:
                return {
                    'success': False,
                    'message': '상담원 연결 요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
                    'error': connect_response.get('error')
                }
                
        except Exception as e:
            logger.error(f"에스컬레이션 요청 오류: {str(e)}")
            return {
                'success': False,
                'message': '상담원 연결 요청을 처리할 수 없습니다. 고객센터로 직접 연락해주세요.'
            }
    
    def check_escalation_status(self, escalation_id: str) -> Dict[str, Any]:
        """에스컬레이션 상태 확인"""
        try:
            escalation = self._get_escalation_request(escalation_id)
            if not escalation:
                return {'success': False, 'message': '요청을 찾을 수 없습니다.'}
            
            # 실시간 대기 시간 업데이트
            current_wait_time = self._get_current_wait_time(escalation.queue_name)
            
            return {
                'success': True,
                'escalation_id': escalation.escalation_id,
                'status': escalation.status.value,
                'priority': escalation.priority.value,
                'estimated_wait_time': current_wait_time,
                'assigned_agent': escalation.assigned_agent,
                'created_at': escalation.created_at,
                'reference_number': escalation.escalation_id[:8].upper()
            }
            
        except Exception as e:
            logger.error(f"에스컬레이션 상태 확인 오류: {str(e)}")
            return {'success': False, 'message': '상태를 확인할 수 없습니다.'}
    
    def cancel_escalation(self, escalation_id: str, reason: str = "") -> Dict[str, Any]:
        """에스컬레이션 취소"""
        try:
            escalation = self._get_escalation_request(escalation_id)
            if not escalation:
                return {'success': False, 'message': '요청을 찾을 수 없습니다.'}
            
            if escalation.status in [EscalationStatus.IN_PROGRESS, EscalationStatus.RESOLVED]:
                return {'success': False, 'message': '이미 처리 중이거나 완료된 요청은 취소할 수 없습니다.'}
            
            # 상태 업데이트
            escalation.status = EscalationStatus.CANCELLED
            escalation.updated_at = datetime.now().isoformat()
            
            self._save_escalation_request(escalation)
            
            # AWS Connect에서 제거 (큐에서 대기 중인 경우)
            self._remove_from_connect_queue(escalation_id)
            
            return {
                'success': True,
                'message': '상담원 연결 요청이 취소되었습니다.',
                'escalation_id': escalation_id
            }
            
        except Exception as e:
            logger.error(f"에스컬레이션 취소 오류: {str(e)}")
            return {'success': False, 'message': '취소 요청을 처리할 수 없습니다.'}
    
    def get_available_agents(self, skills: Optional[List[str]] = None) -> List[AgentAvailability]:
        """가용한 상담원 목록 조회"""
        try:
            # AWS Connect에서 상담원 상태 조회
            response = self.connect_client.get_current_metric_data(
                InstanceId=self.connect_instance_id,
                Filters={
                    'Queues': [],
                    'Channels': ['VOICE', 'CHAT']
                },
                Groupings=['AGENT'],
                CurrentMetrics=[
                    {'Name': 'AGENTS_AVAILABLE', 'Unit': 'COUNT'},
                    {'Name': 'AGENTS_ONLINE', 'Unit': 'COUNT'},
                    {'Name': 'AGENTS_ON_CALL', 'Unit': 'COUNT'}
                ]
            )
            
            available_agents = []
            
            for metric_result in response.get('MetricResults', []):
                agent_data = metric_result.get('Dimensions', {})
                agent_id = agent_data.get('Agent', {}).get('Id')
                
                if agent_id:
                    agent_info = self._get_agent_info(agent_id)
                    
                    if agent_info and (not skills or self._agent_has_skills(agent_info, skills)):
                        available_agents.append(agent_info)
            
            return available_agents
            
        except Exception as e:
            logger.error(f"가용 상담원 조회 오류: {str(e)}")
            return []
    
    def assign_agent(self, escalation_id: str, agent_id: str) -> Dict[str, Any]:
        """상담원 배정"""
        try:
            escalation = self._get_escalation_request(escalation_id)
            if not escalation:
                return {'success': False, 'message': '요청을 찾을 수 없습니다.'}
            
            # 상담원 가용성 확인
            agent_info = self._get_agent_info(agent_id)
            if not agent_info or not agent_info.is_available:
                return {'success': False, 'message': '해당 상담원은 현재 사용할 수 없습니다.'}
            
            # 에스컬레이션 업데이트
            escalation.assigned_agent = agent_id
            escalation.status = EscalationStatus.ASSIGNED
            escalation.updated_at = datetime.now().isoformat()
            
            self._save_escalation_request(escalation)
            
            # 상담원에게 알림 전송
            self._notify_agent(agent_id, escalation)
            
            return {
                'success': True,
                'message': f'상담원 {agent_info.agent_name}이 배정되었습니다.',
                'agent_name': agent_info.agent_name,
                'escalation_id': escalation_id
            }
            
        except Exception as e:
            logger.error(f"상담원 배정 오류: {str(e)}")
            return {'success': False, 'message': '상담원 배정을 처리할 수 없습니다.'}
    
    def get_escalation_analytics(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """에스컬레이션 분석 데이터"""
        try:
            response = self.escalation_table.scan(
                FilterExpression='created_at BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':start': start_date,
                    ':end': end_date
                }
            )
            
            escalations = response.get('Items', [])
            
            analytics = {
                'total_escalations': len(escalations),
                'by_reason': {},
                'by_priority': {},
                'by_status': {},
                'average_wait_time': 0,
                'resolution_rate': 0
            }
            
            total_wait_time = 0
            resolved_count = 0
            
            for escalation in escalations:
                # 사유별 통계
                reason = escalation.get('reason', 'unknown')
                analytics['by_reason'][reason] = analytics['by_reason'].get(reason, 0) + 1
                
                # 우선순위별 통계
                priority = escalation.get('priority', 'unknown')
                analytics['by_priority'][priority] = analytics['by_priority'].get(priority, 0) + 1
                
                # 상태별 통계
                status = escalation.get('status', 'unknown')
                analytics['by_status'][status] = analytics['by_status'].get(status, 0) + 1
                
                # 대기 시간 집계
                if escalation.get('estimated_wait_time'):
                    total_wait_time += escalation['estimated_wait_time']
                
                # 해결 건수
                if status == EscalationStatus.RESOLVED.value:
                    resolved_count += 1
            
            # 평균 계산
            if escalations:
                analytics['average_wait_time'] = total_wait_time / len(escalations)
                analytics['resolution_rate'] = (resolved_count / len(escalations)) * 100
            
            return analytics
            
        except Exception as e:
            logger.error(f"에스컬레이션 분석 오류: {str(e)}")
            return {}
    
    def _calculate_priority(self, reason: EscalationReason, 
                          conversation_history: List[Dict],
                          customer_data: Optional[Dict]) -> EscalationPriority:
        """우선순위 자동 계산"""
        base_priority = {
            EscalationReason.URGENT_MATTER: EscalationPriority.CRITICAL,
            EscalationReason.COMPLAINT: EscalationPriority.HIGH,
            EscalationReason.PAYMENT_ISSUE: EscalationPriority.HIGH,
            EscalationReason.SYSTEM_ERROR: EscalationPriority.HIGH,
            EscalationReason.TECHNICAL_SUPPORT: EscalationPriority.MEDIUM,
            EscalationReason.COMPLEX_INQUIRY: EscalationPriority.MEDIUM,
            EscalationReason.CUSTOMER_REQUEST: EscalationPriority.LOW,
            EscalationReason.BOT_LIMITATION: EscalationPriority.LOW
        }.get(reason, EscalationPriority.MEDIUM)
        
        # VIP 고객 우선순위 상향
        if customer_data and customer_data.get('vip_status'):
            if base_priority.value < EscalationPriority.HIGH.value:
                return EscalationPriority.HIGH
        
        # 반복 문의 시 우선순위 상향
        if len(conversation_history) > 10:
            if base_priority.value < EscalationPriority.MEDIUM.value:
                return EscalationPriority.MEDIUM
        
        return base_priority
    
    def _select_queue(self, reason: EscalationReason, 
                     priority: EscalationPriority) -> str:
        """적절한 큐 선택"""
        base_queue = self.queue_mapping.get(reason, "general-queue")
        
        # 우선순위가 높은 경우 우선순위 큐 사용
        if priority == EscalationPriority.CRITICAL:
            return "priority-queue"
        
        return base_queue
    
    def _estimate_wait_time(self, queue_name: str, 
                           priority: EscalationPriority) -> int:
        """대기 시간 추정 (분 단위)"""
        try:
            # AWS Connect 큐 메트릭 조회
            response = self.connect_client.get_current_metric_data(
                InstanceId=self.connect_instance_id,
                Filters={'Queues': [queue_name]},
                CurrentMetrics=[
                    {'Name': 'CONTACTS_IN_QUEUE', 'Unit': 'COUNT'},
                    {'Name': 'AGENTS_AVAILABLE', 'Unit': 'COUNT'},
                    {'Name': 'LONGEST_QUEUE_WAIT_TIME', 'Unit': 'SECONDS'}
                ]
            )
            
            contacts_in_queue = 0
            agents_available = 0
            longest_wait = 0
            
            for metric_result in response.get('MetricResults', []):
                collections = metric_result.get('Collections', [])
                for collection in collections:
                    metric_name = collection.get('Metric', {}).get('Name')
                    value = collection.get('Value', 0)
                    
                    if metric_name == 'CONTACTS_IN_QUEUE':
                        contacts_in_queue = int(value)
                    elif metric_name == 'AGENTS_AVAILABLE':
                        agents_available = int(value)
                    elif metric_name == 'LONGEST_QUEUE_WAIT_TIME':
                        longest_wait = int(value) // 60  # 초를 분으로 변환
            
            # 대기 시간 계산
            if agents_available > 0:
                estimated_wait = (contacts_in_queue / agents_available) * 3  # 평균 통화 시간 3분 가정
            else:
                estimated_wait = max(longest_wait, 15)  # 최소 15분
            
            # 우선순위에 따른 조정
            if priority == EscalationPriority.CRITICAL:
                estimated_wait = min(estimated_wait, 5)
            elif priority == EscalationPriority.HIGH:
                estimated_wait = min(estimated_wait, 10)
            
            return max(1, int(estimated_wait))
            
        except Exception as e:
            logger.error(f"대기 시간 추정 오류: {str(e)}")
            return 15  # 기본값
    
    def _generate_tags(self, reason: EscalationReason, 
                      customer_data: Optional[Dict]) -> List[str]:
        """태그 생성"""
        tags = [reason.value]
        
        if customer_data:
            if customer_data.get('vip_status'):
                tags.append('vip')
            if customer_data.get('repeat_customer'):
                tags.append('returning')
            if customer_data.get('customer_segment'):
                tags.append(f"segment_{customer_data['customer_segment']}")
        
        return tags
    
    def _generate_escalation_id(self) -> str:
        """에스컬레이션 ID 생성"""
        return f"esc_{uuid.uuid4().hex[:12]}"
    
    def _generate_customer_message(self, escalation: EscalationRequest) -> str:
        """고객 안내 메시지 생성"""
        reference_number = escalation.escalation_id[:8].upper()
        wait_time = escalation.estimated_wait_time
        
        message = f"상담원 연결 요청이 접수되었습니다.\n"
        message += f"참조번호: {reference_number}\n"
        message += f"예상 대기시간: 약 {wait_time}분\n\n"
        
        if escalation.priority == EscalationPriority.CRITICAL:
            message += "긴급 요청으로 우선 처리됩니다."
        elif escalation.priority == EscalationPriority.HIGH:
            message += "우선순위가 높은 요청입니다."
        else:
            message += "순서대로 처리됩니다."
            
        message += "\n\n잠시만 기다려주세요. 곧 상담원이 연결됩니다."
        
        return message
    
    def _load_escalation_rules(self) -> Dict:
        """에스컬레이션 규칙 로드"""
        return {
            'max_retry_attempts': 3,
            'auto_escalation_keywords': [
                '화남', '짜증', '취소', '환불', '불만', '화가', '최악', '실망'
            ],
            'priority_keywords': {
                EscalationPriority.CRITICAL: ['긴급', '응급', '당장', '즉시'],
                EscalationPriority.HIGH: ['빠른', '중요한', '심각한'],
            },
            'working_hours': {
                'start': 9,
                'end': 18,
                'timezone': 'Asia/Seoul'
            }
        }
    
    def _save_escalation_request(self, escalation: EscalationRequest):
        """에스컬레이션 요청 저장"""
        try:
            self.escalation_table.put_item(Item={
                'escalation_id': escalation.escalation_id,
                'session_id': escalation.session_id,
                'customer_id': escalation.customer_id,
                'reason': escalation.reason.value,
                'priority': escalation.priority.value,
                'status': escalation.status.value,
                'description': escalation.description,
                'conversation_history': escalation.conversation_history,
                'customer_data': escalation.customer_data,
                'assigned_agent': escalation.assigned_agent,
                'queue_name': escalation.queue_name,
                'created_at': escalation.created_at,
                'updated_at': escalation.updated_at,
                'estimated_wait_time': escalation.estimated_wait_time,
                'tags': escalation.tags
            })
        except Exception as e:
            logger.error(f"에스컬레이션 요청 저장 오류: {str(e)}")
            raise
    
    def _get_escalation_request(self, escalation_id: str) -> Optional[EscalationRequest]:
        """에스컬레이션 요청 조회"""
        try:
            response = self.escalation_table.get_item(Key={'escalation_id': escalation_id})
            item = response.get('Item')
            
            if not item:
                return None
            
            return EscalationRequest(
                escalation_id=item['escalation_id'],
                session_id=item['session_id'],
                customer_id=item.get('customer_id'),
                reason=EscalationReason(item['reason']),
                priority=EscalationPriority(item['priority']),
                status=EscalationStatus(item['status']),
                description=item['description'],
                conversation_history=item['conversation_history'],
                customer_data=item['customer_data'],
                assigned_agent=item.get('assigned_agent'),
                queue_name=item['queue_name'],
                created_at=item['created_at'],
                updated_at=item['updated_at'],
                estimated_wait_time=item['estimated_wait_time'],
                tags=item.get('tags', [])
            )
            
        except Exception as e:
            logger.error(f"에스컬레이션 요청 조회 오류: {str(e)}")
            return None
    
    def _send_to_connect_queue(self, escalation: EscalationRequest) -> Dict[str, Any]:
        """AWS Connect 큐에 요청 전송"""
        try:
            # 실제 AWS Connect API 호출
            # 여기서는 시뮬레이션
            return {
                'success': True,
                'queue_position': 3,
                'contact_id': f"contact_{uuid.uuid4().hex[:8]}"
            }
        except Exception as e:
            logger.error(f"Connect 큐 전송 오류: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _remove_from_connect_queue(self, escalation_id: str):
        """AWS Connect 큐에서 제거"""
        try:
            # 실제 구현에서는 AWS Connect API 호출
            pass
        except Exception as e:
            logger.error(f"Connect 큐 제거 오류: {str(e)}")
    
    def _get_current_wait_time(self, queue_name: str) -> int:
        """현재 대기 시간 조회"""
        try:
            # AWS Connect 실시간 메트릭 조회
            return self._estimate_wait_time(queue_name, EscalationPriority.MEDIUM)
        except Exception as e:
            logger.error(f"현재 대기 시간 조회 오류: {str(e)}")
            return 15
    
    def _get_agent_info(self, agent_id: str) -> Optional[AgentAvailability]:
        """상담원 정보 조회"""
        try:
            # DynamoDB나 AWS Connect에서 상담원 정보 조회
            # 여기서는 시뮬레이션
            return AgentAvailability(
                agent_id=agent_id,
                agent_name=f"Agent_{agent_id[:4]}",
                skills=['general', 'chat'],
                current_load=2,
                max_capacity=5,
                is_available=True,
                routing_profile="Basic_Routing_Profile",
                last_activity=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"상담원 정보 조회 오류: {str(e)}")
            return None
    
    def _agent_has_skills(self, agent: AgentAvailability, required_skills: List[str]) -> bool:
        """상담원 스킬 확인"""
        return any(skill in agent.skills for skill in required_skills)
    
    def _notify_agent(self, agent_id: str, escalation: EscalationRequest):
        """상담원에게 알림 전송"""
        try:
            # 실제 구현에서는 SNS, SES 등을 통한 알림
            logger.info(f"상담원 {agent_id}에게 에스컬레이션 {escalation.escalation_id} 배정 알림 전송")
        except Exception as e:
            logger.error(f"상담원 알림 전송 오류: {str(e)}") 