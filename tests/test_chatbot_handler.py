"""
챗봇 핸들러 테스트
pytest를 사용한 로컬 개발환경 테스트
"""
import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.handlers.chatbot_handler import ChatbotHandler, lambda_handler


class TestChatbotHandler:
    """챗봇 핸들러 테스트 클래스"""
    
    @pytest.fixture
    def handler(self):
        """테스트용 핸들러 인스턴스"""
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            return ChatbotHandler()
    
    def test_handler_initialization(self, handler):
        """핸들러 초기화 테스트"""
        assert handler.environment == 'development'
        assert handler.use_mock_services is True
    
    def test_greeting_message(self, handler):
        """인사 메시지 처리 테스트"""
        result = handler.process_chat_message("안녕하세요", "test_session")
        
        assert result['success'] is True
        assert result['intent'] == 'greeting'
        assert result['confidence'] >= 0.9
        assert '안녕하세요' in result['response_text']
        assert result['mock_response'] is True
    
    def test_product_inquiry(self, handler):
        """상품 문의 처리 테스트"""
        result = handler.process_chat_message("상품 가격이 궁금해요", "test_session")
        
        assert result['success'] is True
        assert result['intent'] == 'product_inquiry'
        assert result['confidence'] >= 0.8
        assert '상품' in result['response_text']
    
    def test_complaint_message(self, handler):
        """불만 메시지 처리 테스트"""
        result = handler.process_chat_message("서비스에 불만이 있어요", "test_session")
        
        assert result['success'] is True
        assert result['intent'] == 'complaint'
        assert result['confidence'] >= 0.8
        assert '죄송' in result['response_text'] or '상담원' in result['response_text']
    
    def test_reservation_message(self, handler):
        """예약 메시지 처리 테스트"""
        result = handler.process_chat_message("예약하고 싶어요", "test_session")
        
        assert result['success'] is True
        assert result['intent'] == 'reservation'
        assert result['confidence'] >= 0.8
        assert '예약' in result['response_text']
    
    def test_general_inquiry(self, handler):
        """일반 문의 처리 테스트"""
        result = handler.process_chat_message("도움이 필요해요", "test_session")
        
        assert result['success'] is True
        assert result['intent'] == 'general_inquiry'
        assert result['confidence'] >= 0.5
        assert '문의' in result['response_text'] or '도움' in result['response_text']
    
    def test_escalation_process(self, handler):
        """에스컬레이션 처리 테스트"""
        result = handler.process_escalation("test_session", "complaint")
        
        assert result['success'] is True
        assert 'escalation_id' in result
        assert result['escalation_id'].startswith('ESC_')
        assert '상담원' in result['message']
        assert result['mock_response'] is True
    
    def test_context_handling(self, handler):
        """컨텍스트 처리 테스트"""
        context = {'previous_intent': 'greeting', 'user_name': '홍길동'}
        result = handler.process_chat_message("상품 문의", "test_session", context)
        
        assert result['success'] is True
        assert result['context'] == context
    
    def test_error_handling(self, handler):
        """오류 처리 테스트"""
        # 빈 메시지 처리
        result = handler.process_chat_message("", "test_session")
        assert result['success'] is True  # 빈 메시지도 일반 문의로 처리
        
        # None 메시지 처리
        with patch.object(handler, '_mock_chat_response', side_effect=Exception("Test error")):
            result = handler.process_chat_message("테스트", "test_session")
            assert result['success'] is False
            assert 'error' in result


class TestLambdaHandler:
    """Lambda 핸들러 테스트 클래스"""
    
    def test_chat_request(self):
        """채팅 요청 테스트"""
        event = {
            'request_type': 'chat',
            'message': '안녕하세요',
            'session_id': 'test_session'
        }
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        assert 'body' in result
        
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['intent'] == 'greeting'
    
    def test_escalation_request(self):
        """에스컬레이션 요청 테스트"""
        event = {
            'request_type': 'escalation',
            'session_id': 'test_session',
            'reason': 'complaint'
        }
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200
        
        body = json.loads(result['body'])
        assert body['success'] is True
        assert 'escalation_id' in body
    
    def test_invalid_request_type(self):
        """잘못된 요청 타입 테스트"""
        event = {
            'request_type': 'invalid_type',
            'message': '테스트'
        }
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
        
        body = json.loads(result['body'])
        assert body['success'] is False
        assert 'error' in body
    
    def test_missing_parameters(self):
        """필수 파라미터 누락 테스트"""
        event = {
            'request_type': 'chat'
            # message 누락
        }
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            result = lambda_handler(event, {})
        
        assert result['statusCode'] == 200  # 빈 메시지도 처리됨
        
        body = json.loads(result['body'])
        assert body['success'] is True
    
    def test_cors_headers(self):
        """CORS 헤더 테스트"""
        event = {
            'request_type': 'chat',
            'message': '테스트'
        }
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            result = lambda_handler(event, {})
        
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert result['headers']['Access-Control-Allow-Origin'] == '*'
    
    def test_exception_handling(self):
        """예외 처리 테스트"""
        event = {
            'request_type': 'chat',
            'message': '테스트'
        }
        
        with patch('src.handlers.chatbot_handler.ChatbotHandler', side_effect=Exception("Test error")):
            result = lambda_handler(event, {})
        
        assert result['statusCode'] == 500
        
        body = json.loads(result['body'])
        assert body['success'] is False
        assert 'error' in body


class TestAWSIntegration:
    """AWS 서비스 통합 테스트"""
    
    @pytest.fixture
    def aws_handler(self):
        """AWS 환경용 핸들러"""
        with patch.dict(os.environ, {'ENVIRONMENT': 'production'}):
            with patch('boto3.resource'), patch('boto3.client'):
                return ChatbotHandler()
    
    def test_aws_services_initialization(self, aws_handler):
        """AWS 서비스 초기화 테스트"""
        # AWS 환경에서는 실제 서비스 사용 시도
        assert aws_handler.environment == 'production'
        # 모킹으로 인해 실제로는 mock_services가 True가 될 수 있음
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_aws_service_fallback(self, mock_client, mock_resource):
        """AWS 서비스 실패 시 폴백 테스트"""
        # AWS 서비스 초기화 실패 시뮬레이션
        mock_resource.side_effect = Exception("AWS connection failed")
        mock_client.side_effect = Exception("AWS connection failed")
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'production'}):
            handler = ChatbotHandler()
            # 실패 시 mock_services로 폴백되어야 함
            assert handler.use_mock_services is True
    
    def test_dynamodb_save_simulation(self, aws_handler):
        """DynamoDB 저장 시뮬레이션 테스트"""
        # 실제 AWS 환경이 아니므로 모킹된 응답 확인
        result = aws_handler.process_chat_message("테스트", "test_session")
        assert result['success'] is True


class TestPerformance:
    """성능 테스트"""
    
    def test_response_time(self):
        """응답 시간 테스트"""
        import time
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            handler = ChatbotHandler()
        
        start_time = time.time()
        result = handler.process_chat_message("안녕하세요", "test_session")
        end_time = time.time()
        
        response_time = end_time - start_time
        assert response_time < 1.0  # 1초 이내 응답
        assert result['success'] is True
    
    def test_concurrent_requests(self):
        """동시 요청 처리 테스트"""
        import threading
        import time
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            handler = ChatbotHandler()
        
        results = []
        
        def make_request(message, session_id):
            result = handler.process_chat_message(f"{message}_{session_id}", f"session_{session_id}")
            results.append(result)
        
        # 10개의 동시 요청
        threads = []
        start_time = time.time()
        
        for i in range(10):
            thread = threading.Thread(target=make_request, args=("테스트", i))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        
        # 모든 요청이 성공했는지 확인
        assert len(results) == 10
        assert all(result['success'] for result in results)
        
        # 전체 처리 시간이 합리적인지 확인 (10초 이내)
        total_time = end_time - start_time
        assert total_time < 10.0


# 통합 테스트
class TestIntegration:
    """통합 테스트"""
    
    def test_full_conversation_flow(self):
        """전체 대화 플로우 테스트"""
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            handler = ChatbotHandler()
        
        # 1. 인사
        result1 = handler.process_chat_message("안녕하세요", "integration_test")
        assert result1['success'] is True
        assert result1['intent'] == 'greeting'
        
        # 2. 상품 문의
        result2 = handler.process_chat_message("상품 가격 알려주세요", "integration_test")
        assert result2['success'] is True
        assert result2['intent'] == 'product_inquiry'
        
        # 3. 불만 제기
        result3 = handler.process_chat_message("서비스가 별로예요", "integration_test")
        assert result3['success'] is True
        assert result3['intent'] == 'complaint'
        
        # 4. 에스컬레이션
        result4 = handler.process_escalation("integration_test", "complaint")
        assert result4['success'] is True
        assert 'escalation_id' in result4
    
    def test_lambda_handler_integration(self):
        """Lambda 핸들러 통합 테스트"""
        # 다양한 시나리오 테스트
        test_scenarios = [
            {
                'event': {'request_type': 'chat', 'message': '안녕하세요', 'session_id': 'test1'},
                'expected_intent': 'greeting'
            },
            {
                'event': {'request_type': 'chat', 'message': '상품 문의', 'session_id': 'test2'},
                'expected_intent': 'product_inquiry'
            },
            {
                'event': {'request_type': 'escalation', 'session_id': 'test3', 'reason': 'complaint'},
                'expected_success': True
            }
        ]
        
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
            for scenario in test_scenarios:
                result = lambda_handler(scenario['event'], {})
                assert result['statusCode'] == 200
                
                body = json.loads(result['body'])
                assert body['success'] is True
                
                if 'expected_intent' in scenario:
                    assert body['intent'] == scenario['expected_intent']


if __name__ == '__main__':
    # 직접 실행 시 간단한 테스트 수행
    print("=== 챗봇 핸들러 테스트 실행 ===")
    
    # 기본 테스트
    with patch.dict(os.environ, {'ENVIRONMENT': 'development'}):
        handler = ChatbotHandler()
    
    test_messages = [
        "안녕하세요",
        "상품 가격이 궁금해요",
        "서비스에 불만이 있어요",
        "예약하고 싶어요"
    ]
    
    for msg in test_messages:
        result = handler.process_chat_message(msg, "direct_test")
        print(f"메시지: {msg}")
        print(f"의도: {result['intent']}, 신뢰도: {result['confidence']}")
        print(f"응답: {result['response_text']}")
        print("-" * 50) 