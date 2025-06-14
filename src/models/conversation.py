"""
AWS Connect 콜센터용 대화 모델
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import json

class MessageType(Enum):
    """메시지 타입"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    QUICK_REPLY = "quick_reply"
    CARD = "card"
    SYSTEM = "system"

class MessageSource(Enum):
    """메시지 소스"""
    USER = "user"
    BOT = "bot"
    AGENT = "agent"
    SYSTEM = "system"

class ConversationStatus(Enum):
    """대화 상태"""
    ACTIVE = "active"
    BOT_HANDLING = "bot_handling"
    ESCALATED = "escalated"
    AGENT_ASSIGNED = "agent_assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

@dataclass
class Message:
    """메시지 모델"""
    message_id: str
    conversation_id: str
    source: MessageSource
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_sensitive: bool = False
    attachments: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'message_id': self.message_id,
            'conversation_id': self.conversation_id,
            'source': self.source.value,
            'message_type': self.message_type.value,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp,
            'is_sensitive': self.is_sensitive,
            'attachments': self.attachments
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """딕셔너리에서 생성"""
        return cls(
            message_id=data['message_id'],
            conversation_id=data['conversation_id'],
            source=MessageSource(data['source']),
            message_type=MessageType(data['message_type']),
            content=data['content'],
            metadata=data.get('metadata', {}),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            is_sensitive=data.get('is_sensitive', False),
            attachments=data.get('attachments', [])
        )

@dataclass
class ConversationSummary:
    """대화 요약"""
    total_messages: int
    user_messages: int
    bot_messages: int
    agent_messages: int
    duration_minutes: float
    resolution_status: str
    satisfaction_score: Optional[float] = None
    key_topics: List[str] = field(default_factory=list)
    escalation_reason: Optional[str] = None

@dataclass
class Conversation:
    """대화 모델"""
    conversation_id: str
    session_id: str
    user_id: Optional[str]
    channel: str  # web_chat, voice, sms, etc.
    status: ConversationStatus
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ended_at: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    escalation_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    summary: Optional[ConversationSummary] = None
    
    def add_message(self, message: Message) -> None:
        """메시지 추가"""
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()
    
    def get_messages_by_source(self, source: MessageSource) -> List[Message]:
        """소스별 메시지 조회"""
        return [msg for msg in self.messages if msg.source == source]
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """최근 메시지 조회"""
        return self.messages[-count:] if len(self.messages) > count else self.messages
    
    def get_conversation_duration(self) -> float:
        """대화 지속 시간 (분)"""
        if not self.messages:
            return 0.0
        
        start_time = datetime.fromisoformat(self.messages[0].timestamp.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(self.messages[-1].timestamp.replace('Z', '+00:00'))
        
        return (end_time - start_time).total_seconds() / 60.0
    
    def update_context(self, key: str, value: Any) -> None:
        """컨텍스트 업데이트"""
        self.context[key] = value
        self.updated_at = datetime.now().isoformat()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """컨텍스트 조회"""
        return self.context.get(key, default)
    
    def add_tag(self, tag: str) -> None:
        """태그 추가"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.now().isoformat()
    
    def remove_tag(self, tag: str) -> None:
        """태그 제거"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.now().isoformat()
    
    def set_status(self, status: ConversationStatus) -> None:
        """상태 변경"""
        self.status = status
        self.updated_at = datetime.now().isoformat()
        
        if status == ConversationStatus.COMPLETED:
            self.ended_at = datetime.now().isoformat()
    
    def assign_agent(self, agent_id: str) -> None:
        """상담원 배정"""
        self.assigned_agent_id = agent_id
        self.status = ConversationStatus.AGENT_ASSIGNED
        self.updated_at = datetime.now().isoformat()
    
    def escalate(self, escalation_id: str) -> None:
        """에스컬레이션"""
        self.escalation_id = escalation_id
        self.status = ConversationStatus.ESCALATED
        self.updated_at = datetime.now().isoformat()
    
    def generate_summary(self) -> ConversationSummary:
        """대화 요약 생성"""
        user_messages = len(self.get_messages_by_source(MessageSource.USER))
        bot_messages = len(self.get_messages_by_source(MessageSource.BOT))
        agent_messages = len(self.get_messages_by_source(MessageSource.AGENT))
        
        # 주요 토픽 추출 (간단한 키워드 기반)
        key_topics = self._extract_key_topics()
        
        self.summary = ConversationSummary(
            total_messages=len(self.messages),
            user_messages=user_messages,
            bot_messages=bot_messages,
            agent_messages=agent_messages,
            duration_minutes=self.get_conversation_duration(),
            resolution_status=self.status.value,
            key_topics=key_topics,
            escalation_reason=self.context.get('escalation_reason')
        )
        
        return self.summary
    
    def _extract_key_topics(self) -> List[str]:
        """주요 토픽 추출"""
        # 실제 구현에서는 NLP 기반으로 토픽 추출
        common_keywords = {
            '주문': ['주문', '구매', '결제'],
            '배송': ['배송', '택배', '도착'],
            '환불': ['환불', '취소', '반품'],
            '문의': ['문의', '질문', '궁금'],
            '불만': ['불만', '화남', '짜증'],
            '기술지원': ['오류', '버그', '안됨', '문제']
        }
        
        topics = []
        all_text = ' '.join([msg.content for msg in self.messages if msg.source == MessageSource.USER])
        
        for topic, keywords in common_keywords.items():
            if any(keyword in all_text for keyword in keywords):
                topics.append(topic)
        
        return topics
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'conversation_id': self.conversation_id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'channel': self.channel,
            'status': self.status.value,
            'messages': [msg.to_dict() for msg in self.messages],
            'context': self.context,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'ended_at': self.ended_at,
            'assigned_agent_id': self.assigned_agent_id,
            'escalation_id': self.escalation_id,
            'tags': self.tags,
            'summary': self.summary.__dict__ if self.summary else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """딕셔너리에서 생성"""
        messages = [Message.from_dict(msg_data) for msg_data in data.get('messages', [])]
        
        conversation = cls(
            conversation_id=data['conversation_id'],
            session_id=data['session_id'],
            user_id=data.get('user_id'),
            channel=data['channel'],
            status=ConversationStatus(data['status']),
            messages=messages,
            context=data.get('context', {}),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
            ended_at=data.get('ended_at'),
            assigned_agent_id=data.get('assigned_agent_id'),
            escalation_id=data.get('escalation_id'),
            tags=data.get('tags', [])
        )
        
        # 요약 정보가 있으면 복원
        if data.get('summary'):
            summary_data = data['summary']
            conversation.summary = ConversationSummary(**summary_data)
        
        return conversation 