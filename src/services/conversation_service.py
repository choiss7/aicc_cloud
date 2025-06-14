"""
AWS Connect 콜센터용 대화 서비스
"""
import json
import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import uuid

from ..models.conversation import Conversation, Message, MessageSource, MessageType, ConversationStatus

logger = logging.getLogger(__name__)

class ConversationService:
    """대화 관리 서비스"""
    
    def __init__(self, dynamodb_table_name: str = "conversations"):
        self.dynamodb = boto3.resource('dynamodb')
        self.conversations_table = self.dynamodb.Table(dynamodb_table_name)
        self.messages_table = self.dynamodb.Table(f"{dynamodb_table_name}_messages")
        
        # S3 for conversation archives
        self.s3_client = boto3.client('s3')
        self.archive_bucket = "aicc-conversation-archives"
        
        # CloudWatch for metrics
        self.cloudwatch = boto3.client('cloudwatch')
    
    def create_conversation(self, session_id: str, user_id: Optional[str] = None,
                          channel: str = "web_chat") -> Conversation:
        """
        새 대화 생성
        
        Args:
            session_id: 세션 ID
            user_id: 사용자 ID
            channel: 채널 (web_chat, voice, sms, etc.)
            
        Returns:
            Conversation: 생성된 대화 객체
        """
        try:
            conversation_id = self._generate_conversation_id()
            
            conversation = Conversation(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                channel=channel,
                status=ConversationStatus.ACTIVE
            )
            
            # DynamoDB에 저장
            self._save_conversation(conversation)
            
            # 시스템 메시지 추가
            welcome_message = self._create_system_message(
                conversation_id,
                "대화가 시작되었습니다."
            )
            self.add_message(conversation, welcome_message)
            
            # 메트릭 전송
            self._send_metric("ConversationCreated", 1, channel)
            
            logger.info(f"새 대화 생성: {conversation_id}")
            return conversation
            
        except Exception as e:
            logger.error(f"대화 생성 오류: {str(e)}")
            raise
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        대화 조회
        
        Args:
            conversation_id: 대화 ID
            
        Returns:
            Optional[Conversation]: 대화 객체 또는 None
        """
        try:
            # DynamoDB에서 대화 정보 조회
            response = self.conversations_table.get_item(
                Key={'conversation_id': conversation_id}
            )
            
            if 'Item' not in response:
                return None
            
            conversation_data = response['Item']
            
            # 메시지 조회
            messages = self._get_conversation_messages(conversation_id)
            conversation_data['messages'] = [msg.to_dict() for msg in messages]
            
            return Conversation.from_dict(conversation_data)
            
        except Exception as e:
            logger.error(f"대화 조회 오류: {str(e)}")
            return None
    
    def add_message(self, conversation: Conversation, message: Message) -> bool:
        """
        메시지 추가
        
        Args:
            conversation: 대화 객체
            message: 메시지 객체
            
        Returns:
            bool: 성공 여부
        """
        try:
            # 대화에 메시지 추가
            conversation.add_message(message)
            
            # DynamoDB에 메시지 저장
            self._save_message(message)
            
            # 대화 정보 업데이트
            self._update_conversation(conversation)
            
            # 실시간 알림 (필요시)
            if conversation.assigned_agent_id:
                self._notify_agent(conversation.assigned_agent_id, message)
            
            return True
            
        except Exception as e:
            logger.error(f"메시지 추가 오류: {str(e)}")
            return False
    
    def send_user_message(self, conversation_id: str, content: str,
                         message_type: MessageType = MessageType.TEXT) -> Optional[Message]:
        """
        사용자 메시지 전송
        
        Args:
            conversation_id: 대화 ID
            content: 메시지 내용
            message_type: 메시지 타입
            
        Returns:
            Optional[Message]: 생성된 메시지 또는 None
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                logger.error(f"대화를 찾을 수 없음: {conversation_id}")
                return None
            
            # 사용자 메시지 생성
            message = Message(
                message_id=self._generate_message_id(),
                conversation_id=conversation_id,
                source=MessageSource.USER,
                message_type=message_type,
                content=content
            )
            
            # 메시지 추가
            if self.add_message(conversation, message):
                return message
            
            return None
            
        except Exception as e:
            logger.error(f"사용자 메시지 전송 오류: {str(e)}")
            return None
    
    def send_bot_message(self, conversation_id: str, content: str,
                        metadata: Optional[Dict] = None) -> Optional[Message]:
        """
        봇 메시지 전송
        
        Args:
            conversation_id: 대화 ID
            content: 메시지 내용
            metadata: 메타데이터
            
        Returns:
            Optional[Message]: 생성된 메시지 또는 None
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return None
            
            # 봇 메시지 생성
            message = Message(
                message_id=self._generate_message_id(),
                conversation_id=conversation_id,
                source=MessageSource.BOT,
                message_type=MessageType.TEXT,
                content=content,
                metadata=metadata or {}
            )
            
            if self.add_message(conversation, message):
                return message
            
            return None
            
        except Exception as e:
            logger.error(f"봇 메시지 전송 오류: {str(e)}")
            return None
    
    def send_agent_message(self, conversation_id: str, agent_id: str,
                          content: str) -> Optional[Message]:
        """
        상담원 메시지 전송
        
        Args:
            conversation_id: 대화 ID
            agent_id: 상담원 ID
            content: 메시지 내용
            
        Returns:
            Optional[Message]: 생성된 메시지 또는 None
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return None
            
            # 상담원이 배정되어 있는지 확인
            if conversation.assigned_agent_id != agent_id:
                logger.warning(f"상담원 {agent_id}가 대화 {conversation_id}에 배정되지 않음")
            
            # 상담원 메시지 생성
            message = Message(
                message_id=self._generate_message_id(),
                conversation_id=conversation_id,
                source=MessageSource.AGENT,
                message_type=MessageType.TEXT,
                content=content,
                metadata={'agent_id': agent_id}
            )
            
            if self.add_message(conversation, message):
                return message
            
            return None
            
        except Exception as e:
            logger.error(f"상담원 메시지 전송 오류: {str(e)}")
            return None
    
    def escalate_conversation(self, conversation_id: str, escalation_id: str,
                            reason: str) -> bool:
        """
        대화 에스컬레이션
        
        Args:
            conversation_id: 대화 ID
            escalation_id: 에스컬레이션 ID
            reason: 에스컬레이션 사유
            
        Returns:
            bool: 성공 여부
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return False
            
            # 대화 에스컬레이션 처리
            conversation.escalate(escalation_id)
            conversation.update_context('escalation_reason', reason)
            
            # 에스컬레이션 시스템 메시지 추가
            system_message = self._create_system_message(
                conversation_id,
                "상담원에게 연결 중입니다. 잠시만 기다려주세요."
            )
            self.add_message(conversation, system_message)
            
            # 대화 정보 업데이트
            self._update_conversation(conversation)
            
            # 메트릭 전송
            self._send_metric("ConversationEscalated", 1, conversation.channel)
            
            logger.info(f"대화 에스컬레이션: {conversation_id} -> {escalation_id}")
            return True
            
        except Exception as e:
            logger.error(f"대화 에스컬레이션 오류: {str(e)}")
            return False
    
    def assign_agent(self, conversation_id: str, agent_id: str) -> bool:
        """
        상담원 배정
        
        Args:
            conversation_id: 대화 ID
            agent_id: 상담원 ID
            
        Returns:
            bool: 성공 여부
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return False
            
            # 상담원 배정
            conversation.assign_agent(agent_id)
            
            # 배정 안내 메시지 추가
            system_message = self._create_system_message(
                conversation_id,
                f"상담원이 배정되었습니다. 곧 응답드리겠습니다."
            )
            self.add_message(conversation, system_message)
            
            # 대화 정보 업데이트
            self._update_conversation(conversation)
            
            logger.info(f"상담원 배정: {conversation_id} -> {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"상담원 배정 오류: {str(e)}")
            return False
    
    def complete_conversation(self, conversation_id: str, summary: Optional[str] = None) -> bool:
        """
        대화 완료
        
        Args:
            conversation_id: 대화 ID
            summary: 대화 요약
            
        Returns:
            bool: 성공 여부
        """
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return False
            
            # 대화 완료 처리
            conversation.set_status(ConversationStatus.COMPLETED)
            
            if summary:
                conversation.update_context('summary', summary)
            
            # 대화 요약 생성
            conversation.generate_summary()
            
            # 완료 시스템 메시지 추가
            system_message = self._create_system_message(
                conversation_id,
                "대화가 완료되었습니다. 이용해 주셔서 감사합니다."
            )
            self.add_message(conversation, system_message)
            
            # 대화 정보 업데이트
            self._update_conversation(conversation)
            
            # 아카이브 처리 (필요시)
            self._archive_conversation(conversation)
            
            # 메트릭 전송
            self._send_metric("ConversationCompleted", 1, conversation.channel)
            duration = conversation.get_conversation_duration()
            self._send_metric("ConversationDuration", duration, conversation.channel)
            
            logger.info(f"대화 완료: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"대화 완료 오류: {str(e)}")
            return False
    
    def get_active_conversations(self, user_id: Optional[str] = None,
                               agent_id: Optional[str] = None) -> List[Conversation]:
        """
        활성 대화 목록 조회
        
        Args:
            user_id: 사용자 ID (선택)
            agent_id: 상담원 ID (선택)
            
        Returns:
            List[Conversation]: 활성 대화 목록
        """
        try:
            scan_kwargs = {
                'FilterExpression': 'conversation_status = :status',
                'ExpressionAttributeValues': {
                    ':status': ConversationStatus.ACTIVE.value
                }
            }
            
            if user_id:
                scan_kwargs['FilterExpression'] += ' AND user_id = :user_id'
                scan_kwargs['ExpressionAttributeValues'][':user_id'] = user_id
            
            if agent_id:
                scan_kwargs['FilterExpression'] += ' AND assigned_agent_id = :agent_id'
                scan_kwargs['ExpressionAttributeValues'][':agent_id'] = agent_id
            
            response = self.conversations_table.scan(**scan_kwargs)
            
            conversations = []
            for item in response.get('Items', []):
                conversation = Conversation.from_dict(item)
                conversations.append(conversation)
            
            return conversations
            
        except Exception as e:
            logger.error(f"활성 대화 조회 오류: {str(e)}")
            return []
    
    def search_conversations(self, query: str, start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> List[Conversation]:
        """
        대화 검색
        
        Args:
            query: 검색 쿼리
            start_date: 시작 날짜
            end_date: 종료 날짜
            
        Returns:
            List[Conversation]: 검색 결과
        """
        try:
            # 기본적인 텍스트 검색 구현
            # 실제 운영에서는 ElasticSearch 등을 사용할 수 있음
            
            scan_kwargs = {}
            filter_expressions = []
            expression_values = {}
            
            if start_date:
                filter_expressions.append('created_at >= :start_date')
                expression_values[':start_date'] = start_date
            
            if end_date:
                filter_expressions.append('created_at <= :end_date')
                expression_values[':end_date'] = end_date
            
            if filter_expressions:
                scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
                scan_kwargs['ExpressionAttributeValues'] = expression_values
            
            response = self.conversations_table.scan(**scan_kwargs)
            
            conversations = []
            for item in response.get('Items', []):
                conversation = Conversation.from_dict(item)
                
                # 메시지 내용에서 검색어 확인
                if self._conversation_matches_query(conversation, query):
                    conversations.append(conversation)
            
            return conversations
            
        except Exception as e:
            logger.error(f"대화 검색 오류: {str(e)}")
            return []
    
    def _generate_conversation_id(self) -> str:
        """대화 ID 생성"""
        return f"conv_{uuid.uuid4().hex[:12]}"
    
    def _generate_message_id(self) -> str:
        """메시지 ID 생성"""
        return f"msg_{uuid.uuid4().hex[:12]}"
    
    def _create_system_message(self, conversation_id: str, content: str) -> Message:
        """시스템 메시지 생성"""
        return Message(
            message_id=self._generate_message_id(),
            conversation_id=conversation_id,
            source=MessageSource.SYSTEM,
            message_type=MessageType.SYSTEM,
            content=content
        )
    
    def _save_conversation(self, conversation: Conversation):
        """대화 저장"""
        try:
            conversation_data = conversation.to_dict()
            # 메시지는 별도 테이블에 저장하므로 제외
            conversation_data.pop('messages', None)
            
            self.conversations_table.put_item(Item=conversation_data)
            
        except Exception as e:
            logger.error(f"대화 저장 오류: {str(e)}")
            raise
    
    def _save_message(self, message: Message):
        """메시지 저장"""
        try:
            self.messages_table.put_item(Item=message.to_dict())
            
        except Exception as e:
            logger.error(f"메시지 저장 오류: {str(e)}")
            raise
    
    def _update_conversation(self, conversation: Conversation):
        """대화 정보 업데이트"""
        try:
            conversation_data = conversation.to_dict()
            conversation_data.pop('messages', None)
            
            self.conversations_table.put_item(Item=conversation_data)
            
        except Exception as e:
            logger.error(f"대화 업데이트 오류: {str(e)}")
            raise
    
    def _get_conversation_messages(self, conversation_id: str) -> List[Message]:
        """대화 메시지 조회"""
        try:
            response = self.messages_table.query(
                IndexName='conversation-index',
                KeyConditionExpression='conversation_id = :conv_id',
                ExpressionAttributeValues={':conv_id': conversation_id},
                ScanIndexForward=True  # 시간순 정렬
            )
            
            messages = []
            for item in response.get('Items', []):
                message = Message.from_dict(item)
                messages.append(message)
            
            return messages
            
        except Exception as e:
            logger.error(f"대화 메시지 조회 오류: {str(e)}")
            return []
    
    def _notify_agent(self, agent_id: str, message: Message):
        """상담원에게 알림 전송"""
        try:
            # 실제 구현에서는 WebSocket, SNS 등을 사용
            logger.info(f"상담원 {agent_id}에게 새 메시지 알림 전송")
            
        except Exception as e:
            logger.error(f"상담원 알림 전송 오류: {str(e)}")
    
    def _archive_conversation(self, conversation: Conversation):
        """대화 아카이브"""
        try:
            # S3에 대화 내용 저장
            archive_key = f"conversations/{conversation.created_at[:7]}/{conversation.conversation_id}.json"
            
            self.s3_client.put_object(
                Bucket=self.archive_bucket,
                Key=archive_key,
                Body=json.dumps(conversation.to_dict(), ensure_ascii=False),
                ContentType='application/json'
            )
            
            logger.info(f"대화 아카이브 완료: {conversation.conversation_id}")
            
        except Exception as e:
            logger.error(f"대화 아카이브 오류: {str(e)}")
    
    def _send_metric(self, metric_name: str, value: float, dimension_value: str):
        """CloudWatch 메트릭 전송"""
        try:
            self.cloudwatch.put_metric_data(
                Namespace='AICC/Conversations',
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': 'Count',
                        'Dimensions': [
                            {
                                'Name': 'Channel',
                                'Value': dimension_value
                            }
                        ]
                    }
                ]
            )
            
        except Exception as e:
            logger.error(f"메트릭 전송 오류: {str(e)}")
    
    def _conversation_matches_query(self, conversation: Conversation, query: str) -> bool:
        """대화가 검색 쿼리와 일치하는지 확인"""
        query_lower = query.lower()
        
        # 대화 내용에서 검색
        for message in conversation.messages:
            if query_lower in message.content.lower():
                return True
        
        # 태그에서 검색
        for tag in conversation.tags:
            if query_lower in tag.lower():
                return True
        
        # 컨텍스트에서 검색
        for key, value in conversation.context.items():
            if isinstance(value, str) and query_lower in value.lower():
                return True
        
        return False 