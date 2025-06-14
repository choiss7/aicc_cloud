"""
AWS Connect 콜센터용 사용자 모델
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, timezone
import json
import uuid

class UserStatus(Enum):
    """사용자 상태"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"
    PENDING = "pending"

class UserType(Enum):
    """사용자 타입"""
    CUSTOMER = "customer"
    VIP = "vip"
    CORPORATE = "corporate"
    GUEST = "guest"

class ContactChannel(Enum):
    """연락 채널"""
    VOICE = "voice"
    CHAT = "chat"
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"

@dataclass
class ContactInfo:
    """연락처 정보"""
    channel: ContactChannel
    value: str
    is_primary: bool = False
    is_verified: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verified_at: Optional[datetime] = None

@dataclass
class UserPreferences:
    """사용자 선호도 설정"""
    preferred_language: str = "ko-KR"
    preferred_channel: ContactChannel = ContactChannel.VOICE
    timezone: str = "Asia/Seoul"
    notifications_enabled: bool = True
    marketing_consent: bool = False
    callback_enabled: bool = True
    voice_recognition_enabled: bool = True

@dataclass
class UserStats:
    """사용자 통계"""
    total_conversations: int = 0
    total_call_duration: int = 0  # seconds
    average_satisfaction_score: float = 0.0
    last_contact_date: Optional[datetime] = None
    escalation_count: int = 0
    resolution_rate: float = 0.0
    preferred_agents: List[str] = field(default_factory=list)

class User:
    """사용자 정보 관리 클래스"""
    
    def __init__(
        self,
        user_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        user_type: UserType = UserType.CUSTOMER
    ):
        self.user_id = user_id or str(uuid.uuid4())
        self.name = name
        self.user_type = user_type
        self.status = UserStatus.ACTIVE
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.last_activity_at = datetime.now(timezone.utc)
        
        # 연락처 정보
        self.contact_info: List[ContactInfo] = []
        if phone_number:
            self.add_contact_info(ContactChannel.VOICE, phone_number, is_primary=True)
        if email:
            self.add_contact_info(ContactChannel.EMAIL, email)
        
        # 사용자 설정 및 통계
        self.preferences = UserPreferences()
        self.stats = UserStats()
        self.metadata: Dict[str, Any] = {}
        self.tags: List[str] = []
        
        # AWS Connect 관련
        self.connect_customer_id: Optional[str] = None
        self.connect_contact_id: Optional[str] = None
    
    def add_contact_info(
        self, 
        channel: ContactChannel, 
        value: str, 
        is_primary: bool = False,
        is_verified: bool = False
    ) -> None:
        """연락처 정보 추가"""
        # 기본 연락처가 이미 있는 경우 기존 것을 비기본으로 변경
        if is_primary:
            for contact in self.contact_info:
                if contact.channel == channel:
                    contact.is_primary = False
        
        contact = ContactInfo(
            channel=channel,
            value=value,
            is_primary=is_primary,
            is_verified=is_verified
        )
        self.contact_info.append(contact)
        self.updated_at = datetime.now(timezone.utc)
    
    def get_primary_contact(self, channel: ContactChannel) -> Optional[ContactInfo]:
        """특정 채널의 기본 연락처 가져오기"""
        for contact in self.contact_info:
            if contact.channel == channel and contact.is_primary:
                return contact
        # 기본 연락처가 없으면 해당 채널의 첫 번째 연락처 반환
        for contact in self.contact_info:
            if contact.channel == channel:
                return contact
        return None
    
    def get_phone_number(self) -> Optional[str]:
        """전화번호 가져오기"""
        contact = self.get_primary_contact(ContactChannel.VOICE)
        return contact.value if contact else None
    
    def get_email(self) -> Optional[str]:
        """이메일 가져오기"""
        contact = self.get_primary_contact(ContactChannel.EMAIL)
        return contact.value if contact else None
    
    def update_activity(self) -> None:
        """마지막 활동 시간 업데이트"""
        self.last_activity_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def add_tag(self, tag: str) -> None:
        """태그 추가"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.now(timezone.utc)
    
    def remove_tag(self, tag: str) -> None:
        """태그 제거"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.now(timezone.utc)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """메타데이터 설정"""
        self.metadata[key] = value
        self.updated_at = datetime.now(timezone.utc)
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """메타데이터 가져오기"""
        return self.metadata.get(key, default)
    
    def update_stats(
        self,
        conversation_count: int = 0,
        call_duration: int = 0,
        satisfaction_score: Optional[float] = None,
        escalation_occurred: bool = False,
        was_resolved: bool = True
    ) -> None:
        """사용자 통계 업데이트"""
        if conversation_count > 0:
            self.stats.total_conversations += conversation_count
        
        if call_duration > 0:
            self.stats.total_call_duration += call_duration
        
        if satisfaction_score is not None:
            # 평균 만족도 점수 계산
            total_score = (
                self.stats.average_satisfaction_score * 
                max(1, self.stats.total_conversations - conversation_count)
            )
            total_score += satisfaction_score * conversation_count
            self.stats.average_satisfaction_score = total_score / self.stats.total_conversations
        
        if escalation_occurred:
            self.stats.escalation_count += 1
        
        # 해결률 계산 (단순화된 방식)
        if self.stats.total_conversations > 0:
            resolved_count = self.stats.total_conversations - self.stats.escalation_count
            self.stats.resolution_rate = resolved_count / self.stats.total_conversations
        
        self.stats.last_contact_date = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def is_vip(self) -> bool:
        """VIP 고객 여부 확인"""
        return self.user_type == UserType.VIP or "vip" in self.tags
    
    def is_active(self) -> bool:
        """활성 사용자 여부 확인"""
        return self.status == UserStatus.ACTIVE
    
    def get_display_name(self) -> str:
        """표시용 이름 가져오기"""
        if self.name:
            return self.name
        
        phone = self.get_phone_number()
        if phone:
            return f"고객({phone[-4:]})"
        
        email = self.get_email()
        if email:
            return f"고객({email.split('@')[0]})"
        
        return f"고객({self.user_id[:8]})"
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "user_type": self.user_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "contact_info": [
                {
                    "channel": contact.channel.value,
                    "value": contact.value,
                    "is_primary": contact.is_primary,
                    "is_verified": contact.is_verified,
                    "created_at": contact.created_at.isoformat(),
                    "verified_at": contact.verified_at.isoformat() if contact.verified_at else None
                }
                for contact in self.contact_info
            ],
            "preferences": {
                "preferred_language": self.preferences.preferred_language,
                "preferred_channel": self.preferences.preferred_channel.value,
                "timezone": self.preferences.timezone,
                "notifications_enabled": self.preferences.notifications_enabled,
                "marketing_consent": self.preferences.marketing_consent,
                "callback_enabled": self.preferences.callback_enabled,
                "voice_recognition_enabled": self.preferences.voice_recognition_enabled
            },
            "stats": {
                "total_conversations": self.stats.total_conversations,
                "total_call_duration": self.stats.total_call_duration,
                "average_satisfaction_score": self.stats.average_satisfaction_score,
                "last_contact_date": self.stats.last_contact_date.isoformat() if self.stats.last_contact_date else None,
                "escalation_count": self.stats.escalation_count,
                "resolution_rate": self.stats.resolution_rate,
                "preferred_agents": self.stats.preferred_agents
            },
            "metadata": self.metadata,
            "tags": self.tags,
            "connect_customer_id": self.connect_customer_id,
            "connect_contact_id": self.connect_contact_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """딕셔너리에서 User 객체 생성"""
        user = cls(
            user_id=data["user_id"],
            name=data.get("name"),
            user_type=UserType(data["user_type"])
        )
        
        user.status = UserStatus(data["status"])
        user.created_at = datetime.fromisoformat(data["created_at"])
        user.updated_at = datetime.fromisoformat(data["updated_at"])
        user.last_activity_at = datetime.fromisoformat(data["last_activity_at"])
        
        # 연락처 정보 복원
        user.contact_info = []
        for contact_data in data.get("contact_info", []):
            contact = ContactInfo(
                channel=ContactChannel(contact_data["channel"]),
                value=contact_data["value"],
                is_primary=contact_data["is_primary"],
                is_verified=contact_data["is_verified"],
                created_at=datetime.fromisoformat(contact_data["created_at"])
            )
            if contact_data.get("verified_at"):
                contact.verified_at = datetime.fromisoformat(contact_data["verified_at"])
            user.contact_info.append(contact)
        
        # 선호도 설정 복원
        if "preferences" in data:
            prefs = data["preferences"]
            user.preferences = UserPreferences(
                preferred_language=prefs["preferred_language"],
                preferred_channel=ContactChannel(prefs["preferred_channel"]),
                timezone=prefs["timezone"],
                notifications_enabled=prefs["notifications_enabled"],
                marketing_consent=prefs["marketing_consent"],
                callback_enabled=prefs["callback_enabled"],
                voice_recognition_enabled=prefs["voice_recognition_enabled"]
            )
        
        # 통계 정보 복원
        if "stats" in data:
            stats = data["stats"]
            user.stats = UserStats(
                total_conversations=stats["total_conversations"],
                total_call_duration=stats["total_call_duration"],
                average_satisfaction_score=stats["average_satisfaction_score"],
                escalation_count=stats["escalation_count"],
                resolution_rate=stats["resolution_rate"],
                preferred_agents=stats["preferred_agents"]
            )
            if stats.get("last_contact_date"):
                user.stats.last_contact_date = datetime.fromisoformat(stats["last_contact_date"])
        
        user.metadata = data.get("metadata", {})
        user.tags = data.get("tags", [])
        user.connect_customer_id = data.get("connect_customer_id")
        user.connect_contact_id = data.get("connect_contact_id")
        
        return user 