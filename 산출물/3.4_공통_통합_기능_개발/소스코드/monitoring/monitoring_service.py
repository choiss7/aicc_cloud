"""
통합 모니터링 서비스
AWS CloudWatch, Prometheus, Grafana 연동
실시간 시스템 메트릭 수집 및 알림
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import boto3
import psutil
import redis
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import structlog

# 로깅 설정
logger = structlog.get_logger(__name__)

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"

@dataclass
class SystemMetric:
    """시스템 메트릭 데이터 클래스"""
    timestamp: datetime
    metric_name: str
    metric_type: MetricType
    value: float
    labels: Dict[str, str]
    source: str

@dataclass
class Alert:
    """알림 데이터 클래스"""
    id: str
    level: AlertLevel
    title: str
    message: str
    source: str
    timestamp: datetime
    resolved: bool = False
    metadata: Dict[str, Any] = None

class PrometheusMetrics:
    """Prometheus 메트릭 정의"""
    
    def __init__(self):
        # 시스템 메트릭
        self.cpu_usage = Gauge('system_cpu_usage_percent', 'CPU 사용률', ['instance'])
        self.memory_usage = Gauge('system_memory_usage_percent', '메모리 사용률', ['instance'])
        self.disk_usage = Gauge('system_disk_usage_percent', '디스크 사용률', ['instance', 'device'])
        
        # 애플리케이션 메트릭
        self.active_sessions = Gauge('aicc_active_sessions_total', '활성 세션 수', ['service'])
        self.api_requests = Counter('aicc_api_requests_total', 'API 요청 수', ['method', 'endpoint', 'status'])
        self.api_duration = Histogram('aicc_api_duration_seconds', 'API 응답 시간', ['method', 'endpoint'])
        
        # 데이터베이스 메트릭
        self.db_connections = Gauge('aicc_db_connections_active', '활성 DB 연결 수', ['database'])
        self.db_query_duration = Histogram('aicc_db_query_duration_seconds', 'DB 쿼리 시간', ['query_type'])
        
        # AWS Connect 메트릭
        self.connect_calls_active = Gauge('aicc_connect_calls_active', '활성 통화 수', ['queue'])
        self.connect_agents_available = Gauge('aicc_connect_agents_available', '사용 가능한 상담원 수', ['queue'])
        self.connect_queue_size = Gauge('aicc_connect_queue_size', '대기 중인 통화 수', ['queue'])

class CloudWatchMetrics:
    """AWS CloudWatch 메트릭 관리"""
    
    def __init__(self, region_name: str = 'ap-northeast-2'):
        self.cloudwatch = boto3.client('cloudwatch', region_name=region_name)
        self.namespace = 'AICC/ContactCenter'
    
    async def put_metric(self, metric_name: str, value: float, unit: str = 'Count', 
                        dimensions: List[Dict[str, str]] = None):
        """CloudWatch에 메트릭 전송"""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }
            
            if dimensions:
                metric_data['Dimensions'] = dimensions
            
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )
            
            logger.info("CloudWatch 메트릭 전송 완료", 
                       metric_name=metric_name, value=value)
                       
        except Exception as e:
            logger.error("CloudWatch 메트릭 전송 실패", 
                        metric_name=metric_name, error=str(e))

class SystemMonitor:
    """시스템 리소스 모니터링"""
    
    def __init__(self, prometheus_metrics: PrometheusMetrics):
        self.prometheus_metrics = prometheus_metrics
        self.instance_id = self._get_instance_id()
    
    def _get_instance_id(self) -> str:
        """인스턴스 ID 가져오기"""
        try:
            import requests
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id',
                timeout=2
            )
            return response.text
        except:
            return 'localhost'
    
    async def collect_system_metrics(self) -> List[SystemMetric]:
        """시스템 메트릭 수집"""
        metrics = []
        timestamp = datetime.now()
        
        # CPU 사용률
        cpu_percent = psutil.cpu_percent(interval=1)
        self.prometheus_metrics.cpu_usage.labels(instance=self.instance_id).set(cpu_percent)
        metrics.append(SystemMetric(
            timestamp=timestamp,
            metric_name='cpu_usage_percent',
            metric_type=MetricType.GAUGE,
            value=cpu_percent,
            labels={'instance': self.instance_id},
            source='system'
        ))
        
        # 메모리 사용률
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        self.prometheus_metrics.memory_usage.labels(instance=self.instance_id).set(memory_percent)
        metrics.append(SystemMetric(
            timestamp=timestamp,
            metric_name='memory_usage_percent',
            metric_type=MetricType.GAUGE,
            value=memory_percent,
            labels={'instance': self.instance_id},
            source='system'
        ))
        
        # 디스크 사용률
        for partition in psutil.disk_partitions():
            try:
                disk_usage = psutil.disk_usage(partition.mountpoint)
                disk_percent = (disk_usage.used / disk_usage.total) * 100
                
                self.prometheus_metrics.disk_usage.labels(
                    instance=self.instance_id,
                    device=partition.device
                ).set(disk_percent)
                
                metrics.append(SystemMetric(
                    timestamp=timestamp,
                    metric_name='disk_usage_percent',
                    metric_type=MetricType.GAUGE,
                    value=disk_percent,
                    labels={
                        'instance': self.instance_id,
                        'device': partition.device
                    },
                    source='system'
                ))
            except PermissionError:
                continue
        
        return metrics

class DatabaseMonitor:
    """데이터베이스 모니터링"""
    
    def __init__(self, database_url: str, prometheus_metrics: PrometheusMetrics):
        self.engine = create_engine(database_url)
        self.prometheus_metrics = prometheus_metrics
    
    async def collect_db_metrics(self) -> List[SystemMetric]:
        """데이터베이스 메트릭 수집"""
        metrics = []
        timestamp = datetime.now()
        
        try:
            # 활성 연결 수
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT count(*) as active_connections
                    FROM pg_stat_activity
                    WHERE state = 'active'
                """))
                active_connections = result.scalar()
                
                self.prometheus_metrics.db_connections.labels(database='postgres').set(active_connections)
                metrics.append(SystemMetric(
                    timestamp=timestamp,
                    metric_name='db_active_connections',
                    metric_type=MetricType.GAUGE,
                    value=active_connections,
                    labels={'database': 'postgres'},
                    source='database'
                ))
                
                # 느린 쿼리 수
                result = conn.execute(text("""
                    SELECT count(*) as slow_queries
                    FROM pg_stat_activity
                    WHERE state = 'active' AND query_start < NOW() - INTERVAL '30 seconds'
                """))
                slow_queries = result.scalar()
                
                metrics.append(SystemMetric(
                    timestamp=timestamp,
                    metric_name='db_slow_queries',
                    metric_type=MetricType.GAUGE,
                    value=slow_queries,
                    labels={'database': 'postgres'},
                    source='database'
                ))
                
        except Exception as e:
            logger.error("데이터베이스 메트릭 수집 실패", error=str(e))
        
        return metrics

class ApplicationMonitor:
    """애플리케이션 메트릭 모니터링"""
    
    def __init__(self, redis_client: redis.Redis, prometheus_metrics: PrometheusMetrics):
        self.redis_client = redis_client
        self.prometheus_metrics = prometheus_metrics
    
    async def collect_app_metrics(self) -> List[SystemMetric]:
        """애플리케이션 메트릭 수집"""
        metrics = []
        timestamp = datetime.now()
        
        try:
            # 활성 세션 수 (Redis에서 조회)
            active_sessions = self.redis_client.scard('active_sessions')
            self.prometheus_metrics.active_sessions.labels(service='chat').set(active_sessions)
            
            metrics.append(SystemMetric(
                timestamp=timestamp,
                metric_name='active_sessions',
                metric_type=MetricType.GAUGE,
                value=active_sessions,
                labels={'service': 'chat'},
                source='application'
            ))
            
            # WebSocket 연결 수
            websocket_connections = self.redis_client.scard('websocket_connections')
            metrics.append(SystemMetric(
                timestamp=timestamp,
                metric_name='websocket_connections',
                metric_type=MetricType.GAUGE,
                value=websocket_connections,
                labels={'service': 'websocket'},
                source='application'
            ))
            
        except Exception as e:
            logger.error("애플리케이션 메트릭 수집 실패", error=str(e))
        
        return metrics

class AWSConnectMonitor:
    """AWS Connect 모니터링"""
    
    def __init__(self, instance_id: str, prometheus_metrics: PrometheusMetrics):
        self.connect_client = boto3.client('connect')
        self.instance_id = instance_id
        self.prometheus_metrics = prometheus_metrics
    
    async def collect_connect_metrics(self) -> List[SystemMetric]:
        """AWS Connect 메트릭 수집"""
        metrics = []
        timestamp = datetime.now()
        
        try:
            # 큐 메트릭 조회
            queues = self.connect_client.list_queues(InstanceId=self.instance_id)
            
            for queue in queues['QueueSummaryList']:
                queue_id = queue['Id']
                queue_name = queue['Name']
                
                # 현재 메트릭 조회
                current_metrics = self.connect_client.get_current_metric_data(
                    InstanceId=self.instance_id,
                    Filters={
                        'Queues': [queue_id],
                        'Channels': ['VOICE']
                    },
                    CurrentMetrics=[
                        {'Name': 'AGENTS_AVAILABLE', 'Unit': 'COUNT'},
                        {'Name': 'CONTACTS_IN_QUEUE', 'Unit': 'COUNT'},
                        {'Name': 'AGENTS_ON_CALL', 'Unit': 'COUNT'}
                    ]
                )
                
                for metric_result in current_metrics['MetricResults']:
                    for collection in metric_result['Collections']:
                        metric_name = collection['Metric']['Name']
                        value = collection['Value']
                        
                        if metric_name == 'AGENTS_AVAILABLE':
                            self.prometheus_metrics.connect_agents_available.labels(
                                queue=queue_name
                            ).set(value)
                        elif metric_name == 'CONTACTS_IN_QUEUE':
                            self.prometheus_metrics.connect_queue_size.labels(
                                queue=queue_name
                            ).set(value)
                        elif metric_name == 'AGENTS_ON_CALL':
                            self.prometheus_metrics.connect_calls_active.labels(
                                queue=queue_name
                            ).set(value)
                        
                        metrics.append(SystemMetric(
                            timestamp=timestamp,
                            metric_name=f'connect_{metric_name.lower()}',
                            metric_type=MetricType.GAUGE,
                            value=value,
                            labels={'queue': queue_name},
                            source='aws_connect'
                        ))
                        
        except Exception as e:
            logger.error("AWS Connect 메트릭 수집 실패", error=str(e))
        
        return metrics

class AlertManager:
    """알림 관리 시스템"""
    
    def __init__(self, sns_topic_arn: str = None):
        self.sns_client = boto3.client('sns') if sns_topic_arn else None
        self.sns_topic_arn = sns_topic_arn
        self.alert_rules = self._load_alert_rules()
        self.active_alerts: Dict[str, Alert] = {}
    
    def _load_alert_rules(self) -> Dict[str, Dict]:
        """알림 규칙 로드"""
        return {
            'high_cpu_usage': {
                'metric': 'cpu_usage_percent',
                'threshold': 80,
                'operator': '>',
                'level': AlertLevel.WARNING,
                'duration': 300  # 5분
            },
            'high_memory_usage': {
                'metric': 'memory_usage_percent',
                'threshold': 85,
                'operator': '>',
                'level': AlertLevel.WARNING,
                'duration': 300
            },
            'high_disk_usage': {
                'metric': 'disk_usage_percent',
                'threshold': 90,
                'operator': '>',
                'level': AlertLevel.ERROR,
                'duration': 60
            },
            'db_connection_high': {
                'metric': 'db_active_connections',
                'threshold': 50,
                'operator': '>',
                'level': AlertLevel.WARNING,
                'duration': 180
            },
            'queue_size_high': {
                'metric': 'connect_contacts_in_queue',
                'threshold': 10,
                'operator': '>',
                'level': AlertLevel.ERROR,
                'duration': 120
            }
        }
    
    async def evaluate_metrics(self, metrics: List[SystemMetric]):
        """메트릭 기반 알림 평가"""
        for metric in metrics:
            await self._evaluate_metric(metric)
    
    async def _evaluate_metric(self, metric: SystemMetric):
        """개별 메트릭 평가"""
        for rule_name, rule in self.alert_rules.items():
            if metric.metric_name == rule['metric']:
                threshold = rule['threshold']
                operator = rule['operator']
                
                triggered = False
                if operator == '>' and metric.value > threshold:
                    triggered = True
                elif operator == '<' and metric.value < threshold:
                    triggered = True
                elif operator == '==' and metric.value == threshold:
                    triggered = True
                
                if triggered:
                    await self._create_alert(rule_name, rule, metric)
                else:
                    await self._resolve_alert(rule_name)
    
    async def _create_alert(self, rule_name: str, rule: Dict, metric: SystemMetric):
        """알림 생성"""
        alert_id = f"{rule_name}_{metric.source}_{hash(str(metric.labels))}"
        
        if alert_id not in self.active_alerts:
            alert = Alert(
                id=alert_id,
                level=rule['level'],
                title=f"{rule_name.replace('_', ' ').title()}",
                message=f"{metric.metric_name}: {metric.value} (임계값: {rule['threshold']})",
                source=metric.source,
                timestamp=datetime.now(),
                metadata={
                    'metric': asdict(metric),
                    'rule': rule
                }
            )
            
            self.active_alerts[alert_id] = alert
            await self._send_alert(alert)
            
            logger.warning("알림 생성", 
                          alert_id=alert_id, 
                          level=alert.level.value,
                          message=alert.message)
    
    async def _resolve_alert(self, rule_name: str):
        """알림 해결"""
        alerts_to_resolve = [
            alert_id for alert_id in self.active_alerts.keys()
            if alert_id.startswith(rule_name)
        ]
        
        for alert_id in alerts_to_resolve:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            del self.active_alerts[alert_id]
            
            logger.info("알림 해결", alert_id=alert_id)
    
    async def _send_alert(self, alert: Alert):
        """알림 전송"""
        # SNS로 알림 전송
        if self.sns_client and self.sns_topic_arn:
            try:
                message = {
                    'alert_id': alert.id,
                    'level': alert.level.value,
                    'title': alert.title,
                    'message': alert.message,
                    'source': alert.source,
                    'timestamp': alert.timestamp.isoformat()
                }
                
                self.sns_client.publish(
                    TopicArn=self.sns_topic_arn,
                    Message=json.dumps(message),
                    Subject=f"[{alert.level.value.upper()}] {alert.title}"
                )
                
            except Exception as e:
                logger.error("SNS 알림 전송 실패", error=str(e))

class MonitoringService:
    """통합 모니터링 서비스"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prometheus_metrics = PrometheusMetrics()
        self.cloudwatch_metrics = CloudWatchMetrics(config.get('aws_region', 'ap-northeast-2'))
        self.alert_manager = AlertManager(config.get('sns_topic_arn'))
        
        # 모니터 초기화
        self.system_monitor = SystemMonitor(self.prometheus_metrics)
        
        if config.get('database_url'):
            self.db_monitor = DatabaseMonitor(config['database_url'], self.prometheus_metrics)
        
        if config.get('redis_url'):
            self.redis_client = redis.from_url(config['redis_url'])
            self.app_monitor = ApplicationMonitor(self.redis_client, self.prometheus_metrics)
        
        if config.get('connect_instance_id'):
            self.connect_monitor = AWSConnectMonitor(
                config['connect_instance_id'], 
                self.prometheus_metrics
            )
        
        self.running = False
    
    async def start(self):
        """모니터링 서비스 시작"""
        self.running = True
        
        # Prometheus 메트릭 서버 시작
        start_http_server(self.config.get('prometheus_port', 8000))
        logger.info("Prometheus 메트릭 서버 시작", port=self.config.get('prometheus_port', 8000))
        
        # 메트릭 수집 루프 시작
        asyncio.create_task(self._metric_collection_loop())
        logger.info("모니터링 서비스 시작")
    
    async def stop(self):
        """모니터링 서비스 중지"""
        self.running = False
        logger.info("모니터링 서비스 중지")
    
    async def _metric_collection_loop(self):
        """메트릭 수집 루프"""
        while self.running:
            try:
                all_metrics = []
                
                # 시스템 메트릭 수집
                system_metrics = await self.system_monitor.collect_system_metrics()
                all_metrics.extend(system_metrics)
                
                # 데이터베이스 메트릭 수집
                if hasattr(self, 'db_monitor'):
                    db_metrics = await self.db_monitor.collect_db_metrics()
                    all_metrics.extend(db_metrics)
                
                # 애플리케이션 메트릭 수집
                if hasattr(self, 'app_monitor'):
                    app_metrics = await self.app_monitor.collect_app_metrics()
                    all_metrics.extend(app_metrics)
                
                # AWS Connect 메트릭 수집
                if hasattr(self, 'connect_monitor'):
                    connect_metrics = await self.connect_monitor.collect_connect_metrics()
                    all_metrics.extend(connect_metrics)
                
                # CloudWatch로 메트릭 전송
                for metric in all_metrics:
                    await self.cloudwatch_metrics.put_metric(
                        metric_name=metric.metric_name,
                        value=metric.value,
                        dimensions=[
                            {'Name': k, 'Value': v} for k, v in metric.labels.items()
                        ]
                    )
                
                # 알림 평가
                await self.alert_manager.evaluate_metrics(all_metrics)
                
                logger.debug("메트릭 수집 완료", count=len(all_metrics))
                
            except Exception as e:
                logger.error("메트릭 수집 중 오류", error=str(e))
            
            # 30초 대기
            await asyncio.sleep(30)

# 설정 예시
DEFAULT_CONFIG = {
    'aws_region': 'ap-northeast-2',
    'prometheus_port': 8000,
    'database_url': 'postgresql://user:password@localhost:5432/aicc_db',
    'redis_url': 'redis://localhost:6379',
    'connect_instance_id': 'your-connect-instance-id',
    'sns_topic_arn': 'arn:aws:sns:ap-northeast-2:123456789012:aicc-alerts'
}

async def main():
    """메인 실행 함수"""
    monitoring_service = MonitoringService(DEFAULT_CONFIG)
    
    try:
        await monitoring_service.start()
        
        # 서비스 실행 유지
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("서비스 종료 요청")
    finally:
        await monitoring_service.stop()

if __name__ == "__main__":
    asyncio.run(main()) 