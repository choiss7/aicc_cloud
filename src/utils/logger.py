"""
로깅 시스템 설정 및 관리
AWS Connect 콜센터 애플리케이션을 위한 통합 로깅 시스템
"""

import logging
import logging.handlers
import json
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union
from pathlib import Path
import traceback
from functools import wraps


class JSONFormatter(logging.Formatter):
    """JSON 형식 로그 포매터"""
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드를 JSON 형식으로 포매팅"""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # 스레드 정보 추가
        if hasattr(record, 'thread') and record.thread:
            log_entry['thread_id'] = record.thread
            log_entry['thread_name'] = record.threadName
        
        # 프로세스 정보 추가
        if hasattr(record, 'process') and record.process:
            log_entry['process_id'] = record.process
        
        # 예외 정보 추가
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # 추가 컨텍스트 정보
        if self.include_extra:
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                              'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                              'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                              'thread', 'threadName', 'processName', 'process', 'getMessage']:
                    extra_fields[key] = value
            
            if extra_fields:
                log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ContextualFilter(logging.Filter):
    """컨텍스트 정보를 로그에 추가하는 필터"""
    
    def __init__(self, context: Dict[str, Any] = None):
        super().__init__()
        self.context = context or {}
    
    def filter(self, record: logging.LogRecord) -> bool:
        """로그 레코드에 컨텍스트 정보 추가"""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True
    
    def update_context(self, **kwargs):
        """컨텍스트 업데이트"""
        self.context.update(kwargs)
    
    def clear_context(self):
        """컨텍스트 초기화"""
        self.context.clear()


class CloudWatchHandler(logging.Handler):
    """AWS CloudWatch Logs 핸들러"""
    
    def __init__(
        self,
        log_group: str,
        log_stream: str,
        aws_client_manager=None,
        buffer_size: int = 100,
        flush_interval: int = 60
    ):
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.sequence_token = None
        self.last_flush = datetime.now()
        
        # CloudWatch 클라이언트 초기화
        if aws_client_manager:
            try:
                from .aws_client import CloudWatchClient
                self.cloudwatch = CloudWatchClient(aws_client_manager)
                self._ensure_log_group_exists()
                self._ensure_log_stream_exists()
                self.enabled = True
            except Exception as e:
                print(f"CloudWatch 핸들러 초기화 실패: {e}")
                self.enabled = False
        else:
            self.enabled = False
    
    def _ensure_log_group_exists(self):
        """로그 그룹 존재 확인 및 생성"""
        try:
            self.cloudwatch.create_log_group(self.log_group)
        except Exception as e:
            print(f"로그 그룹 생성 실패: {e}")
    
    def _ensure_log_stream_exists(self):
        """로그 스트림 존재 확인 및 생성"""
        try:
            self.cloudwatch.logs_client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except Exception as e:
            # 이미 존재하는 경우는 무시
            if 'ResourceAlreadyExistsException' not in str(e):
                print(f"로그 스트림 생성 실패: {e}")
    
    def emit(self, record: logging.LogRecord):
        """로그 레코드 처리"""
        if not self.enabled:
            return
        
        try:
            log_event = {
                'timestamp': int(record.created * 1000),  # milliseconds
                'message': self.format(record)
            }
            
            self.buffer.append(log_event)
            
            # 버퍼가 가득 찼거나 일정 시간이 지나면 플러시
            now = datetime.now()
            if (len(self.buffer) >= self.buffer_size or 
                (now - self.last_flush).seconds >= self.flush_interval):
                self.flush()
                
        except Exception as e:
            self.handleError(record)
    
    def flush(self):
        """버퍼의 로그를 CloudWatch로 전송"""
        if not self.enabled or not self.buffer:
            return
        
        try:
            # 타임스탬프 순으로 정렬
            self.buffer.sort(key=lambda x: x['timestamp'])
            
            self.sequence_token = self.cloudwatch.put_log_events(
                log_group_name=self.log_group,
                log_stream_name=self.log_stream,
                log_events=self.buffer,
                sequence_token=self.sequence_token
            )
            
            self.buffer.clear()
            self.last_flush = datetime.now()
            
        except Exception as e:
            print(f"CloudWatch 로그 전송 실패: {e}")
    
    def close(self):
        """핸들러 종료 시 버퍼 플러시"""
        self.flush()
        super().close()


class LoggerManager:
    """로거 관리 클래스"""
    
    def __init__(
        self,
        app_name: str = "aicc_chatbot",
        log_level: str = "INFO",
        log_dir: str = "logs",
        enable_console: bool = True,
        enable_file: bool = True,
        enable_cloudwatch: bool = False,
        cloudwatch_log_group: Optional[str] = None,
        aws_client_manager=None
    ):
        self.app_name = app_name
        self.log_level = getattr(logging, log_level.upper())
        self.log_dir = Path(log_dir)
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.enable_cloudwatch = enable_cloudwatch
        self.cloudwatch_log_group = cloudwatch_log_group or f"/aws/lambda/{app_name}"
        self.aws_client_manager = aws_client_manager
        
        # 로그 디렉토리 생성
        if self.enable_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 글로벌 컨텍스트 필터
        self.context_filter = ContextualFilter({
            'app_name': app_name,
            'environment': os.getenv('ENVIRONMENT', 'development')
        })
        
        # 루트 로거 설정
        self._setup_root_logger()
    
    def _setup_root_logger(self):
        """루트 로거 설정"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # 기존 핸들러 제거
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 콘솔 핸들러 추가
        if self.enable_console:
            self._add_console_handler(root_logger)
        
        # 파일 핸들러 추가
        if self.enable_file:
            self._add_file_handlers(root_logger)
        
        # CloudWatch 핸들러 추가
        if self.enable_cloudwatch and self.aws_client_manager:
            self._add_cloudwatch_handler(root_logger)
        
        # 글로벌 필터 추가
        root_logger.addFilter(self.context_filter)
    
    def _add_console_handler(self, logger: logging.Logger):
        """콘솔 핸들러 추가"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        
        # 개발 환경에서는 간단한 포맷, 운영에서는 JSON 포맷
        if os.getenv('ENVIRONMENT') == 'development':
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        else:
            console_formatter = JSONFormatter()
        
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    def _add_file_handlers(self, logger: logging.Logger):
        """파일 핸들러 추가"""
        # 일반 로그 파일
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.app_name}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        
        # 에러 로그 파일 (ERROR 이상만)
        error_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.app_name}_error.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
    
    def _add_cloudwatch_handler(self, logger: logging.Logger):
        """CloudWatch 핸들러 추가"""
        try:
            log_stream = f"{self.app_name}-{datetime.now().strftime('%Y-%m-%d')}"
            cloudwatch_handler = CloudWatchHandler(
                log_group=self.cloudwatch_log_group,
                log_stream=log_stream,
                aws_client_manager=self.aws_client_manager
            )
            cloudwatch_handler.setLevel(self.log_level)
            cloudwatch_handler.setFormatter(JSONFormatter())
            logger.addHandler(cloudwatch_handler)
        except Exception as e:
            print(f"CloudWatch 핸들러 추가 실패: {e}")
    
    def get_logger(self, name: str) -> logging.Logger:
        """특정 이름의 로거 가져오기"""
        return logging.getLogger(name)
    
    def set_context(self, **kwargs):
        """글로벌 로그 컨텍스트 설정"""
        self.context_filter.update_context(**kwargs)
    
    def clear_context(self):
        """글로벌 로그 컨텍스트 초기화"""
        self.context_filter.clear_context()
    
    def set_log_level(self, level: str):
        """로그 레벨 변경"""
        new_level = getattr(logging, level.upper())
        logging.getLogger().setLevel(new_level)
        
        # 모든 핸들러의 레벨도 변경
        for handler in logging.getLogger().handlers:
            if not isinstance(handler, logging.handlers.RotatingFileHandler) or 'error' not in handler.baseFilename:
                handler.setLevel(new_level)


# 전역 로거 매니저 인스턴스
_logger_manager: Optional[LoggerManager] = None


def init_logging(
    app_name: str = "aicc_chatbot",
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_console: bool = True,
    enable_file: bool = True,
    enable_cloudwatch: bool = False,
    cloudwatch_log_group: Optional[str] = None,
    aws_client_manager=None
) -> LoggerManager:
    """로깅 시스템 초기화"""
    global _logger_manager
    
    _logger_manager = LoggerManager(
        app_name=app_name,
        log_level=log_level,
        log_dir=log_dir,
        enable_console=enable_console,
        enable_file=enable_file,
        enable_cloudwatch=enable_cloudwatch,
        cloudwatch_log_group=cloudwatch_log_group,
        aws_client_manager=aws_client_manager
    )
    
    return _logger_manager


def get_logger(name: str = None) -> logging.Logger:
    """로거 인스턴스 가져오기"""
    if _logger_manager is None:
        # 기본 설정으로 초기화
        init_logging()
    
    if name:
        return _logger_manager.get_logger(name)
    else:
        return logging.getLogger()


def log_function_call(logger: logging.Logger = None):
    """함수 호출 로깅 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or get_logger(func.__module__)
            
            # 함수 시작 로깅
            func_logger.debug(
                f"함수 호출 시작: {func.__name__}",
                extra={
                    'function': func.__name__,
                    'module': func.__module__,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys())
                }
            )
            
            start_time = datetime.now()
            
            try:
                result = func(*args, **kwargs)
                
                # 성공 로깅
                execution_time = (datetime.now() - start_time).total_seconds()
                func_logger.debug(
                    f"함수 호출 완료: {func.__name__}",
                    extra={
                        'function': func.__name__,
                        'module': func.__module__,
                        'execution_time': execution_time,
                        'status': 'success'
                    }
                )
                
                return result
                
            except Exception as e:
                # 예외 로깅
                execution_time = (datetime.now() - start_time).total_seconds()
                func_logger.error(
                    f"함수 호출 실패: {func.__name__}",
                    exc_info=True,
                    extra={
                        'function': func.__name__,
                        'module': func.__module__,
                        'execution_time': execution_time,
                        'status': 'error',
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                )
                raise
        
        return wrapper
    return decorator


def log_with_context(**context_kwargs):
    """컨텍스트와 함께 로깅하는 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 임시 컨텍스트 설정
            if _logger_manager:
                old_context = _logger_manager.context_filter.context.copy()
                _logger_manager.set_context(**context_kwargs)
            
            try:
                return func(*args, **kwargs)
            finally:
                # 컨텍스트 복원
                if _logger_manager:
                    _logger_manager.context_filter.context = old_context
        
        return wrapper
    return decorator


# 편의 함수들
def debug(message: str, **kwargs):
    """디버그 로그"""
    get_logger().debug(message, extra=kwargs)


def info(message: str, **kwargs):
    """정보 로그"""
    get_logger().info(message, extra=kwargs)


def warning(message: str, **kwargs):
    """경고 로그"""
    get_logger().warning(message, extra=kwargs)


def error(message: str, exc_info: bool = False, **kwargs):
    """에러 로그"""
    get_logger().error(message, exc_info=exc_info, extra=kwargs)


def critical(message: str, exc_info: bool = True, **kwargs):
    """크리티컬 로그"""
    get_logger().critical(message, exc_info=exc_info, extra=kwargs)


# 특수 로거들
def get_performance_logger() -> logging.Logger:
    """성능 측정용 로거"""
    return get_logger('performance')


def get_security_logger() -> logging.Logger:
    """보안 이벤트용 로거"""
    return get_logger('security')


def get_audit_logger() -> logging.Logger:
    """감사 로그용 로거"""
    return get_logger('audit') 