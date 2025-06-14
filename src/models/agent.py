"""
AWS Connect 콜센터용 상담원 모델
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime, timedelta, timezone
import json
import uuid

class AgentStatus(Enum):
    """상담원 상태"""
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"
    IN_CALL = "in_call"
    IN_CHAT = "in_chat"
    AFTER_CALL_WORK = "after_call_work"
    BREAK = "break"
    TRAINING = "training"
    MEETING = "meeting"

class AgentRole(Enum):
    """상담원 역할"""
    JUNIOR = "junior"
    SENIOR = "senior"
    SPECIALIST = "specialist"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"

class ShiftType(Enum):
    """근무 형태"""
    DAY = "day"
    EVENING = "evening" 
    NIGHT = "night"
    FLEXIBLE = "flexible"

class AgentTier(Enum):
    """상담원 등급"""
    JUNIOR = "junior"
    SENIOR = "senior"
    EXPERT = "expert"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"

class SkillLevel(Enum):
    """스킬 레벨"""
    BEGINNER = 1
    INTERMEDIATE = 3
    ADVANCED = 5
    EXPERT = 7
    MASTER = 10

@dataclass
class AgentSkill:
    """상담원 스킬"""
    skill_id: str
    skill_name: str
    proficiency_level: int  # 1-5 (1: 초급, 5: 전문가)
    certified: bool = False
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'skill_id': self.skill_id,
            'skill_name': self.skill_name,
            'proficiency_level': self.proficiency_level,
            'certified': self.certified,
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentSkill':
        """딕셔너리에서 생성"""
        return cls(
            skill_id=data['skill_id'],
            skill_name=data['skill_name'],
            proficiency_level=data.get('proficiency_level', 1),
            certified=data.get('certified', False),
            last_updated=data.get('last_updated', datetime.now().isoformat())
        )

@dataclass
class WorkingHours:
    """근무 시간"""
    start_time: str  # HH:MM 형식
    end_time: str    # HH:MM 형식
    break_duration: int = 60  # 분 단위
    timezone: str = "Asia/Seoul"
    days_of_week: List[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])  # 1=월, 7=일
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'start_time': self.start_time,
            'end_time': self.end_time,
            'break_duration': self.break_duration,
            'timezone': self.timezone,
            'days_of_week': self.days_of_week
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkingHours':
        """딕셔너리에서 생성"""
        return cls(
            start_time=data['start_time'],
            end_time=data['end_time'],
            break_duration=data.get('break_duration', 60),
            timezone=data.get('timezone', 'Asia/Seoul'),
            days_of_week=data.get('days_of_week', [1, 2, 3, 4, 5])
        )

@dataclass
class AgentPerformance:
    """상담원 성과 지표"""
    total_conversations: int = 0
    resolved_issues: int = 0
    escalated_issues: int = 0
    average_resolution_time: float = 0.0  # 분 단위
    customer_satisfaction_score: float = 0.0  # 1-5 점
    first_call_resolution_rate: float = 0.0  # 백분율
    utilization_rate: float = 0.0  # 백분율
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def calculate_resolution_rate(self) -> float:
        """해결률 계산"""
        if self.total_conversations == 0:
            return 0.0
        return (self.resolved_issues / self.total_conversations) * 100
    
    def calculate_escalation_rate(self) -> float:
        """에스컬레이션 비율 계산"""
        if self.total_conversations == 0:
            return 0.0
        return (self.escalated_issues / self.total_conversations) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            'total_conversations': self.total_conversations,
            'resolved_issues': self.resolved_issues,
            'escalated_issues': self.escalated_issues,
            'average_resolution_time': self.average_resolution_time,
            'customer_satisfaction_score': self.customer_satisfaction_score,
            'first_call_resolution_rate': self.first_call_resolution_rate,
            'utilization_rate': self.utilization_rate,
            'resolution_rate': self.calculate_resolution_rate(),
            'escalation_rate': self.calculate_escalation_rate(),
            'last_updated': self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentPerformance':
        """딕셔너리에서 생성"""
        return cls(
            total_conversations=data.get('total_conversations', 0),
            resolved_issues=data.get('resolved_issues', 0),
            escalated_issues=data.get('escalated_issues', 0),
            average_resolution_time=data.get('average_resolution_time', 0.0),
            customer_satisfaction_score=data.get('customer_satisfaction_score', 0.0),
            first_call_resolution_rate=data.get('first_call_resolution_rate', 0.0),
            utilization_rate=data.get('utilization_rate', 0.0),
            last_updated=data.get('last_updated', datetime.now().isoformat())
        )

@dataclass
class WorkSchedule:
    """근무 스케줄 정보"""
    schedule_id: str
    day_of_week: int  # 0: 월요일, 6: 일요일
    start_time: str  # "09:00" 형식
    end_time: str    # "18:00" 형식
    is_active: bool = True
    break_times: List[Dict[str, str]] = field(default_factory=list)  # [{"start": "12:00", "end": "13:00"}]

@dataclass
class AgentMetrics:
    """상담원 성과 메트릭"""
    # 통화 관련
    total_calls: int = 0
    total_call_duration: int = 0  # seconds
    average_call_duration: float = 0.0
    
    # 응답 관련
    total_answered_calls: int = 0
    total_missed_calls: int = 0
    answer_rate: float = 0.0
    average_response_time: float = 0.0  # seconds
    
    # 해결률 관련
    total_resolved_issues: int = 0
    total_escalated_issues: int = 0
    resolution_rate: float = 0.0
    first_call_resolution_rate: float = 0.0
    
    # 만족도 관련
    total_satisfaction_surveys: int = 0
    average_satisfaction_score: float = 0.0
    satisfaction_count_by_score: Dict[int, int] = field(default_factory=dict)  # {1: 0, 2: 1, ...}
    
    # 시간 관련
    total_work_time: int = 0  # seconds
    total_available_time: int = 0  # seconds
    total_busy_time: int = 0  # seconds
    total_break_time: int = 0  # seconds
    utilization_rate: float = 0.0
    
    # 품질 관련
    quality_score: float = 0.0
    quality_assessments: int = 0
    coaching_sessions: int = 0
    
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class Agent:
    """상담원 정보 관리 클래스"""
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        username: str = None,
        full_name: str = None,
        email: str = None,
        phone: str = None,
        tier: AgentTier = AgentTier.JUNIOR
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.username = username
        self.full_name = full_name
        self.email = email
        self.phone = phone
        self.tier = tier
        self.status = AgentStatus.OFFLINE
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.last_activity_at = datetime.now(timezone.utc)
        
        # 스킬 및 역량
        self.skills: Dict[str, AgentSkill] = {}
        self.languages: Set[str] = {"ko-KR"}  # 지원 언어
        self.certifications: List[str] = []
        
        # 근무 관련
        self.schedules: List[WorkSchedule] = []
        self.is_active: bool = True
        self.hire_date: Optional[datetime] = None
        self.department: Optional[str] = None
        self.team: Optional[str] = None
        self.supervisor_id: Optional[str] = None
        
        # 성과 및 통계
        self.metrics = AgentMetrics()
        self.current_session_start: Optional[datetime] = None
        self.status_history: List[Dict[str, Any]] = []
        
        # AWS Connect 관련
        self.connect_user_id: Optional[str] = None
        self.connect_routing_profile_id: Optional[str] = None
        self.connect_queue_ids: List[str] = []
        
        # 기타
        self.metadata: Dict[str, Any] = {}
        self.tags: List[str] = []
        self.notes: List[Dict[str, Any]] = []
    
    def add_skill(
        self, 
        skill_name: str, 
        level: SkillLevel, 
        priority: int = 1,
        certified: bool = False,
        certification_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None
    ) -> None:
        """스킬 추가"""
        skill = AgentSkill(
            skill_name=skill_name,
            level=level,
            priority=priority,
            certified=certified,
            certification_date=certification_date,
            expiry_date=expiry_date
        )
        self.skills[skill_name] = skill
        self.updated_at = datetime.now(timezone.utc)
    
    def update_skill_level(self, skill_name: str, level: SkillLevel) -> bool:
        """스킬 레벨 업데이트"""
        if skill_name in self.skills:
            self.skills[skill_name].level = level
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False
    
    def remove_skill(self, skill_name: str) -> bool:
        """스킬 제거"""
        if skill_name in self.skills:
            del self.skills[skill_name]
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False
    
    def get_skills_by_level(self, min_level: SkillLevel) -> List[AgentSkill]:
        """특정 레벨 이상의 스킬 조회"""
        return [
            skill for skill in self.skills.values() 
            if skill.level.value >= min_level.value and skill.is_valid()
        ]
    
    def has_skill(self, skill_name: str, min_level: SkillLevel = SkillLevel.BEGINNER) -> bool:
        """특정 스킬 보유 여부 확인"""
        if skill_name not in self.skills:
            return False
        
        skill = self.skills[skill_name]
        return skill.level.value >= min_level.value and skill.is_valid()
    
    def add_language(self, language_code: str) -> None:
        """지원 언어 추가"""
        self.languages.add(language_code)
        self.updated_at = datetime.now(timezone.utc)
    
    def remove_language(self, language_code: str) -> None:
        """지원 언어 제거"""
        self.languages.discard(language_code)
        self.updated_at = datetime.now(timezone.utc)
    
    def supports_language(self, language_code: str) -> bool:
        """언어 지원 여부 확인"""
        return language_code in self.languages
    
    def set_status(self, status: AgentStatus, reason: str = None) -> None:
        """상태 변경"""
        old_status = self.status
        self.status = status
        self.last_activity_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        
        # 상태 이력 기록
        status_change = {
            "from_status": old_status.value,
            "to_status": status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }
        self.status_history.append(status_change)
        
        # 세션 시작/종료 처리
        if status == AgentStatus.AVAILABLE and old_status == AgentStatus.OFFLINE:
            self.current_session_start = datetime.now(timezone.utc)
        elif status == AgentStatus.OFFLINE and old_status != AgentStatus.OFFLINE:
            if self.current_session_start:
                session_duration = (datetime.now(timezone.utc) - self.current_session_start).total_seconds()
                self.metrics.total_work_time += int(session_duration)
                self.current_session_start = None
    
    def is_available(self) -> bool:
        """응대 가능 상태 확인"""
        return self.status == AgentStatus.AVAILABLE and self.is_active
    
    def add_schedule(self, schedule: WorkSchedule) -> None:
        """근무 스케줄 추가"""
        self.schedules.append(schedule)
        self.updated_at = datetime.now(timezone.utc)
    
    def update_metrics(
        self,
        call_count: int = 0,
        call_duration: int = 0,
        answered_calls: int = 0,
        missed_calls: int = 0,
        resolved_issues: int = 0,
        escalated_issues: int = 0,
        satisfaction_score: Optional[float] = None,
        response_time: Optional[float] = None,
        quality_score: Optional[float] = None
    ) -> None:
        """성과 메트릭 업데이트"""
        metrics = self.metrics
        
        # 통화 관련
        metrics.total_calls += call_count
        metrics.total_call_duration += call_duration
        if metrics.total_calls > 0:
            metrics.average_call_duration = metrics.total_call_duration / metrics.total_calls
        
        # 응답 관련
        metrics.total_answered_calls += answered_calls
        metrics.total_missed_calls += missed_calls
        total_calls = metrics.total_answered_calls + metrics.total_missed_calls
        if total_calls > 0:
            metrics.answer_rate = metrics.total_answered_calls / total_calls
        
        if response_time is not None:
            # 평균 응답 시간 계산 (단순화)
            if metrics.total_answered_calls > 0:
                metrics.average_response_time = (
                    (metrics.average_response_time * (metrics.total_answered_calls - answered_calls)) + 
                    (response_time * answered_calls)
                ) / metrics.total_answered_calls
            else:
                metrics.average_response_time = response_time
        
        # 해결률 관련
        metrics.total_resolved_issues += resolved_issues
        metrics.total_escalated_issues += escalated_issues
        total_issues = metrics.total_resolved_issues + metrics.total_escalated_issues
        if total_issues > 0:
            metrics.resolution_rate = metrics.total_resolved_issues / total_issues
        
        # 만족도 관련
        if satisfaction_score is not None:
            metrics.total_satisfaction_surveys += 1
            # 평균 만족도 계산
            total_score = (
                metrics.average_satisfaction_score * 
                (metrics.total_satisfaction_surveys - 1)
            ) + satisfaction_score
            metrics.average_satisfaction_score = total_score / metrics.total_satisfaction_surveys
            
            # 점수별 카운트
            score_int = int(satisfaction_score)
            if score_int not in metrics.satisfaction_count_by_score:
                metrics.satisfaction_count_by_score[score_int] = 0
            metrics.satisfaction_count_by_score[score_int] += 1
        
        # 품질 점수
        if quality_score is not None:
            metrics.quality_assessments += 1
            # 평균 품질 점수 계산
            total_quality = (
                metrics.quality_score * (metrics.quality_assessments - 1)
            ) + quality_score
            metrics.quality_score = total_quality / metrics.quality_assessments
        
        metrics.last_updated = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def get_performance_score(self) -> float:
        """종합 성과 점수 계산 (0-100)"""
        metrics = self.metrics
        score = 0.0
        weights = {
            "answer_rate": 0.2,
            "resolution_rate": 0.25,
            "satisfaction": 0.25,
            "quality": 0.2,
            "utilization": 0.1
        }
        
        # 응답률 점수
        score += metrics.answer_rate * 100 * weights["answer_rate"]
        
        # 해결률 점수
        score += metrics.resolution_rate * 100 * weights["resolution_rate"]
        
        # 만족도 점수 (5점 만점을 100점으로 환산)
        satisfaction_score = (metrics.average_satisfaction_score / 5.0) * 100
        score += satisfaction_score * weights["satisfaction"]
        
        # 품질 점수
        score += metrics.quality_score * weights["quality"]
        
        # 활용률 점수
        score += metrics.utilization_rate * 100 * weights["utilization"]
        
        return min(100.0, max(0.0, score))
    
    def add_note(self, note: str, author: str, category: str = "general") -> None:
        """노트 추가"""
        note_entry = {
            "id": str(uuid.uuid4()),
            "content": note,
            "author": author,
            "category": category,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.notes.append(note_entry)
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
    
    def get_skill_match_score(self, required_skills: List[Dict[str, Any]]) -> float:
        """요구 스킬과의 매칭 점수 계산 (0-100)"""
        if not required_skills:
            return 100.0
        
        total_score = 0.0
        total_weight = 0.0
        
        for req_skill in required_skills:
            skill_name = req_skill.get("name")
            required_level = SkillLevel(req_skill.get("level", 1))
            weight = req_skill.get("weight", 1.0)
            
            if self.has_skill(skill_name, required_level):
                agent_skill = self.skills[skill_name]
                # 레벨이 높을수록 높은 점수
                level_score = min(100, (agent_skill.level.value / required_level.value) * 100)
                total_score += level_score * weight
            else:
                # 스킬이 없거나 레벨이 부족한 경우
                total_score += 0
            
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "agent_id": self.agent_id,
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "tier": self.tier.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
            "skills": {
                name: {
                    "skill_name": skill.skill_name,
                    "level": skill.level.value,
                    "priority": skill.priority,
                    "certified": skill.certified,
                    "certification_date": skill.certification_date.isoformat() if skill.certification_date else None,
                    "expiry_date": skill.expiry_date.isoformat() if skill.expiry_date else None,
                    "created_at": skill.created_at.isoformat()
                }
                for name, skill in self.skills.items()
            },
            "languages": list(self.languages),
            "certifications": self.certifications,
            "schedules": [
                {
                    "schedule_id": schedule.schedule_id,
                    "day_of_week": schedule.day_of_week,
                    "start_time": schedule.start_time,
                    "end_time": schedule.end_time,
                    "is_active": schedule.is_active,
                    "break_times": schedule.break_times
                }
                for schedule in self.schedules
            ],
            "is_active": self.is_active,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "department": self.department,
            "team": self.team,
            "supervisor_id": self.supervisor_id,
            "metrics": {
                "total_calls": self.metrics.total_calls,
                "total_call_duration": self.metrics.total_call_duration,
                "average_call_duration": self.metrics.average_call_duration,
                "total_answered_calls": self.metrics.total_answered_calls,
                "total_missed_calls": self.metrics.total_missed_calls,
                "answer_rate": self.metrics.answer_rate,
                "average_response_time": self.metrics.average_response_time,
                "total_resolved_issues": self.metrics.total_resolved_issues,
                "total_escalated_issues": self.metrics.total_escalated_issues,
                "resolution_rate": self.metrics.resolution_rate,
                "first_call_resolution_rate": self.metrics.first_call_resolution_rate,
                "total_satisfaction_surveys": self.metrics.total_satisfaction_surveys,
                "average_satisfaction_score": self.metrics.average_satisfaction_score,
                "satisfaction_count_by_score": self.metrics.satisfaction_count_by_score,
                "total_work_time": self.metrics.total_work_time,
                "total_available_time": self.metrics.total_available_time,
                "total_busy_time": self.metrics.total_busy_time,
                "total_break_time": self.metrics.total_break_time,
                "utilization_rate": self.metrics.utilization_rate,
                "quality_score": self.metrics.quality_score,
                "quality_assessments": self.metrics.quality_assessments,
                "coaching_sessions": self.metrics.coaching_sessions,
                "last_updated": self.metrics.last_updated.isoformat()
            },
            "current_session_start": self.current_session_start.isoformat() if self.current_session_start else None,
            "status_history": self.status_history,
            "connect_user_id": self.connect_user_id,
            "connect_routing_profile_id": self.connect_routing_profile_id,
            "connect_queue_ids": self.connect_queue_ids,
            "metadata": self.metadata,
            "tags": self.tags,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Agent':
        """딕셔너리에서 Agent 객체 생성"""
        agent = cls(
            agent_id=data["agent_id"],
            username=data.get("username"),
            full_name=data.get("full_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            tier=AgentTier(data.get("tier", "junior"))
        )
        
        agent.status = AgentStatus(data["status"])
        agent.created_at = datetime.fromisoformat(data["created_at"])
        agent.updated_at = datetime.fromisoformat(data["updated_at"])
        agent.last_activity_at = datetime.fromisoformat(data["last_activity_at"])
        
        # 스킬 복원
        agent.skills = {}
        for name, skill_data in data.get("skills", {}).items():
            skill = AgentSkill(
                skill_name=skill_data["skill_name"],
                level=SkillLevel(skill_data["level"]),
                priority=skill_data["priority"],
                certified=skill_data["certified"],
                created_at=datetime.fromisoformat(skill_data["created_at"])
            )
            if skill_data.get("certification_date"):
                skill.certification_date = datetime.fromisoformat(skill_data["certification_date"])
            if skill_data.get("expiry_date"):
                skill.expiry_date = datetime.fromisoformat(skill_data["expiry_date"])
            agent.skills[name] = skill
        
        agent.languages = set(data.get("languages", ["ko-KR"]))
        agent.certifications = data.get("certifications", [])
        
        # 스케줄 복원
        agent.schedules = []
        for schedule_data in data.get("schedules", []):
            schedule = WorkSchedule(
                schedule_id=schedule_data["schedule_id"],
                day_of_week=schedule_data["day_of_week"],
                start_time=schedule_data["start_time"],
                end_time=schedule_data["end_time"],
                is_active=schedule_data["is_active"],
                break_times=schedule_data["break_times"]
            )
            agent.schedules.append(schedule)
        
        agent.is_active = data.get("is_active", True)
        if data.get("hire_date"):
            agent.hire_date = datetime.fromisoformat(data["hire_date"])
        agent.department = data.get("department")
        agent.team = data.get("team")
        agent.supervisor_id = data.get("supervisor_id")
        
        # 메트릭 복원
        if "metrics" in data:
            metrics_data = data["metrics"]
            agent.metrics = AgentMetrics(
                total_calls=metrics_data["total_calls"],
                total_call_duration=metrics_data["total_call_duration"],
                average_call_duration=metrics_data["average_call_duration"],
                total_answered_calls=metrics_data["total_answered_calls"],
                total_missed_calls=metrics_data["total_missed_calls"],
                answer_rate=metrics_data["answer_rate"],
                average_response_time=metrics_data["average_response_time"],
                total_resolved_issues=metrics_data["total_resolved_issues"],
                total_escalated_issues=metrics_data["total_escalated_issues"],
                resolution_rate=metrics_data["resolution_rate"],
                first_call_resolution_rate=metrics_data["first_call_resolution_rate"],
                total_satisfaction_surveys=metrics_data["total_satisfaction_surveys"],
                average_satisfaction_score=metrics_data["average_satisfaction_score"],
                satisfaction_count_by_score=metrics_data["satisfaction_count_by_score"],
                total_work_time=metrics_data["total_work_time"],
                total_available_time=metrics_data["total_available_time"],
                total_busy_time=metrics_data["total_busy_time"],
                total_break_time=metrics_data["total_break_time"],
                utilization_rate=metrics_data["utilization_rate"],
                quality_score=metrics_data["quality_score"],
                quality_assessments=metrics_data["quality_assessments"],
                coaching_sessions=metrics_data["coaching_sessions"],
                last_updated=datetime.fromisoformat(metrics_data["last_updated"])
            )
        
        if data.get("current_session_start"):
            agent.current_session_start = datetime.fromisoformat(data["current_session_start"])
        
        agent.status_history = data.get("status_history", [])
        agent.connect_user_id = data.get("connect_user_id")
        agent.connect_routing_profile_id = data.get("connect_routing_profile_id")
        agent.connect_queue_ids = data.get("connect_queue_ids", [])
        agent.metadata = data.get("metadata", {})
        agent.tags = data.get("tags", [])
        agent.notes = data.get("notes", [])
        
        return agent 