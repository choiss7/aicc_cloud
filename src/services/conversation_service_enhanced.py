"""
AWS Connect 콜센터용 대화 서비스 (DynamoDB 강화 버전)
"""
import json
import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)

class ConversationServiceEnhanced:
    """대화 관리 서비스 (DynamoDB 강화 버전)"""
    
    def __init__(self, table_prefix: str = "aicc"):
        # DynamoDB 테이블 설정
        self.dynamodb = boto3.resource('dynamodb')
        self.conversations_table = self.dynamodb.Table(f"{table_prefix}_conversations")
        self.messages_table = self.dynamodb.Table(f"{table_prefix}_messages")
        self.analytics_table = self.dynamodb.Table(f"{table_prefix}_analytics")
        
        # DynamoDB 클라이언트 (배치 작업용)
        self.dynamodb_client = boto3.client('dynamodb')
        
        # S3 for conversation archives
        self.s3_client = boto3.client('s3')
        self.archive_bucket = 'aicc-conversation-archives'
        
        # CloudWatch for metrics
        self.cloudwatch = boto3.client('cloudwatch')
    
    def create_conversation_enhanced(self, session_id: str, user_id: Optional[str] = None,
                                   channel: str = "web_chat", metadata: Optional[Dict] = None):
        """강화된 대화 생성 기능"""
        try:
            conversation_id = str(uuid.uuid4())
            current_time = datetime.now()
            
            # 트랜잭션으로 대화 및 분석 데이터 동시 저장
            transaction_items = [
                {
                    'Put': {
                        'TableName': self.conversations_table.table_name,
                        'Item': {
                            'conversation_id': conversation_id,
                            'session_id': session_id,
                            'user_id': user_id or 'anonymous',
                            'channel': channel,
                            'status': 'ACTIVE',
                            'created_at': current_time.isoformat(),
                            'metadata': metadata or {},
                            'message_count': 0,
                            'last_activity': current_time.isoformat()
                        }
                    }
                }
            ]
            
            # 트랜잭션 실행
            self.dynamodb_client.transact_write_items(
                TransactItems=transaction_items
            )
            
            # 실시간 분석 업데이트
            self._update_realtime_analytics('conversation_created', channel, current_time)
            
            logger.info(f"강화된 대화 생성 완료: {conversation_id}")
            return conversation_id
            
        except Exception as e:
            logger.error(f"강화된 대화 생성 오류: {str(e)}")
            raise
    
    def save_message_with_analytics(self, conversation_id: str, message_data: Dict):
        """메시지 저장과 동시에 분석 데이터 업데이트"""
        try:
            current_time = datetime.now()
            message_id = str(uuid.uuid4())
            
            # 메시지 저장
            self.messages_table.put_item(
                Item={
                    'conversation_id': conversation_id,
                    'message_id': message_id,
                    'timestamp': current_time.isoformat(),
                    'source': message_data['source'],
                    'content': message_data['content'],
                    'message_type': message_data.get('message_type', 'TEXT'),
                    'metadata': message_data.get('metadata', {})
                }
            )
            
            # 대화 테이블 업데이트 (메시지 카운트, 마지막 활동 시간)
            self.conversations_table.update_item(
                Key={'conversation_id': conversation_id},
                UpdateExpression='ADD message_count :inc SET last_activity = :timestamp',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':timestamp': current_time.isoformat()
                }
            )
            
            # 실시간 분석 업데이트
            self._update_realtime_analytics('message_sent', message_data['source'], current_time)
            
            return message_id
            
        except Exception as e:
            logger.error(f"메시지 저장 및 분석 업데이트 오류: {str(e)}")
            raise
    
    def get_conversation_with_pagination(self, conversation_id: str, 
                                       page_size: int = 50, 
                                       last_evaluated_key: Optional[Dict] = None):
        """페이지네이션을 지원하는 대화 조회"""
        try:
            # 대화 기본 정보 조회
            conversation_response = self.conversations_table.get_item(
                Key={'conversation_id': conversation_id}
            )
            
            if 'Item' not in conversation_response:
                return None
            
            conversation = conversation_response['Item']
            
            # 메시지 페이지네이션 조회
            query_kwargs = {
                'KeyConditionExpression': 'conversation_id = :conversation_id',
                'ExpressionAttributeValues': {':conversation_id': conversation_id},
                'ScanIndexForward': True,  # 시간순 정렬
                'Limit': page_size
            }
            
            if last_evaluated_key:
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
            
            messages_response = self.messages_table.query(**query_kwargs)
            
            return {
                'conversation': conversation,
                'messages': messages_response.get('Items', []),
                'last_evaluated_key': messages_response.get('LastEvaluatedKey'),
                'has_more': 'LastEvaluatedKey' in messages_response
            }
            
        except Exception as e:
            logger.error(f"페이지네이션 대화 조회 오류: {str(e)}")
            return None
    
    def get_analytics_dashboard_data(self, time_range: str = '24h'):
        """대시보드용 분석 데이터 조회"""
        try:
            # 시간 범위 계산
            if time_range == '24h':
                start_time = datetime.now() - timedelta(hours=24)
            elif time_range == '7d':
                start_time = datetime.now() - timedelta(days=7)
            elif time_range == '30d':
                start_time = datetime.now() - timedelta(days=30)
            else:
                start_time = datetime.now() - timedelta(hours=24)
            
            # 분석 데이터 조회
            response = self.analytics_table.scan(
                FilterExpression='#timestamp >= :start_time',
                ExpressionAttributeNames={'#timestamp': 'timestamp'},
                ExpressionAttributeValues={':start_time': start_time.isoformat()}
            )
            
            analytics_items = response.get('Items', [])
            
            # 데이터 집계
            dashboard_data = {
                'total_conversations': 0,
                'total_messages': 0,
                'channel_distribution': {},
                'hourly_activity': {}
            }
            
            for item in analytics_items:
                event_type = item.get('event_type')
                
                if event_type == 'conversation_created':
                    dashboard_data['total_conversations'] += item.get('count', 0)
                    channel = item.get('dimension_value', 'unknown')
                    dashboard_data['channel_distribution'][channel] = \
                        dashboard_data['channel_distribution'].get(channel, 0) + item.get('count', 0)
                
                elif event_type == 'message_sent':
                    dashboard_data['total_messages'] += item.get('count', 0)
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"대시보드 데이터 조회 오류: {str(e)}")
            return {}
    
    def export_conversations_to_s3(self, conversation_ids: List[str], 
                                  export_format: str = 'json'):
        """대화 데이터를 S3로 내보내기"""
        try:
            export_data = []
            
            for conversation_id in conversation_ids:
                conversation_data = self.get_conversation_with_pagination(conversation_id)
                if conversation_data:
                    export_data.append(conversation_data)
            
            # 내보내기 파일 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
            
            # S3 업로드
            s3_key = f"exports/conversations_{timestamp}.json"
            
            self.s3_client.put_object(
                Bucket=self.archive_bucket,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'export_timestamp': timestamp,
                    'conversation_count': str(len(conversation_ids)),
                    'export_format': export_format
                }
            )
            
            # 서명된 URL 생성
            download_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.archive_bucket, 'Key': s3_key},
                ExpiresIn=3600  # 1시간 유효
            )
            
            logger.info(f"대화 데이터 내보내기 완료: {len(conversation_ids)}개 대화 -> {s3_key}")
            
            return {
                'success': True,
                'download_url': download_url,
                's3_key': s3_key,
                'conversation_count': len(conversation_ids)
            }
            
        except Exception as e:
            logger.error(f"S3 내보내기 오류: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def bulk_update_conversation_status(self, updates: List[Dict]):
        """대화 상태 일괄 업데이트"""
        try:
            successful_updates = 0
            failed_updates = 0
            
            for update in updates:
                try:
                    conversation_id = update['conversation_id']
                    new_status = update['status']
                    
                    self.conversations_table.update_item(
                        Key={'conversation_id': conversation_id},
                        UpdateExpression='SET #status = :status, updated_at = :timestamp',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={
                            ':status': new_status,
                            ':timestamp': datetime.now().isoformat()
                        }
                    )
                    
                    successful_updates += 1
                    
                except Exception as update_error:
                    logger.error(f"개별 업데이트 오류: {str(update_error)}")
                    failed_updates += 1
            
            return {
                'successful_updates': successful_updates,
                'failed_updates': failed_updates,
                'total_updates': len(updates)
            }
            
        except Exception as e:
            logger.error(f"일괄 상태 업데이트 오류: {str(e)}")
            return {
                'successful_updates': 0,
                'failed_updates': len(updates),
                'total_updates': len(updates)
            }
    
    def _update_realtime_analytics(self, event_type: str, dimension_value: str, timestamp: datetime):
        """실시간 분석 데이터 업데이트"""
        try:
            # 시간 기반 키 생성 (시간별 집계)
            time_key = timestamp.strftime('%Y%m%d_%H')
            analytics_id = f"{event_type}_{dimension_value}_{time_key}"
            
            # DynamoDB 원자적 카운터 업데이트
            self.analytics_table.update_item(
                Key={'analytics_id': analytics_id},
                UpdateExpression='ADD event_count :inc SET event_type = :event_type, dimension_value = :dimension_value, time_key = :time_key, last_updated = :timestamp',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':event_type': event_type,
                    ':dimension_value': dimension_value,
                    ':time_key': time_key,
                    ':timestamp': timestamp.isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"실시간 분석 업데이트 오류: {str(e)}")
    
    def get_conversation_summary(self, conversation_id: str):
        """대화 요약 정보 조회"""
        try:
            # 대화 기본 정보
            conversation_response = self.conversations_table.get_item(
                Key={'conversation_id': conversation_id}
            )
            
            if 'Item' not in conversation_response:
                return None
            
            conversation = conversation_response['Item']
            
            # 메시지 통계 조회
            messages_response = self.messages_table.query(
                KeyConditionExpression='conversation_id = :conversation_id',
                ExpressionAttributeValues={':conversation_id': conversation_id},
                Select='COUNT'
            )
            
            message_count = messages_response.get('Count', 0)
            
            # 요약 정보 구성
            summary = {
                'conversation_id': conversation_id,
                'status': conversation.get('status'),
                'channel': conversation.get('channel'),
                'created_at': conversation.get('created_at'),
                'last_activity': conversation.get('last_activity'),
                'message_count': message_count,
                'user_id': conversation.get('user_id'),
                'duration_minutes': self._calculate_duration(
                    conversation.get('created_at'),
                    conversation.get('last_activity')
                )
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"대화 요약 조회 오류: {str(e)}")
            return None
    
    def _calculate_duration(self, start_time: str, end_time: str) -> float:
        """대화 지속 시간 계산 (분 단위)"""
        try:
            if not start_time or not end_time:
                return 0.0
            
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            
            duration = (end - start).total_seconds() / 60
            return round(duration, 2)
            
        except Exception:
            return 0.0
