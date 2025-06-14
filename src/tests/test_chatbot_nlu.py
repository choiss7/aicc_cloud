"""
AWS Connect 콜센터용 NLU 모듈 단위 테스트
"""
import pytest
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime

from src.chatbot_nlu import ChatbotNLU, IntentResult, NLUResponse


class TestChatbotNLU(unittest.TestCase):
    """ChatbotNLU 클래스 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.nlu = ChatbotNLU(
            lex_bot_name='test_bot',
            lex_bot_alias='test_alias'
        )
        self.test_session_id = 'test_session_123'
        self.test_session_attributes = {'user_id': 'test_user'}
    
    @patch('src.chatbot_nlu.boto3.Session')
    def test_init_with_environment_variables(self, mock_session):
        """환경 변수를 통한 초기화 테스트"""
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        nlu = ChatbotNLU()
        
        self.assertIsNotNone(nlu.lex_client)
        self.assertEqual(nlu.lex_bot_name, 'AICC_ChatBot')
        self.assertEqual(nlu.lex_bot_alias, 'DRAFT')
    
    def test_confidence_threshold_initialization(self):
        """신뢰도 임계값 초기화 테스트"""
        expected_thresholds = {
            'greeting': 0.7,
            'product_inquiry': 0.8,
            'complaint': 0.75,
            'reservation': 0.85,
            'cancel_request': 0.9,
            'technical_support': 0.8,
            'payment_inquiry': 0.85,
            'default': 0.7
        }
        
        self.assertEqual(self.nlu.confidence_threshold, expected_thresholds)
    
    @patch.object(ChatbotNLU, '_call_lex')
    @patch.object(ChatbotNLU, '_extract_intent')
    @patch.object(ChatbotNLU, '_generate_response')
    @patch.object(ChatbotNLU, '_update_session_attributes')
    def test_process_message_success(self, mock_update_session, mock_generate_response,
                                   mock_extract_intent, mock_call_lex):
        """메시지 처리 성공 테스트"""
        # Mock 설정
        mock_lex_response = {'sessionState': {'intent': {'name': 'greeting'}}}
        mock_call_lex.return_value = mock_lex_response
        
        mock_intent_result = IntentResult(
            intent='greeting',
            confidence=0.9,
            entities={'name': 'John'},
            slots={'name': {'value': {'interpretedValue': 'John'}}}
        )
        mock_extract_intent.return_value = mock_intent_result
        
        mock_generate_response.return_value = ("안녕하세요!", "continue")
        mock_update_session.return_value = {'last_intent': 'greeting'}
        
        # 테스트 실행
        result = self.nlu.process_message(
            "안녕하세요",
            self.test_session_id,
            self.test_session_attributes
        )
        
        # 검증
        self.assertIsInstance(result, NLUResponse)
        self.assertEqual(result.intent_result.intent, 'greeting')
        self.assertEqual(result.response_text, "안녕하세요!")
        self.assertEqual(result.next_action, "continue")
        
        # Mock 호출 검증
        mock_call_lex.assert_called_once()
        mock_extract_intent.assert_called_once()
        mock_generate_response.assert_called_once()
        mock_update_session.assert_called_once()
    
    @patch.object(ChatbotNLU, '_call_lex')
    def test_process_message_error_handling(self, mock_call_lex):
        """메시지 처리 오류 처리 테스트"""
        # Lex 호출 오류 시뮬레이션
        mock_call_lex.side_effect = Exception("Lex API Error")
        
        result = self.nlu.process_message(
            "테스트 메시지",
            self.test_session_id,
            self.test_session_attributes
        )
        
        # 오류 응답 검증
        self.assertIsInstance(result, NLUResponse)
        self.assertEqual(result.intent_result.intent, "error")
        self.assertEqual(result.intent_result.confidence, 0.0)
        self.assertIn("오류가 발생했습니다", result.response_text)
    
    @patch('src.chatbot_nlu.boto3.Session')
    def test_call_lex_success(self, mock_session):
        """Lex 호출 성공 테스트"""
        # Mock 설정
        mock_client = Mock()
        mock_response = {
            'sessionState': {
                'intent': {
                    'name': 'greeting',
                    'nluIntentConfidence': {'score': 0.9}
                }
            }
        }
        mock_client.recognize_text.return_value = mock_response
        mock_session.return_value.client.return_value = mock_client
        
        nlu = ChatbotNLU()
        
        # 테스트 실행
        result = nlu._call_lex("안녕하세요", self.test_session_id, {})
        
        # 검증
        self.assertEqual(result, mock_response)
        mock_client.recognize_text.assert_called_once()
    
    def test_extract_intent_with_slots(self):
        """슬롯이 있는 의도 추출 테스트"""
        lex_response = {
            'sessionState': {
                'intent': {
                    'name': 'product_inquiry',
                    'nluIntentConfidence': {'score': 0.85},
                    'slots': {
                        'product_name': {
                            'value': {'interpretedValue': '스마트폰'}
                        },
                        'product_category': {
                            'value': {'interpretedValue': '전자제품'}
                        }
                    }
                }
            }
        }
        
        result = self.nlu._extract_intent(lex_response)
        
        self.assertEqual(result.intent, 'product_inquiry')
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.entities['product_name'], '스마트폰')
        self.assertEqual(result.entities['product_category'], '전자제품')
    
    def test_extract_intent_without_slots(self):
        """슬롯이 없는 의도 추출 테스트"""
        lex_response = {
            'sessionState': {
                'intent': {
                    'name': 'greeting',
                    'nluIntentConfidence': {'score': 0.9}
                }
            }
        }
        
        result = self.nlu._extract_intent(lex_response)
        
        self.assertEqual(result.intent, 'greeting')
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.entities, {})
    
    def test_generate_response_high_confidence(self):
        """높은 신뢰도 응답 생성 테스트"""
        intent_result = IntentResult(
            intent='greeting',
            confidence=0.9,
            entities={},
            slots={}
        )
        
        response_text, next_action = self.nlu._generate_response(intent_result)
        
        self.assertEqual(response_text, "안녕하세요! 무엇을 도와드릴까요?")
        self.assertEqual(next_action, "continue")
    
    def test_generate_response_low_confidence(self):
        """낮은 신뢰도 응답 생성 테스트"""
        intent_result = IntentResult(
            intent='product_inquiry',
            confidence=0.5,  # 임계값(0.8)보다 낮음
            entities={},
            slots={}
        )
        
        response_text, next_action = self.nlu._generate_response(intent_result)
        
        self.assertIn("좀 더 구체적으로", response_text)
        self.assertEqual(next_action, "clarify")
    
    def test_generate_response_complaint_escalation(self):
        """불만 처리 에스컬레이션 테스트"""
        intent_result = IntentResult(
            intent='complaint',
            confidence=0.9,
            entities={},
            slots={}
        )
        
        response_text, next_action = self.nlu._generate_response(intent_result)
        
        self.assertIn("상담원에게 연결", response_text)
        self.assertEqual(next_action, "escalate")
    
    def test_get_clarification_response(self):
        """명확화 응답 테스트"""
        test_cases = [
            ('product_inquiry', "상품 문의에 대해 좀 더 구체적으로"),
            ('complaint', "불편사항에 대해 자세히 설명"),
            ('unknown_intent', "좀 더 자세히 말씀해 주시겠어요?")
        ]
        
        for intent, expected_text in test_cases:
            response = self.nlu._get_clarification_response(intent)
            self.assertIn(expected_text, response)
    
    def test_update_session_attributes(self):
        """세션 속성 업데이트 테스트"""
        intent_result = IntentResult(
            intent='product_inquiry',
            confidence=0.85,
            entities={'product_name': '스마트폰'},
            slots={}
        )
        
        current_attributes = {'user_id': 'test_user'}
        
        updated_attributes = self.nlu._update_session_attributes(
            intent_result, current_attributes
        )
        
        self.assertEqual(updated_attributes['user_id'], 'test_user')
        self.assertEqual(updated_attributes['last_intent'], 'product_inquiry')
        self.assertEqual(updated_attributes['last_confidence'], '0.85')
        self.assertEqual(updated_attributes['entity_product_name'], '스마트폰')
    
    def test_get_supported_intents(self):
        """지원되는 의도 목록 테스트"""
        intents = self.nlu.get_supported_intents()
        
        expected_intents = [
            'greeting', 'product_inquiry', 'complaint', 'reservation',
            'cancel_request', 'technical_support', 'payment_inquiry'
        ]
        
        for intent in expected_intents:
            self.assertIn(intent, intents)
    
    def test_update_confidence_threshold(self):
        """신뢰도 임계값 업데이트 테스트"""
        original_threshold = self.nlu.confidence_threshold['greeting']
        new_threshold = 0.95
        
        self.nlu.update_confidence_threshold('greeting', new_threshold)
        
        self.assertEqual(self.nlu.confidence_threshold['greeting'], new_threshold)
        self.assertNotEqual(self.nlu.confidence_threshold['greeting'], original_threshold)
    
    def test_create_error_response(self):
        """오류 응답 생성 테스트"""
        error_response = self.nlu._create_error_response()
        
        self.assertIsInstance(error_response, NLUResponse)
        self.assertEqual(error_response.intent_result.intent, "error")
        self.assertEqual(error_response.intent_result.confidence, 0.0)
        self.assertIn("오류가 발생했습니다", error_response.response_text)
        self.assertEqual(error_response.next_action, "error")


class TestIntentResult(unittest.TestCase):
    """IntentResult 데이터클래스 테스트"""
    
    def test_intent_result_creation(self):
        """IntentResult 생성 테스트"""
        intent_result = IntentResult(
            intent='greeting',
            confidence=0.9,
            entities={'name': 'John'},
            slots={'name': {'value': 'John'}}
        )
        
        self.assertEqual(intent_result.intent, 'greeting')
        self.assertEqual(intent_result.confidence, 0.9)
        self.assertEqual(intent_result.entities['name'], 'John')
        self.assertIn('name', intent_result.slots)


class TestNLUResponse(unittest.TestCase):
    """NLUResponse 데이터클래스 테스트"""
    
    def test_nlu_response_creation(self):
        """NLUResponse 생성 테스트"""
        intent_result = IntentResult(
            intent='greeting',
            confidence=0.9,
            entities={},
            slots={}
        )
        
        nlu_response = NLUResponse(
            intent_result=intent_result,
            response_text="안녕하세요!",
            next_action="continue",
            session_attributes={'last_intent': 'greeting'}
        )
        
        self.assertEqual(nlu_response.intent_result.intent, 'greeting')
        self.assertEqual(nlu_response.response_text, "안녕하세요!")
        self.assertEqual(nlu_response.next_action, "continue")
        self.assertEqual(nlu_response.session_attributes['last_intent'], 'greeting')


# 통합 테스트
class TestNLUIntegration(unittest.TestCase):
    """NLU 통합 테스트"""
    
    @patch('src.chatbot_nlu.boto3.Session')
    def test_full_conversation_flow(self, mock_session):
        """전체 대화 흐름 테스트"""
        # Mock 설정
        mock_client = Mock()
        mock_session.return_value.client.return_value = mock_client
        
        # 인사 -> 상품 문의 -> 불만 -> 에스컬레이션 시나리오
        conversation_flow = [
            {
                'input': '안녕하세요',
                'expected_intent': 'greeting',
                'lex_response': {
                    'sessionState': {
                        'intent': {
                            'name': 'greeting',
                            'nluIntentConfidence': {'score': 0.9}
                        }
                    }
                }
            },
            {
                'input': '스마트폰 문의드립니다',
                'expected_intent': 'product_inquiry',
                'lex_response': {
                    'sessionState': {
                        'intent': {
                            'name': 'product_inquiry',
                            'nluIntentConfidence': {'score': 0.85},
                            'slots': {
                                'product_name': {
                                    'value': {'interpretedValue': '스마트폰'}
                                }
                            }
                        }
                    }
                }
            },
            {
                'input': '불만이 있습니다',
                'expected_intent': 'complaint',
                'lex_response': {
                    'sessionState': {
                        'intent': {
                            'name': 'complaint',
                            'nluIntentConfidence': {'score': 0.9}
                        }
                    }
                }
            }
        ]
        
        nlu = ChatbotNLU()
        session_attributes = {}
        
        for step in conversation_flow:
            mock_client.recognize_text.return_value = step['lex_response']
            
            result = nlu.process_message(
                step['input'],
                'test_session',
                session_attributes
            )
            
            self.assertEqual(result.intent_result.intent, step['expected_intent'])
            session_attributes = result.session_attributes


if __name__ == '__main__':
    unittest.main() 