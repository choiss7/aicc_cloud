"""
AWS 서비스 클라이언트 통합 관리
AWS Connect 콜센터 환경을 위한 각종 AWS 서비스 클라이언트 래퍼
"""

import boto3
import json
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
from botocore.exceptions import ClientError, BotoCoreError
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


class AWSClientManager:
    """AWS 서비스 클라이언트 통합 관리 클래스"""
    
    def __init__(
        self,
        region_name: str = "ap-northeast-2",
        profile_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ):
        self.region_name = region_name
        self.profile_name = profile_name
        
        # 세션 구성
        if profile_name:
            self.session = boto3.Session(profile_name=profile_name)
        else:
            self.session = boto3.Session(
                aws_access_key_id=aws_access_key_id or os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=aws_secret_access_key or os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=region_name
            )
        
        # 클라이언트 캐시
        self._clients: Dict[str, Any] = {}
        
        # 연결 테스트 실행
        self._test_connection()
    
    def _test_connection(self) -> bool:
        """AWS 연결 테스트"""
        try:
            sts_client = self.get_client('sts')
            identity = sts_client.get_caller_identity()
            logger.info(f"AWS 연결 성공: {identity.get('Arn')}")
            return True
        except Exception as e:
            logger.error(f"AWS 연결 실패: {e}")
            return False
    
    @lru_cache(maxsize=32)
    def get_client(self, service_name: str) -> Any:
        """AWS 서비스 클라이언트 가져오기 (캐시됨)"""
        if service_name not in self._clients:
            try:
                self._clients[service_name] = self.session.client(
                    service_name,
                    region_name=self.region_name
                )
                logger.debug(f"{service_name} 클라이언트 생성 완료")
            except Exception as e:
                logger.error(f"{service_name} 클라이언트 생성 실패: {e}")
                raise
        
        return self._clients[service_name]
    
    def get_resource(self, service_name: str) -> Any:
        """AWS 서비스 리소스 가져오기"""
        try:
            return self.session.resource(service_name, region_name=self.region_name)
        except Exception as e:
            logger.error(f"{service_name} 리소스 생성 실패: {e}")
            raise


class ConnectClient:
    """AWS Connect 서비스 클라이언트"""
    
    def __init__(self, aws_manager: AWSClientManager, instance_id: str):
        self.client = aws_manager.get_client('connect')
        self.instance_id = instance_id
        self.instance_arn = f"arn:aws:connect:{aws_manager.region_name}:{self._get_account_id()}:instance/{instance_id}"
    
    def _get_account_id(self) -> str:
        """계정 ID 가져오기"""
        try:
            sts_client = boto3.client('sts')
            return sts_client.get_caller_identity()['Account']
        except Exception:
            return "000000000000"  # 기본값
    
    def create_user(
        self,
        username: str,
        first_name: str,
        last_name: str,
        email: str,
        phone_config: Dict[str, Any],
        security_profile_ids: List[str],
        routing_profile_id: str,
        hierarchy_group_id: Optional[str] = None
    ) -> str:
        """Connect 사용자 생성"""
        try:
            response = self.client.create_user(
                Username=username,
                PasswordConfig={
                    'PasswordExpiry': datetime.now() + timedelta(days=90),
                    'PasswordExpiry': False
                },
                IdentityInfo={
                    'FirstName': first_name,
                    'LastName': last_name,
                    'Email': email
                },
                PhoneConfig=phone_config,
                SecurityProfileIds=security_profile_ids,
                RoutingProfileId=routing_profile_id,
                HierarchyGroupId=hierarchy_group_id,
                InstanceId=self.instance_id
            )
            
            user_id = response['UserId']
            logger.info(f"Connect 사용자 생성 완료: {username} ({user_id})")
            return user_id
            
        except ClientError as e:
            logger.error(f"Connect 사용자 생성 실패: {e}")
            raise
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Connect 사용자 정보 조회"""
        try:
            response = self.client.describe_user(
                UserId=user_id,
                InstanceId=self.instance_id
            )
            return response['User']
        except ClientError as e:
            logger.error(f"Connect 사용자 조회 실패: {e}")
            return {}
    
    def update_user_status(self, user_id: str, agent_status_id: str) -> bool:
        """상담원 상태 업데이트"""
        try:
            self.client.put_user_status(
                UserId=user_id,
                InstanceId=self.instance_id,
                AgentStatusId=agent_status_id
            )
            logger.info(f"상담원 상태 업데이트 완료: {user_id}")
            return True
        except ClientError as e:
            logger.error(f"상담원 상태 업데이트 실패: {e}")
            return False
    
    def get_current_metric_data(
        self,
        filters: Dict[str, Any],
        metrics: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """실시간 메트릭 데이터 조회"""
        try:
            response = self.client.get_current_metric_data(
                InstanceId=self.instance_id,
                Filters=filters,
                Metrics=metrics
            )
            return response.get('MetricResults', [])
        except ClientError as e:
            logger.error(f"실시간 메트릭 조회 실패: {e}")
            return []
    
    def list_routing_profiles(self) -> List[Dict[str, Any]]:
        """라우팅 프로필 목록 조회"""
        try:
            response = self.client.list_routing_profiles(
                InstanceId=self.instance_id
            )
            return response.get('RoutingProfileSummaryList', [])
        except ClientError as e:
            logger.error(f"라우팅 프로필 조회 실패: {e}")
            return []


class LexClient:
    """AWS Lex 서비스 클라이언트"""
    
    def __init__(self, aws_manager: AWSClientManager):
        self.client_v1 = aws_manager.get_client('lex-runtime')
        self.client_v2 = aws_manager.get_client('lexv2-runtime')
    
    def post_text(
        self,
        bot_name: str,
        bot_alias: str,
        user_id: str,
        input_text: str,
        session_attributes: Optional[Dict[str, str]] = None,
        request_attributes: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Lex V1 텍스트 요청 (deprecated but still used)"""
        try:
            response = self.client_v1.post_text(
                botName=bot_name,
                botAlias=bot_alias,
                userId=user_id,
                inputText=input_text,
                sessionAttributes=session_attributes or {},
                requestAttributes=request_attributes or {}
            )
            
            logger.debug(f"Lex V1 응답: {response.get('intentName')} - {response.get('message')}")
            return response
            
        except ClientError as e:
            logger.error(f"Lex V1 요청 실패: {e}")
            return {'dialogState': 'Failed', 'message': '처리 중 오류가 발생했습니다.'}
    
    def recognize_text(
        self,
        bot_id: str,
        bot_alias_id: str,
        locale_id: str,
        session_id: str,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
        request_attributes: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Lex V2 텍스트 인식"""
        try:
            response = self.client_v2.recognize_text(
                botId=bot_id,
                botAliasId=bot_alias_id,
                localeId=locale_id,
                sessionId=session_id,
                text=text,
                sessionState=session_state or {},
                requestAttributes=request_attributes or {}
            )
            
            logger.debug(f"Lex V2 응답: {response.get('sessionState', {}).get('intent', {}).get('name')}")
            return response
            
        except ClientError as e:
            logger.error(f"Lex V2 요청 실패: {e}")
            return {
                'sessionState': {'dialogAction': {'type': 'Close'}},
                'messages': [{'content': '처리 중 오류가 발생했습니다.', 'contentType': 'PlainText'}]
            }
    
    def recognize_utterance(
        self,
        bot_id: str,
        bot_alias_id: str,
        locale_id: str,
        session_id: str,
        request_content_type: str,
        input_stream: bytes,
        session_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Lex V2 음성 인식"""
        try:
            response = self.client_v2.recognize_utterance(
                botId=bot_id,
                botAliasId=bot_alias_id,
                localeId=locale_id,
                sessionId=session_id,
                requestContentType=request_content_type,
                inputStream=input_stream,
                sessionState=json.dumps(session_state) if session_state else '{}'
            )
            
            logger.debug("Lex V2 음성 인식 완료")
            return response
            
        except ClientError as e:
            logger.error(f"Lex V2 음성 인식 실패: {e}")
            return {}


class DynamoDBClient:
    """AWS DynamoDB 클라이언트"""
    
    def __init__(self, aws_manager: AWSClientManager):
        self.client = aws_manager.get_client('dynamodb')
        self.resource = aws_manager.get_resource('dynamodb')
    
    def get_table(self, table_name: str):
        """테이블 리소스 가져오기"""
        return self.resource.Table(table_name)
    
    def put_item(self, table_name: str, item: Dict[str, Any]) -> bool:
        """항목 저장"""
        try:
            table = self.get_table(table_name)
            table.put_item(Item=item)
            logger.debug(f"DynamoDB 항목 저장 완료: {table_name}")
            return True
        except ClientError as e:
            logger.error(f"DynamoDB 항목 저장 실패: {e}")
            return False
    
    def get_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        projection_expression: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """항목 조회"""
        try:
            table = self.get_table(table_name)
            
            get_params = {'Key': key}
            if projection_expression:
                get_params['ProjectionExpression'] = projection_expression
            
            response = table.get_item(**get_params)
            return response.get('Item')
            
        except ClientError as e:
            logger.error(f"DynamoDB 항목 조회 실패: {e}")
            return None
    
    def query_items(
        self,
        table_name: str,
        key_condition_expression,
        filter_expression=None,
        projection_expression: Optional[str] = None,
        limit: Optional[int] = None,
        scan_index_forward: bool = True
    ) -> List[Dict[str, Any]]:
        """항목 쿼리"""
        try:
            table = self.get_table(table_name)
            
            query_params = {
                'KeyConditionExpression': key_condition_expression,
                'ScanIndexForward': scan_index_forward
            }
            
            if filter_expression:
                query_params['FilterExpression'] = filter_expression
            if projection_expression:
                query_params['ProjectionExpression'] = projection_expression
            if limit:
                query_params['Limit'] = limit
            
            response = table.query(**query_params)
            return response.get('Items', [])
            
        except ClientError as e:
            logger.error(f"DynamoDB 쿼리 실패: {e}")
            return []
    
    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None
    ) -> bool:
        """항목 업데이트"""
        try:
            table = self.get_table(table_name)
            
            update_params = {
                'Key': key,
                'UpdateExpression': update_expression
            }
            
            if expression_attribute_names:
                update_params['ExpressionAttributeNames'] = expression_attribute_names
            if expression_attribute_values:
                update_params['ExpressionAttributeValues'] = expression_attribute_values
            
            table.update_item(**update_params)
            logger.debug(f"DynamoDB 항목 업데이트 완료: {table_name}")
            return True
            
        except ClientError as e:
            logger.error(f"DynamoDB 항목 업데이트 실패: {e}")
            return False


class S3Client:
    """AWS S3 클라이언트"""
    
    def __init__(self, aws_manager: AWSClientManager):
        self.client = aws_manager.get_client('s3')
        self.resource = aws_manager.get_resource('s3')
    
    def upload_file(
        self,
        file_path: str,
        bucket: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """파일 업로드"""
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.client.upload_file(file_path, bucket, key, ExtraArgs=extra_args)
            logger.info(f"S3 파일 업로드 완료: s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 파일 업로드 실패: {e}")
            return False
    
    def upload_fileobj(
        self,
        fileobj,
        bucket: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """파일 객체 업로드"""
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.client.upload_fileobj(fileobj, bucket, key, ExtraArgs=extra_args)
            logger.info(f"S3 파일 객체 업로드 완료: s3://{bucket}/{key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 파일 객체 업로드 실패: {e}")
            return False
    
    def download_file(self, bucket: str, key: str, file_path: str) -> bool:
        """파일 다운로드"""
        try:
            self.client.download_file(bucket, key, file_path)
            logger.info(f"S3 파일 다운로드 완료: s3://{bucket}/{key} -> {file_path}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 파일 다운로드 실패: {e}")
            return False
    
    def get_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """객체 가져오기"""
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response
        except ClientError as e:
            logger.error(f"S3 객체 조회 실패: {e}")
            return None
    
    def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiration: int = 3600,
        http_method: str = 'GET'
    ) -> Optional[str]:
        """프리사인드 URL 생성"""
        try:
            url = self.client.generate_presigned_url(
                'get_object' if http_method == 'GET' else 'put_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"프리사인드 URL 생성 실패: {e}")
            return None


class CloudWatchClient:
    """AWS CloudWatch 클라이언트"""
    
    def __init__(self, aws_manager: AWSClientManager):
        self.client = aws_manager.get_client('cloudwatch')
        self.logs_client = aws_manager.get_client('logs')
    
    def put_metric_data(
        self,
        namespace: str,
        metric_data: List[Dict[str, Any]]
    ) -> bool:
        """메트릭 데이터 전송"""
        try:
            self.client.put_metric_data(
                Namespace=namespace,
                MetricData=metric_data
            )
            logger.debug(f"CloudWatch 메트릭 전송 완료: {namespace}")
            return True
            
        except ClientError as e:
            logger.error(f"CloudWatch 메트릭 전송 실패: {e}")
            return False
    
    def get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        period: int,
        statistics: List[str],
        dimensions: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """메트릭 통계 조회"""
        try:
            params = {
                'Namespace': namespace,
                'MetricName': metric_name,
                'StartTime': start_time,
                'EndTime': end_time,
                'Period': period,
                'Statistics': statistics
            }
            
            if dimensions:
                params['Dimensions'] = dimensions
            
            response = self.client.get_metric_statistics(**params)
            return response.get('Datapoints', [])
            
        except ClientError as e:
            logger.error(f"CloudWatch 메트릭 통계 조회 실패: {e}")
            return []
    
    def create_log_group(self, log_group_name: str) -> bool:
        """로그 그룹 생성"""
        try:
            self.logs_client.create_log_group(logGroupName=log_group_name)
            logger.info(f"CloudWatch 로그 그룹 생성 완료: {log_group_name}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                logger.debug(f"로그 그룹이 이미 존재: {log_group_name}")
                return True
            logger.error(f"CloudWatch 로그 그룹 생성 실패: {e}")
            return False
    
    def put_log_events(
        self,
        log_group_name: str,
        log_stream_name: str,
        log_events: List[Dict[str, Any]],
        sequence_token: Optional[str] = None
    ) -> Optional[str]:
        """로그 이벤트 전송"""
        try:
            params = {
                'logGroupName': log_group_name,
                'logStreamName': log_stream_name,
                'logEvents': log_events
            }
            
            if sequence_token:
                params['sequenceToken'] = sequence_token
            
            response = self.logs_client.put_log_events(**params)
            return response.get('nextSequenceToken')
            
        except ClientError as e:
            logger.error(f"CloudWatch 로그 이벤트 전송 실패: {e}")
            return None


class AWSServiceFactory:
    """AWS 서비스 팩토리 클래스"""
    
    def __init__(
        self,
        region_name: str = "ap-northeast-2",
        profile_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ):
        self.aws_manager = AWSClientManager(
            region_name=region_name,
            profile_name=profile_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
    
    def get_connect_client(self, instance_id: str) -> ConnectClient:
        """Connect 클라이언트 생성"""
        return ConnectClient(self.aws_manager, instance_id)
    
    def get_lex_client(self) -> LexClient:
        """Lex 클라이언트 생성"""
        return LexClient(self.aws_manager)
    
    def get_dynamodb_client(self) -> DynamoDBClient:
        """DynamoDB 클라이언트 생성"""
        return DynamoDBClient(self.aws_manager)
    
    def get_s3_client(self) -> S3Client:
        """S3 클라이언트 생성"""
        return S3Client(self.aws_manager)
    
    def get_cloudwatch_client(self) -> CloudWatchClient:
        """CloudWatch 클라이언트 생성"""
        return CloudWatchClient(self.aws_manager)


# 전역 팩토리 인스턴스 (싱글톤 패턴)
_aws_factory_instance: Optional[AWSServiceFactory] = None


def get_aws_factory(**kwargs) -> AWSServiceFactory:
    """AWS 서비스 팩토리 인스턴스 가져오기"""
    global _aws_factory_instance
    
    if _aws_factory_instance is None:
        _aws_factory_instance = AWSServiceFactory(**kwargs)
    
    return _aws_factory_instance


def init_aws_services(
    region_name: str = "ap-northeast-2",
    profile_name: Optional[str] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None
) -> AWSServiceFactory:
    """AWS 서비스 초기화"""
    global _aws_factory_instance
    
    _aws_factory_instance = AWSServiceFactory(
        region_name=region_name,
        profile_name=profile_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
    )
    
    logger.info("AWS 서비스 초기화 완료")
    return _aws_factory_instance 