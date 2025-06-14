"""
설정 관리 시스템
AWS Connect 콜센터 애플리케이션을 위한 통합 설정 관리
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, Union, List
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import logging
from functools import lru_cache


class Environment(Enum):
    """실행 환경"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class AWSConfig:
    """AWS 서비스 설정"""
    region: str = "ap-northeast-2"
    profile_name: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    
    # AWS Connect 설정
    connect_instance_id: Optional[str] = None
    connect_instance_arn: Optional[str] = None
    
    # DynamoDB 설정
    dynamodb_tables: Dict[str, str] = field(default_factory=lambda: {
        'conversations': 'aicc-conversations',
        'users': 'aicc-users',
        'agents': 'aicc-agents',
        'faq': 'aicc-faq',
        'metrics': 'aicc-metrics'
    })
    
    # S3 설정
    s3_buckets: Dict[str, str] = field(default_factory=lambda: {
        'recordings': 'aicc-call-recordings',
        'reports': 'aicc-reports',
        'backups': 'aicc-backups'
    })
    
    # Lex 설정
    lex_bot_name: str = "AICC_ChatBot"
    lex_bot_alias: str = "PROD"
    lex_v2_bot_id: Optional[str] = None
    lex_v2_bot_alias_id: str = "TSTALIASID"
    lex_locale_id: str = "ko_KR"
    
    # CloudWatch 설정
    cloudwatch_log_group: str = "/aws/lambda/aicc-chatbot"
    cloudwatch_metrics_namespace: str = "AICC/ChatBot"


@dataclass
class DatabaseConfig:
    """데이터베이스 설정"""
    # DynamoDB 설정은 AWSConfig에 포함
    # 필요시 RDS 등 다른 DB 설정 추가 가능
    
    # 연결 풀 설정
    max_connections: int = 20
    connection_timeout: int = 30
    read_timeout: int = 10
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class ChatbotConfig:
    """챗봇 서비스 설정"""
    # NLU 설정
    confidence_threshold: float = 0.7
    intent_confidence_threshold: float = 0.8
    entity_confidence_threshold: float = 0.6
    
    # 대화 관리
    session_timeout_minutes: int = 30
    max_conversation_turns: int = 50
    
    # 응답 설정
    default_language: str = "ko-KR"
    supported_languages: List[str] = field(default_factory=lambda: ["ko-KR", "en-US"])
    
    # 에스컬레이션 설정
    max_escalation_attempts: int = 3
    escalation_timeout_seconds: int = 300
    
    # FAQ 설정
    faq_similarity_threshold: float = 0.8
    max_faq_results: int = 5
    
    # 시나리오 설정
    scenario_timeout_minutes: int = 15
    max_scenario_steps: int = 20


@dataclass
class APIConfig:
    """API 서버 설정"""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # CORS 설정
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    cors_headers: List[str] = field(default_factory=lambda: ["*"])
    
    # 보안 설정
    secret_key: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    
    # 요청 제한
    rate_limit_per_minute: int = 100
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    
    # 웹훅 설정
    webhook_timeout_seconds: int = 30
    webhook_retry_attempts: int = 3


@dataclass
class LoggingConfig:
    """로깅 설정"""
    level: str = "INFO"
    format: str = "json"  # json, text
    
    # 파일 로깅
    enable_file_logging: bool = True
    log_directory: str = "logs"
    max_file_size_mb: int = 10
    backup_count: int = 5
    
    # 콘솔 로깅
    enable_console_logging: bool = True
    
    # CloudWatch 로깅
    enable_cloudwatch_logging: bool = False
    
    # 성능 로깅
    log_performance: bool = True
    slow_query_threshold_seconds: float = 1.0


@dataclass
class MonitoringConfig:
    """모니터링 및 메트릭 설정"""
    # 메트릭 수집
    enable_metrics: bool = True
    metrics_interval_seconds: int = 60
    
    # 헬스체크
    health_check_interval_seconds: int = 30
    
    # 알림 설정
    enable_alerts: bool = False
    alert_email: Optional[str] = None
    alert_sns_topic_arn: Optional[str] = None
    
    # 임계값 설정
    error_rate_threshold: float = 0.05  # 5%
    response_time_threshold_ms: float = 1000  # 1초
    availability_threshold: float = 0.99  # 99%


class ConfigManager:
    """설정 관리 클래스"""
    
    def __init__(
        self,
        env: Optional[Union[str, Environment]] = None,
        config_dir: Union[str, Path] = "config",
        config_file: Optional[str] = None
    ):
        # 환경 설정
        if isinstance(env, str):
            self.env = Environment(env)
        elif isinstance(env, Environment):
            self.env = env
        else:
            self.env = Environment(os.getenv('ENVIRONMENT', 'development'))
        
        self.config_dir = Path(config_dir)
        self.config_file = config_file
        
        # 설정 로드
        self._config_data = self._load_config()
        
        # 설정 객체 생성
        self.aws = self._create_aws_config()
        self.database = self._create_database_config()
        self.chatbot = self._create_chatbot_config()
        self.api = self._create_api_config()
        self.logging = self._create_logging_config()
        self.monitoring = self._create_monitoring_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        config_data = {}
        
        # 기본 설정 파일 로드
        base_config_file = self.config_dir / "config.yaml"
        if base_config_file.exists():
            config_data.update(self._load_yaml_file(base_config_file))
        
        # 환경별 설정 파일 로드
        env_config_file = self.config_dir / f"config.{self.env.value}.yaml"
        if env_config_file.exists():
            config_data.update(self._load_yaml_file(env_config_file))
        
        # 특정 설정 파일 로드
        if self.config_file:
            specific_config_file = Path(self.config_file)
            if specific_config_file.exists():
                config_data.update(self._load_file(specific_config_file))
        
        # 환경 변수로 덮어쓰기
        config_data = self._override_with_env_vars(config_data)
        
        return config_data
    
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """YAML 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.warning(f"설정 파일 로드 실패: {file_path} - {e}")
            return {}
    
    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """JSON 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"설정 파일 로드 실패: {file_path} - {e}")
            return {}
    
    def _load_file(self, file_path: Path) -> Dict[str, Any]:
        """파일 확장자에 따라 적절한 로더 선택"""
        if file_path.suffix.lower() in ['.yaml', '.yml']:
            return self._load_yaml_file(file_path)
        elif file_path.suffix.lower() == '.json':
            return self._load_json_file(file_path)
        else:
            logging.warning(f"지원하지 않는 설정 파일 형식: {file_path}")
            return {}
    
    def _override_with_env_vars(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """환경 변수로 설정 덮어쓰기"""
        # AWS 설정
        if os.getenv('AWS_REGION'):
            config_data.setdefault('aws', {})['region'] = os.getenv('AWS_REGION')
        
        if os.getenv('AWS_PROFILE'):
            config_data.setdefault('aws', {})['profile_name'] = os.getenv('AWS_PROFILE')
        
        if os.getenv('AWS_ACCESS_KEY_ID'):
            config_data.setdefault('aws', {})['access_key_id'] = os.getenv('AWS_ACCESS_KEY_ID')
        
        if os.getenv('AWS_SECRET_ACCESS_KEY'):
            config_data.setdefault('aws', {})['secret_access_key'] = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if os.getenv('CONNECT_INSTANCE_ID'):
            config_data.setdefault('aws', {})['connect_instance_id'] = os.getenv('CONNECT_INSTANCE_ID')
        
        # API 설정
        if os.getenv('API_HOST'):
            config_data.setdefault('api', {})['host'] = os.getenv('API_HOST')
        
        if os.getenv('API_PORT'):
            config_data.setdefault('api', {})['port'] = int(os.getenv('API_PORT'))
        
        if os.getenv('API_SECRET_KEY'):
            config_data.setdefault('api', {})['secret_key'] = os.getenv('API_SECRET_KEY')
        
        # 로깅 설정
        if os.getenv('LOG_LEVEL'):
            config_data.setdefault('logging', {})['level'] = os.getenv('LOG_LEVEL')
        
        return config_data
    
    def _create_aws_config(self) -> AWSConfig:
        """AWS 설정 객체 생성"""
        aws_data = self._config_data.get('aws', {})
        return AWSConfig(**{k: v for k, v in aws_data.items() if hasattr(AWSConfig, k)})
    
    def _create_database_config(self) -> DatabaseConfig:
        """데이터베이스 설정 객체 생성"""
        db_data = self._config_data.get('database', {})
        return DatabaseConfig(**{k: v for k, v in db_data.items() if hasattr(DatabaseConfig, k)})
    
    def _create_chatbot_config(self) -> ChatbotConfig:
        """챗봇 설정 객체 생성"""
        chatbot_data = self._config_data.get('chatbot', {})
        return ChatbotConfig(**{k: v for k, v in chatbot_data.items() if hasattr(ChatbotConfig, k)})
    
    def _create_api_config(self) -> APIConfig:
        """API 설정 객체 생성"""
        api_data = self._config_data.get('api', {})
        return APIConfig(**{k: v for k, v in api_data.items() if hasattr(APIConfig, k)})
    
    def _create_logging_config(self) -> LoggingConfig:
        """로깅 설정 객체 생성"""
        logging_data = self._config_data.get('logging', {})
        return LoggingConfig(**{k: v for k, v in logging_data.items() if hasattr(LoggingConfig, k)})
    
    def _create_monitoring_config(self) -> MonitoringConfig:
        """모니터링 설정 객체 생성"""
        monitoring_data = self._config_data.get('monitoring', {})
        return MonitoringConfig(**{k: v for k, v in monitoring_data.items() if hasattr(MonitoringConfig, k)})
    
    def get(self, key: str, default: Any = None) -> Any:
        """중첩된 키로 설정값 가져오기 (예: 'aws.region')"""
        keys = key.split('.')
        value = self._config_data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """중첩된 키로 설정값 설정하기"""
        keys = key.split('.')
        target = self._config_data
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """전체 설정을 딕셔너리로 반환"""
        return {
            'environment': self.env.value,
            'aws': self.aws.__dict__,
            'database': self.database.__dict__,
            'chatbot': self.chatbot.__dict__,
            'api': self.api.__dict__,
            'logging': self.logging.__dict__,
            'monitoring': self.monitoring.__dict__
        }
    
    def save_config(self, file_path: Optional[Union[str, Path]] = None) -> bool:
        """현재 설정을 파일로 저장"""
        if not file_path:
            file_path = self.config_dir / f"config.{self.env.value}.yaml"
        
        file_path = Path(file_path)
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)
            
            logging.info(f"설정 파일 저장 완료: {file_path}")
            return True
            
        except Exception as e:
            logging.error(f"설정 파일 저장 실패: {e}")
            return False
    
    def validate_config(self) -> List[str]:
        """설정 검증"""
        errors = []
        
        # AWS 설정 검증
        if not self.aws.region:
            errors.append("AWS region이 설정되지 않았습니다.")
        
        if not self.aws.connect_instance_id and self.env != Environment.TEST:
            errors.append("AWS Connect Instance ID가 설정되지 않았습니다.")
        
        # API 설정 검증
        if self.env == Environment.PRODUCTION and self.api.secret_key == "your-secret-key-change-in-production":
            errors.append("운영 환경에서 기본 시크릿 키를 사용하고 있습니다.")
        
        if self.api.port < 1 or self.api.port > 65535:
            errors.append(f"잘못된 API 포트 번호: {self.api.port}")
        
        # 챗봇 설정 검증
        if not (0.0 <= self.chatbot.confidence_threshold <= 1.0):
            errors.append(f"잘못된 신뢰도 임계값: {self.chatbot.confidence_threshold}")
        
        return errors
    
    def is_development(self) -> bool:
        """개발 환경 여부"""
        return self.env == Environment.DEVELOPMENT
    
    def is_production(self) -> bool:
        """운영 환경 여부"""
        return self.env == Environment.PRODUCTION
    
    def is_test(self) -> bool:
        """테스트 환경 여부"""
        return self.env == Environment.TEST


# 전역 설정 인스턴스
_config_manager: Optional[ConfigManager] = None


@lru_cache(maxsize=1)
def get_config(
    env: Optional[Union[str, Environment]] = None,
    config_dir: Union[str, Path] = "config",
    config_file: Optional[str] = None
) -> ConfigManager:
    """설정 관리자 인스턴스 가져오기 (싱글톤)"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager(
            env=env,
            config_dir=config_dir,
            config_file=config_file
        )
        
        # 설정 검증
        validation_errors = _config_manager.validate_config()
        if validation_errors:
            logging.warning(f"설정 검증 오류: {validation_errors}")
    
    return _config_manager


def init_config(
    env: Optional[Union[str, Environment]] = None,
    config_dir: Union[str, Path] = "config",
    config_file: Optional[str] = None
) -> ConfigManager:
    """설정 초기화"""
    global _config_manager
    
    # 캐시 클리어
    get_config.cache_clear()
    
    _config_manager = ConfigManager(
        env=env,
        config_dir=config_dir,
        config_file=config_file
    )
    
    return _config_manager


# 편의 함수들
def get_aws_config() -> AWSConfig:
    """AWS 설정 가져오기"""
    return get_config().aws


def get_database_config() -> DatabaseConfig:
    """데이터베이스 설정 가져오기"""
    return get_config().database


def get_chatbot_config() -> ChatbotConfig:
    """챗봇 설정 가져오기"""
    return get_config().chatbot


def get_api_config() -> APIConfig:
    """API 설정 가져오기"""
    return get_config().api


def get_logging_config() -> LoggingConfig:
    """로깅 설정 가져오기"""
    return get_config().logging


def get_monitoring_config() -> MonitoringConfig:
    """모니터링 설정 가져오기"""
    return get_config().monitoring


def is_development() -> bool:
    """개발 환경 여부"""
    return get_config().is_development()


def is_production() -> bool:
    """운영 환경 여부"""
    return get_config().is_production()


def is_test() -> bool:
    """테스트 환경 여부"""
    return get_config().is_test() 