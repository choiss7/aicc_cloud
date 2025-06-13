"""
외부 연동 서비스
CRM, ERP, 결제 시스템, SMS/Email, 소셜 미디어 연동
API Gateway, 웹훅, 메시지 큐 관리
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import boto3
import aioredis
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import structlog

# 로깅 설정
logger = structlog.get_logger(__name__)

Base = declarative_base()

class IntegrationType(Enum):
    CRM = "crm"
    ERP = "erp"
    PAYMENT = "payment"
    SMS = "sms"
    EMAIL = "email"
    SOCIAL_MEDIA = "social_media"
    WEBHOOK = "webhook"
    API = "api"

class IntegrationStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING = "pending"

class MessageType(Enum):
    SYNC = "sync"
    ASYNC = "async"
    WEBHOOK = "webhook"
    BATCH = "batch"

@dataclass
class IntegrationConfig:
    """연동 설정"""
    integration_id: str
    name: str
    type: IntegrationType
    endpoint_url: str
    auth_type: str  # api_key, oauth2, basic, bearer
    auth_config: Dict[str, Any]
    headers: Dict[str, str] = None
    timeout: int = 30
    retry_count: int = 3
    rate_limit: int = 100  # requests per minute
    enabled: bool = True

@dataclass
class IntegrationMessage:
    """연동 메시지"""
    message_id: str
    integration_id: str
    message_type: MessageType
    payload: Dict[str, Any]
    headers: Dict[str, str] = None
    timestamp: datetime = None
    retry_count: int = 0
    max_retries: int = 3
    status: str = "pending"

class Integration(Base):
    """연동 설정 모델"""
    __tablename__ = 'integrations'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    endpoint_url = Column(String, nullable=False)
    
    auth_type = Column(String, nullable=False)
    auth_config = Column(Text)  # JSON
    headers = Column(Text)  # JSON
    
    timeout = Column(Integer, default=30)
    retry_count = Column(Integer, default=3)
    rate_limit = Column(Integer, default=100)
    
    status = Column(String, default=IntegrationStatus.ACTIVE.value)
    enabled = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 통계
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    last_request_at = Column(DateTime)

class IntegrationLog(Base):
    """연동 로그 모델"""
    __tablename__ = 'integration_logs'
    
    id = Column(String, primary_key=True)
    integration_id = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False, index=True)
    
    request_method = Column(String)
    request_url = Column(String)
    request_headers = Column(Text)  # JSON
    request_body = Column(Text)
    
    response_status = Column(Integer)
    response_headers = Column(Text)  # JSON
    response_body = Column(Text)
    
    duration_ms = Column(Integer)
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class AuthManager:
    """인증 관리자"""
    
    def __init__(self):
        self.token_cache = {}
    
    async def get_auth_headers(self, config: IntegrationConfig) -> Dict[str, str]:
        """인증 헤더 생성"""
        auth_type = config.auth_type
        auth_config = config.auth_config
        
        if auth_type == "api_key":
            return {auth_config.get("header_name", "X-API-Key"): auth_config["api_key"]}
        
        elif auth_type == "bearer":
            return {"Authorization": f"Bearer {auth_config['token']}"}
        
        elif auth_type == "basic":
            import base64
            credentials = f"{auth_config['username']}:{auth_config['password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        
        elif auth_type == "oauth2":
            token = await self._get_oauth2_token(config)
            return {"Authorization": f"Bearer {token}"}
        
        return {}
    
    async def _get_oauth2_token(self, config: IntegrationConfig) -> str:
        """OAuth2 토큰 획득"""
        auth_config = config.auth_config
        cache_key = f"oauth2_token_{config.integration_id}"
        
        # 캐시된 토큰 확인
        if cache_key in self.token_cache:
            token_info = self.token_cache[cache_key]
            if datetime.now() < token_info['expires_at']:
                return token_info['access_token']
        
        # 새 토큰 요청
        async with aiohttp.ClientSession() as session:
            data = {
                'grant_type': 'client_credentials',
                'client_id': auth_config['client_id'],
                'client_secret': auth_config['client_secret']
            }
            
            if auth_config.get('scope'):
                data['scope'] = auth_config['scope']
            
            async with session.post(auth_config['token_url'], data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    
                    # 토큰 캐시
                    expires_in = token_data.get('expires_in', 3600)
                    self.token_cache[cache_key] = {
                        'access_token': token_data['access_token'],
                        'expires_at': datetime.now() + timedelta(seconds=expires_in - 60)
                    }
                    
                    return token_data['access_token']
                else:
                    raise Exception(f"OAuth2 토큰 획득 실패: {response.status}")

class RateLimiter:
    """요청 제한 관리자"""
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis_client = redis_client
    
    async def is_allowed(self, integration_id: str, rate_limit: int) -> bool:
        """요청 허용 여부 확인"""
        key = f"rate_limit:{integration_id}"
        current_minute = int(datetime.now().timestamp() // 60)
        
        # 현재 분의 요청 수 확인
        current_count = await self.redis_client.get(f"{key}:{current_minute}")
        current_count = int(current_count) if current_count else 0
        
        if current_count >= rate_limit:
            return False
        
        # 요청 수 증가
        await self.redis_client.incr(f"{key}:{current_minute}")
        await self.redis_client.expire(f"{key}:{current_minute}", 120)  # 2분 후 만료
        
        return True

class WebhookManager:
    """웹훅 관리자"""
    
    def __init__(self):
        self.webhook_handlers: Dict[str, Callable] = {}
    
    def register_webhook(self, event_type: str, handler: Callable):
        """웹훅 핸들러 등록"""
        self.webhook_handlers[event_type] = handler
        logger.info("웹훅 핸들러 등록", event_type=event_type)
    
    async def handle_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """웹훅 처리"""
        if event_type not in self.webhook_handlers:
            logger.warning("등록되지 않은 웹훅 이벤트", event_type=event_type)
            return {"status": "error", "message": "Unknown event type"}
        
        try:
            handler = self.webhook_handlers[event_type]
            result = await handler(payload)
            
            logger.info("웹훅 처리 완료", event_type=event_type)
            return {"status": "success", "result": result}
            
        except Exception as e:
            logger.error("웹훅 처리 실패", event_type=event_type, error=str(e))
            return {"status": "error", "message": str(e)}

class CRMIntegration:
    """CRM 연동"""
    
    def __init__(self, config: IntegrationConfig, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
    
    async def get_customer_info(self, customer_id: str) -> Dict[str, Any]:
        """고객 정보 조회"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/customers/{customer_id}"
            
            async with session.get(url, headers=headers, timeout=self.config.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"CRM 고객 정보 조회 실패: {response.status}")
    
    async def update_customer_info(self, customer_id: str, data: Dict[str, Any]) -> bool:
        """고객 정보 업데이트"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/customers/{customer_id}"
            
            async with session.put(url, headers=headers, json=data, timeout=self.config.timeout) as response:
                return response.status in [200, 204]
    
    async def create_interaction_log(self, customer_id: str, interaction_data: Dict[str, Any]) -> str:
        """상호작용 로그 생성"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        payload = {
            'customer_id': customer_id,
            'interaction_type': interaction_data.get('type', 'call'),
            'channel': interaction_data.get('channel', 'voice'),
            'agent_id': interaction_data.get('agent_id'),
            'start_time': interaction_data.get('start_time'),
            'end_time': interaction_data.get('end_time'),
            'summary': interaction_data.get('summary'),
            'outcome': interaction_data.get('outcome'),
            'tags': interaction_data.get('tags', [])
        }
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/interactions"
            
            async with session.post(url, headers=headers, json=payload, timeout=self.config.timeout) as response:
                if response.status == 201:
                    result = await response.json()
                    return result.get('id')
                else:
                    raise Exception(f"CRM 상호작용 로그 생성 실패: {response.status}")

class PaymentIntegration:
    """결제 시스템 연동"""
    
    def __init__(self, config: IntegrationConfig, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
    
    async def process_payment(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """결제 처리"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        payload = {
            'amount': payment_data['amount'],
            'currency': payment_data.get('currency', 'KRW'),
            'payment_method': payment_data['payment_method'],
            'customer_id': payment_data['customer_id'],
            'order_id': payment_data.get('order_id', str(uuid.uuid4())),
            'description': payment_data.get('description', ''),
            'metadata': payment_data.get('metadata', {})
        }
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/payments"
            
            async with session.post(url, headers=headers, json=payload, timeout=self.config.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"결제 처리 실패: {response.status} - {error_text}")
    
    async def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """결제 상태 조회"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/payments/{payment_id}"
            
            async with session.get(url, headers=headers, timeout=self.config.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"결제 상태 조회 실패: {response.status}")
    
    async def refund_payment(self, payment_id: str, amount: Optional[int] = None) -> Dict[str, Any]:
        """결제 환불"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        payload = {}
        if amount:
            payload['amount'] = amount
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/payments/{payment_id}/refund"
            
            async with session.post(url, headers=headers, json=payload, timeout=self.config.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"결제 환불 실패: {response.status}")

class NotificationIntegration:
    """알림 연동 (SMS/Email)"""
    
    def __init__(self, config: IntegrationConfig, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
        
        # AWS SNS/SES 클라이언트
        self.sns_client = boto3.client('sns')
        self.ses_client = boto3.client('ses')
    
    async def send_sms(self, phone_number: str, message: str) -> str:
        """SMS 발송"""
        try:
            # AWS SNS를 통한 SMS 발송
            response = self.sns_client.publish(
                PhoneNumber=phone_number,
                Message=message
            )
            
            message_id = response['MessageId']
            logger.info("SMS 발송 완료", phone_number=phone_number, message_id=message_id)
            
            return message_id
            
        except Exception as e:
            logger.error("SMS 발송 실패", phone_number=phone_number, error=str(e))
            raise
    
    async def send_email(self, to_email: str, subject: str, body: str, 
                        from_email: str = None, html_body: str = None) -> str:
        """이메일 발송"""
        try:
            if not from_email:
                from_email = self.config.auth_config.get('from_email', 'noreply@aicc.com')
            
            destination = {'ToAddresses': [to_email]}
            message = {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}}
            }
            
            if html_body:
                message['Body']['Html'] = {'Data': html_body, 'Charset': 'UTF-8'}
            
            # AWS SES를 통한 이메일 발송
            response = self.ses_client.send_email(
                Source=from_email,
                Destination=destination,
                Message=message
            )
            
            message_id = response['MessageId']
            logger.info("이메일 발송 완료", to_email=to_email, message_id=message_id)
            
            return message_id
            
        except Exception as e:
            logger.error("이메일 발송 실패", to_email=to_email, error=str(e))
            raise
    
    async def send_push_notification(self, device_token: str, title: str, 
                                   body: str, data: Dict[str, Any] = None) -> str:
        """푸시 알림 발송"""
        try:
            # FCM 메시지 구성
            message = {
                'notification': {
                    'title': title,
                    'body': body
                },
                'token': device_token
            }
            
            if data:
                message['data'] = {k: str(v) for k, v in data.items()}
            
            # 외부 FCM API 호출
            headers = await self.auth_manager.get_auth_headers(self.config)
            headers['Content-Type'] = 'application/json'
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.endpoint_url}/send"
                
                async with session.post(url, headers=headers, json={'message': message}, 
                                      timeout=self.config.timeout) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('name', str(uuid.uuid4()))
                        
                        logger.info("푸시 알림 발송 완료", device_token=device_token, message_id=message_id)
                        return message_id
                    else:
                        raise Exception(f"푸시 알림 발송 실패: {response.status}")
                        
        except Exception as e:
            logger.error("푸시 알림 발송 실패", device_token=device_token, error=str(e))
            raise

class SocialMediaIntegration:
    """소셜 미디어 연동"""
    
    def __init__(self, config: IntegrationConfig, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
    
    async def post_message(self, platform: str, message: str, 
                          media_urls: List[str] = None) -> str:
        """소셜 미디어 메시지 게시"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        payload = {
            'platform': platform,
            'message': message,
            'media_urls': media_urls or []
        }
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/posts"
            
            async with session.post(url, headers=headers, json=payload, timeout=self.config.timeout) as response:
                if response.status == 201:
                    result = await response.json()
                    return result.get('post_id')
                else:
                    raise Exception(f"소셜 미디어 게시 실패: {response.status}")
    
    async def get_mentions(self, platform: str, since: datetime = None) -> List[Dict[str, Any]]:
        """멘션 조회"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        
        params = {'platform': platform}
        if since:
            params['since'] = since.isoformat()
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/mentions"
            
            async with session.get(url, headers=headers, params=params, timeout=self.config.timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"멘션 조회 실패: {response.status}")
    
    async def reply_to_mention(self, platform: str, mention_id: str, reply: str) -> str:
        """멘션 답글"""
        headers = await self.auth_manager.get_auth_headers(self.config)
        headers['Content-Type'] = 'application/json'
        
        payload = {
            'platform': platform,
            'mention_id': mention_id,
            'reply': reply
        }
        
        async with aiohttp.ClientSession() as session:
            url = f"{self.config.endpoint_url}/mentions/reply"
            
            async with session.post(url, headers=headers, json=payload, timeout=self.config.timeout) as response:
                if response.status == 201:
                    result = await response.json()
                    return result.get('reply_id')
                else:
                    raise Exception(f"멘션 답글 실패: {response.status}")

class IntegrationService:
    """통합 연동 서비스"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # 데이터베이스 설정
        self.engine = create_engine(config['database_url'])
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Redis 설정
        self.redis_client = aioredis.from_url(config['redis_url'])
        
        # 컴포넌트 초기화
        self.auth_manager = AuthManager()
        self.rate_limiter = RateLimiter(self.redis_client)
        self.webhook_manager = WebhookManager()
        
        # 연동 인스턴스 캐시
        self.integrations: Dict[str, Any] = {}
        
        # 메시지 큐
        self.message_queue = asyncio.Queue()
        
        # 웹훅 핸들러 등록
        self._register_default_webhooks()
    
    def _register_default_webhooks(self):
        """기본 웹훅 핸들러 등록"""
        
        async def handle_customer_update(payload: Dict[str, Any]) -> Dict[str, Any]:
            """고객 정보 업데이트 웹훅"""
            customer_id = payload.get('customer_id')
            updated_data = payload.get('data', {})
            
            # CRM 연동이 있다면 고객 정보 업데이트
            crm_integration = await self.get_integration_by_type(IntegrationType.CRM)
            if crm_integration:
                await crm_integration.update_customer_info(customer_id, updated_data)
            
            return {'customer_id': customer_id, 'updated': True}
        
        async def handle_payment_completed(payload: Dict[str, Any]) -> Dict[str, Any]:
            """결제 완료 웹훅"""
            payment_id = payload.get('payment_id')
            customer_id = payload.get('customer_id')
            amount = payload.get('amount')
            
            # 결제 완료 알림 발송
            notification_integration = await self.get_integration_by_type(IntegrationType.SMS)
            if notification_integration and payload.get('phone_number'):
                await notification_integration.send_sms(
                    payload['phone_number'],
                    f"결제가 완료되었습니다. 결제금액: {amount:,}원"
                )
            
            return {'payment_id': payment_id, 'notified': True}
        
        self.webhook_manager.register_webhook('customer.updated', handle_customer_update)
        self.webhook_manager.register_webhook('payment.completed', handle_payment_completed)
    
    async def register_integration(self, config: IntegrationConfig):
        """연동 등록"""
        # 데이터베이스에 저장
        with self.SessionLocal() as session:
            integration = Integration(
                id=config.integration_id,
                name=config.name,
                type=config.type.value,
                endpoint_url=config.endpoint_url,
                auth_type=config.auth_type,
                auth_config=json.dumps(config.auth_config),
                headers=json.dumps(config.headers or {}),
                timeout=config.timeout,
                retry_count=config.retry_count,
                rate_limit=config.rate_limit,
                enabled=config.enabled
            )
            
            session.merge(integration)
            session.commit()
        
        # 연동 인스턴스 생성
        await self._create_integration_instance(config)
        
        logger.info("연동 등록 완료", 
                   integration_id=config.integration_id,
                   type=config.type.value)
    
    async def _create_integration_instance(self, config: IntegrationConfig):
        """연동 인스턴스 생성"""
        if config.type == IntegrationType.CRM:
            self.integrations[config.integration_id] = CRMIntegration(config, self.auth_manager)
        elif config.type == IntegrationType.PAYMENT:
            self.integrations[config.integration_id] = PaymentIntegration(config, self.auth_manager)
        elif config.type in [IntegrationType.SMS, IntegrationType.EMAIL]:
            self.integrations[config.integration_id] = NotificationIntegration(config, self.auth_manager)
        elif config.type == IntegrationType.SOCIAL_MEDIA:
            self.integrations[config.integration_id] = SocialMediaIntegration(config, self.auth_manager)
    
    async def get_integration(self, integration_id: str) -> Optional[Any]:
        """연동 인스턴스 조회"""
        return self.integrations.get(integration_id)
    
    async def get_integration_by_type(self, integration_type: IntegrationType) -> Optional[Any]:
        """타입별 연동 인스턴스 조회"""
        for integration_id, instance in self.integrations.items():
            with self.SessionLocal() as session:
                integration = session.query(Integration).filter(Integration.id == integration_id).first()
                if integration and integration.type == integration_type.value and integration.enabled:
                    return instance
        return None
    
    async def send_message(self, message: IntegrationMessage) -> Dict[str, Any]:
        """메시지 전송"""
        integration = await self.get_integration(message.integration_id)
        if not integration:
            raise ValueError(f"연동을 찾을 수 없습니다: {message.integration_id}")
        
        # 요청 제한 확인
        with self.SessionLocal() as session:
            integration_config = session.query(Integration).filter(
                Integration.id == message.integration_id
            ).first()
            
            if not integration_config or not integration_config.enabled:
                raise ValueError(f"비활성화된 연동: {message.integration_id}")
            
            is_allowed = await self.rate_limiter.is_allowed(
                message.integration_id, 
                integration_config.rate_limit
            )
            
            if not is_allowed:
                raise Exception(f"요청 제한 초과: {message.integration_id}")
        
        # 메시지 타입에 따른 처리
        if message.message_type == MessageType.SYNC:
            return await self._send_sync_message(integration, message)
        elif message.message_type == MessageType.ASYNC:
            await self.message_queue.put(message)
            return {"status": "queued", "message_id": message.message_id}
        else:
            raise ValueError(f"지원하지 않는 메시지 타입: {message.message_type}")
    
    async def _send_sync_message(self, integration: Any, message: IntegrationMessage) -> Dict[str, Any]:
        """동기 메시지 전송"""
        start_time = datetime.now()
        log_id = str(uuid.uuid4())
        
        try:
            # 메시지 전송 (연동 타입에 따라 다른 메서드 호출)
            result = await self._execute_integration_method(integration, message)
            
            # 성공 로그 기록
            await self._log_integration_request(
                log_id, message.integration_id, message.message_id,
                "POST", "", message.headers or {}, message.payload,
                200, {}, result, int((datetime.now() - start_time).total_seconds() * 1000)
            )
            
            # 통계 업데이트
            await self._update_integration_stats(message.integration_id, True)
            
            return {"status": "success", "result": result}
            
        except Exception as e:
            # 실패 로그 기록
            await self._log_integration_request(
                log_id, message.integration_id, message.message_id,
                "POST", "", message.headers or {}, message.payload,
                500, {}, None, int((datetime.now() - start_time).total_seconds() * 1000),
                str(e)
            )
            
            # 통계 업데이트
            await self._update_integration_stats(message.integration_id, False)
            
            # 재시도 로직
            if message.retry_count < message.max_retries:
                message.retry_count += 1
                await asyncio.sleep(2 ** message.retry_count)  # 지수 백오프
                return await self._send_sync_message(integration, message)
            
            raise
    
    async def _execute_integration_method(self, integration: Any, message: IntegrationMessage) -> Any:
        """연동별 메서드 실행"""
        payload = message.payload
        method = payload.get('method')
        
        if isinstance(integration, CRMIntegration):
            if method == 'get_customer_info':
                return await integration.get_customer_info(payload['customer_id'])
            elif method == 'update_customer_info':
                return await integration.update_customer_info(payload['customer_id'], payload['data'])
            elif method == 'create_interaction_log':
                return await integration.create_interaction_log(payload['customer_id'], payload['interaction_data'])
        
        elif isinstance(integration, PaymentIntegration):
            if method == 'process_payment':
                return await integration.process_payment(payload['payment_data'])
            elif method == 'get_payment_status':
                return await integration.get_payment_status(payload['payment_id'])
            elif method == 'refund_payment':
                return await integration.refund_payment(payload['payment_id'], payload.get('amount'))
        
        elif isinstance(integration, NotificationIntegration):
            if method == 'send_sms':
                return await integration.send_sms(payload['phone_number'], payload['message'])
            elif method == 'send_email':
                return await integration.send_email(
                    payload['to_email'], payload['subject'], payload['body'],
                    payload.get('from_email'), payload.get('html_body')
                )
            elif method == 'send_push_notification':
                return await integration.send_push_notification(
                    payload['device_token'], payload['title'], payload['body'], payload.get('data')
                )
        
        elif isinstance(integration, SocialMediaIntegration):
            if method == 'post_message':
                return await integration.post_message(
                    payload['platform'], payload['message'], payload.get('media_urls')
                )
            elif method == 'get_mentions':
                return await integration.get_mentions(payload['platform'], payload.get('since'))
            elif method == 'reply_to_mention':
                return await integration.reply_to_mention(
                    payload['platform'], payload['mention_id'], payload['reply']
                )
        
        raise ValueError(f"지원하지 않는 메서드: {method}")
    
    async def _log_integration_request(self, log_id: str, integration_id: str, message_id: str,
                                     method: str, url: str, request_headers: Dict,
                                     request_body: Any, response_status: int,
                                     response_headers: Dict, response_body: Any,
                                     duration_ms: int, error_message: str = None):
        """연동 요청 로그 기록"""
        with self.SessionLocal() as session:
            log = IntegrationLog(
                id=log_id,
                integration_id=integration_id,
                message_id=message_id,
                request_method=method,
                request_url=url,
                request_headers=json.dumps(request_headers),
                request_body=json.dumps(request_body) if request_body else None,
                response_status=response_status,
                response_headers=json.dumps(response_headers),
                response_body=json.dumps(response_body) if response_body else None,
                duration_ms=duration_ms,
                error_message=error_message
            )
            
            session.add(log)
            session.commit()
    
    async def _update_integration_stats(self, integration_id: str, success: bool):
        """연동 통계 업데이트"""
        with self.SessionLocal() as session:
            integration = session.query(Integration).filter(Integration.id == integration_id).first()
            
            if integration:
                integration.total_requests += 1
                if success:
                    integration.successful_requests += 1
                else:
                    integration.failed_requests += 1
                integration.last_request_at = datetime.now()
                
                session.commit()
    
    async def process_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """웹훅 처리"""
        return await self.webhook_manager.handle_webhook(event_type, payload)
    
    async def start_message_processor(self):
        """비동기 메시지 처리기 시작"""
        while True:
            try:
                message = await self.message_queue.get()
                integration = await self.get_integration(message.integration_id)
                
                if integration:
                    await self._send_sync_message(integration, message)
                
                self.message_queue.task_done()
                
            except Exception as e:
                logger.error("메시지 처리 실패", error=str(e))
                await asyncio.sleep(1)

# 설정 예시
DEFAULT_CONFIG = {
    'database_url': 'postgresql://user:password@localhost:5432/aicc_db',
    'redis_url': 'redis://localhost:6379'
}

async def main():
    """메인 실행 함수"""
    integration_service = IntegrationService(DEFAULT_CONFIG)
    
    # CRM 연동 등록 예시
    crm_config = IntegrationConfig(
        integration_id="crm_salesforce",
        name="Salesforce CRM",
        type=IntegrationType.CRM,
        endpoint_url="https://api.salesforce.com/v1",
        auth_type="oauth2",
        auth_config={
            "client_id": "your_client_id",
            "client_secret": "your_client_secret",
            "token_url": "https://login.salesforce.com/services/oauth2/token"
        }
    )
    
    await integration_service.register_integration(crm_config)
    
    # 메시지 처리기 시작
    asyncio.create_task(integration_service.start_message_processor())
    
    # 예시 메시지 전송
    message = IntegrationMessage(
        message_id=str(uuid.uuid4()),
        integration_id="crm_salesforce",
        message_type=MessageType.SYNC,
        payload={
            "method": "get_customer_info",
            "customer_id": "12345"
        }
    )
    
    try:
        result = await integration_service.send_message(message)
        logger.info("연동 테스트 완료", result=result)
    except Exception as e:
        logger.error("연동 테스트 실패", error=str(e))

if __name__ == "__main__":
    asyncio.run(main()) 