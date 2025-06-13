from sqlalchemy import Column, String, DateTime, Integer, Text, Boolean, ForeignKey, Enum, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid

Base = declarative_base()

class AgentStatus(enum.Enum):
    available = "available"
    busy = "busy"
    away = "away"
    offline = "offline"

class AgentRole(enum.Enum):
    agent = "agent"
    supervisor = "supervisor"
    admin = "admin"

class CustomerStatus(enum.Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"

class CustomerType(enum.Enum):
    individual = "individual"
    business = "business"

class RiskLevel(enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class ChatSessionStatus(enum.Enum):
    active = "active"
    waiting = "waiting"
    ended = "ended"
    transferred = "transferred"

class MessageType(enum.Enum):
    text = "text"
    image = "image"
    file = "file"
    system = "system"

class MessageSender(enum.Enum):
    customer = "customer"
    agent = "agent"
    system = "system"

class CallDirection(enum.Enum):
    inbound = "inbound"
    outbound = "outbound"

class CallStatus(enum.Enum):
    ringing = "ringing"
    connected = "connected"
    on_hold = "on_hold"
    ended = "ended"
    missed = "missed"

class InteractionType(enum.Enum):
    call = "call"
    chat = "chat"
    email = "email"
    sms = "sms"

class InteractionStatus(enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"

class Priority(enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class Agent(Base):
    __tablename__ = "agents"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    role = Column(Enum(AgentRole), nullable=False, default=AgentRole.agent)
    department = Column(String(100), nullable=False)
    status = Column(Enum(AgentStatus), nullable=False, default=AgentStatus.offline)
    phone = Column(String(20))
    extension = Column(String(10))
    hire_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 관계
    chat_sessions = relationship("ChatSession", back_populates="agent")
    messages = relationship("Message", back_populates="agent")
    calls = relationship("Call", back_populates="agent")
    interactions = relationship("CustomerInteraction", back_populates="agent")

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, index=True)
    email = Column(String(100), index=True)
    phone = Column(String(20), nullable=False, index=True)
    address = Column(Text)
    date_of_birth = Column(DateTime)
    gender = Column(String(10))
    preferred_language = Column(String(10), default="ko")
    customer_type = Column(Enum(CustomerType), nullable=False, default=CustomerType.individual)
    status = Column(Enum(CustomerStatus), nullable=False, default=CustomerStatus.active)
    notes = Column(Text)
    tags = Column(Text)  # JSON 형태로 저장
    
    # 금융 관련 정보
    account_numbers = Column(Text)  # JSON 형태로 저장
    credit_score = Column(Integer)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.low)
    
    # 상담 이력 통계
    total_calls = Column(Integer, default=0)
    total_chats = Column(Integer, default=0)
    last_contact_date = Column(DateTime)
    satisfaction_score = Column(Float)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 관계
    chat_sessions = relationship("ChatSession", back_populates="customer")
    calls = relationship("Call", back_populates="customer")
    interactions = relationship("CustomerInteraction", back_populates="customer")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"))
    status = Column(Enum(ChatSessionStatus), nullable=False, default=ChatSessionStatus.waiting)
    priority = Column(Enum(Priority), nullable=False, default=Priority.medium)
    department = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False)  # web, mobile, phone, email
    tags = Column(Text)  # JSON 형태로 저장
    
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime)
    queue_time = Column(Integer)  # 대기 시간 (초)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 관계
    customer = relationship("Customer", back_populates="chat_sessions")
    agent = relationship("Agent", back_populates="chat_sessions")
    messages = relationship("Message", back_populates="chat_session", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"))
    sender = Column(Enum(MessageSender), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.text)
    
    # 파일 관련 메타데이터
    file_name = Column(String(255))
    file_size = Column(Integer)
    file_type = Column(String(100))
    file_url = Column(String(500))
    
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # 관계
    chat_session = relationship("ChatSession", back_populates="messages")
    agent = relationship("Agent", back_populates="messages")

class Call(Base):
    __tablename__ = "calls"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    
    direction = Column(Enum(CallDirection), nullable=False)
    status = Column(Enum(CallStatus), nullable=False, default=CallStatus.ringing)
    
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime)
    connect_time = Column(DateTime)
    duration = Column(Integer)  # 통화 시간 (초)
    queue_time = Column(Integer)  # 대기 시간 (초)
    hold_time = Column(Integer)  # 보류 시간 (초)
    
    recording_url = Column(String(500))
    notes = Column(Text)
    disposition = Column(String(100))
    category = Column(String(100))
    subcategory = Column(String(100))
    resolution = Column(Text)
    
    transferred_from = Column(String)
    transferred_to = Column(String)
    follow_up_required = Column(Boolean, default=False)
    satisfaction_rating = Column(Integer)
    tags = Column(Text)  # JSON 형태로 저장
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 관계
    customer = relationship("Customer", back_populates="calls")
    agent = relationship("Agent", back_populates="calls")

class CustomerInteraction(Base):
    __tablename__ = "customer_interactions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False)
    
    interaction_type = Column(Enum(InteractionType), nullable=False)
    subject = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(InteractionStatus), nullable=False, default=InteractionStatus.open)
    priority = Column(Enum(Priority), nullable=False, default=Priority.medium)
    
    category = Column(String(100), nullable=False)
    subcategory = Column(String(100))
    resolution = Column(Text)
    satisfaction_rating = Column(Integer)
    
    duration = Column(Integer)  # 상담 시간 (초)
    follow_up_date = Column(DateTime)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    resolved_at = Column(DateTime)
    
    # 관계
    customer = relationship("Customer", back_populates="interactions")
    agent = relationship("Agent", back_populates="interactions")
    attachments = relationship("InteractionAttachment", back_populates="interaction", cascade="all, delete-orphan")

class InteractionAttachment(Base):
    __tablename__ = "interaction_attachments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    interaction_id = Column(String, ForeignKey("customer_interactions.id"), nullable=False)
    
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(100), nullable=False)
    file_url = Column(String(500), nullable=False)
    
    uploaded_at = Column(DateTime, server_default=func.now())
    
    # 관계
    interaction = relationship("CustomerInteraction", back_populates="attachments")

class CallQueue(Base):
    __tablename__ = "call_queues"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    department = Column(String(100), nullable=False)
    
    max_wait_time = Column(Integer, default=300)  # 최대 대기 시간 (초)
    priority_weight = Column(Float, default=1.0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class QueueStats(Base):
    __tablename__ = "queue_stats"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("call_queues.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    
    waiting_calls = Column(Integer, default=0)
    available_agents = Column(Integer, default=0)
    average_wait_time = Column(Integer, default=0)
    longest_wait_time = Column(Integer, default=0)
    calls_offered = Column(Integer, default=0)
    calls_answered = Column(Integer, default=0)
    calls_abandoned = Column(Integer, default=0)
    
    created_at = Column(DateTime, server_default=func.now())
    
    # 관계
    queue = relationship("CallQueue") 