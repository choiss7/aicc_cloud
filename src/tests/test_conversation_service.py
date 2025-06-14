"""
AWS Connect 콜센터용 대화 서비스 단위 테스트
"""
import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime
import uuid

from src.services.conversation_service import ConversationService
from src.models.conversation import Conversation, Message, MessageSource, MessageType, ConversationStatus


class TestConversationService(unittest.TestCase):
    """ConversationService 클래스 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        with patch('src.services.conversation_service.boto3.resource'):
            self.service = ConversationService("test_conversations")
        
        self.test_session_id = 'test_session_123'
        self.test_user_id = 'test_user_456'
        self.test_conversation_id = 'conv_789'
    
    @patch('src.services.conversation_service.boto3.resource')
    @patch('src.services.conversation_service.boto3.client')
    def test_init_with_aws_services(self, mock_boto3_client, mock_boto3_resource):
        """AWS 서비스 초기화 테스트"""
        mock_dynamodb = Mock()
        mock_s3 = Mock()
        mock_cloudwatch = Mock()
        
        mock_boto3_resource.return_value = mock_dynamodb
        mock_boto3_client.side_effect = [mock_s3, mock_cloudwatch]
        
        service = ConversationService("test_table")
        
        self.assertIsNotNone(service.dynamodb)
        self.assertIsNotNone(service.s3_client)
        self.assertIsNotNone(service.cloudwatch)
    
    @patch.object(ConversationService, '_save_conversation')
    @patch.object(ConversationService, '_send_metric')
    @patch.object(ConversationService, 'add_message')
    def test_create_conversation_success(self, mock_add_message, mock_send_metric, mock_save_conversation):
        """대화 생성 성공 테스트"""
        mock_save_conversation.return_value = None
        mock_add_message.return_value = True
        mock_send_metric.return_value = None
        
        result = self.service.create_conversation(
            session_id=self.test_session_id,
            user_id=self.test_user_id,
            channel='web_chat'
        )
        
        self.assertIsInstance(result, Conversation)
        self.assertEqual(result.session_id, self.test_session_id)
        self.assertEqual(result.user_id, self.test_user_id)
        self.assertEqual(result.channel, 'web_chat')
        self.assertEqual(result.status, ConversationStatus.ACTIVE)
        
        mock_save_conversation.assert_called_once()
        mock_add_message.assert_called_once()
        mock_send_metric.assert_called_once_with("ConversationCreated", 1, 'web_chat')


if __name__ == '__main__':
    unittest.main() 