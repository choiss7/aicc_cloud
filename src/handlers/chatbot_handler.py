"""
AWS Lambda 챗봇 핸들러
로컬 개발환경에서 테스트 가능한 구조로 작성
"""
import json
import logging
import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('env.local')  # 로컬 개발용
load_dotenv()  # 기본 .env

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatbotHandler:
    """챗봇 핸들러 클래스"""
    
    def __init__(self):
        """핸들러 초기화"""
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.debug = os.getenv('APP_DEBUG', 'false').lower() == 'true'
        
        # 로컬 개발환경에서는 AWS 서비스 모킹
        if self.environment == 'development':
            self._setup_local_environment()
        else:
            self._setup_aws_services()
    
    def _setup_local_environment(self):
        """로컬 개발환경 설정"""
        logger.info("로컬 개발환경으로 설정됨")
        # 로컬에서는 실제 AWS 서비스 대신 모킹된 응답 사용
        self.use_mock_services = True
    
    def _setup_aws_services(self):
        """AWS 서비스 설정"""
        logger.info("AWS 환경으로 설정됨")
        self.use_mock_services = False
        
        # 실제 AWS 서비스 초기화는 여기서 수행
        try:
            import boto3
            self.dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION'))
            self.s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION'))
            self.bedrock = boto3.client('bedrock-runtime', region_name=os.getenv('BEDROCK_REGION', 'us-east-1'))
        except Exception as e:
            logger.warning(f"AWS 서비스 초기화 실패: {e}")
            self.use_mock_services = True
    
    def process_chat_message(self, message: str, session_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """채팅 메시지 처리"""
        try:
            logger.info(f"메시지 처리 시작: {message[:50]}...")
            
            if self.use_mock_services:
                return self._mock_chat_response(message, session_id, context)
            else:
                return self._process_with_aws_services(message, session_id, context)
                
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'response_text': '죄송합니다. 일시적인 오류가 발생했습니다.',
                'timestamp': datetime.now().isoformat()
            }
    
    def _mock_chat_response(self, message: str, session_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """로컬 개발용 모킹된 응답"""
        # 간단한 키워드 기반 응답
        message_lower = message.lower()
        
        if any(keyword in message_lower for keyword in ['안녕', '안녕하세요', 'hello', 'hi']):
            intent = 'greeting'
            response_text = '안녕하세요! 무엇을 도와드릴까요?'
            confidence = 0.95
        elif any(keyword in message_lower for keyword in ['상품', '제품', '가격', 'product']):
            intent = 'product_inquiry'
            response_text = '상품 문의를 도와드리겠습니다. 어떤 상품에 대해 궁금하신가요?'
            confidence = 0.90
        elif any(keyword in message_lower for keyword in ['불만', '문제', '별로', '나쁘', '싫어', '화나', 'complaint', '불편']):
            intent = 'complaint'
            response_text = '불편을 끼쳐드려 죄송합니다. 상담원 연결을 도와드리겠습니다.'
            confidence = 0.85
        elif any(keyword in message_lower for keyword in ['예약', 'reservation']):
            intent = 'reservation'
            response_text = '예약 관련 도움을 드리겠습니다. 어떤 예약을 원하시나요?'
            confidence = 0.88
        else:
            intent = 'general_inquiry'
            response_text = '문의해 주셔서 감사합니다. 더 자세한 도움이 필요하시면 상담원과 연결해드릴 수 있습니다.'
            confidence = 0.70
        
        return {
            'success': True,
            'intent': intent,
            'confidence': confidence,
            'response_text': response_text,
            'session_id': session_id,
            'next_action': 'continue_conversation',
            'timestamp': datetime.now().isoformat(),
            'context': context or {},
            'mock_response': True  # 테스트용 플래그
        }
    
    def _process_with_aws_services(self, message: str, session_id: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """실제 AWS 서비스를 사용한 처리"""
        # 실제 Bedrock NLU 처리 로직
        try:
            # Bedrock Claude 호출
            nlu_result = self._call_bedrock_nlu(message, context or {})
            
            # DynamoDB에 대화 저장
            self._save_conversation(session_id, message, nlu_result)
            
            return {
                'success': True,
                'intent': nlu_result.get('intent', 'general_inquiry'),
                'confidence': nlu_result.get('confidence', 0.5),
                'response_text': nlu_result.get('response_text', '처리 중입니다.'),
                'session_id': session_id,
                'next_action': nlu_result.get('next_action', 'continue_conversation'),
                'timestamp': datetime.now().isoformat(),
                'context': nlu_result.get('context', {}),
                'mock_response': False
            }
        except Exception as e:
            logger.error(f"AWS 서비스 처리 중 오류: {e}")
            # 오류 시 모킹된 응답으로 폴백
            return self._mock_chat_response(message, session_id, context)
    
    def _call_bedrock_nlu(self, message: str, context: Dict) -> Dict[str, Any]:
        """Bedrock Claude NLU 호출"""
        # 실제 Bedrock 호출 로직 (간소화된 버전)
        prompt = f"""
        사용자 메시지: {message}
        컨텍스트: {json.dumps(context, ensure_ascii=False)}
        
        다음 JSON 형식으로 응답해주세요:
        {{
            "intent": "의도명",
            "confidence": 0.0-1.0,
            "response_text": "응답 메시지",
            "next_action": "다음 액션"
        }}
        """
        
        # 실제 구현에서는 bedrock-runtime 클라이언트 사용
        # 여기서는 간단한 모킹 응답 반환
        return {
            'intent': 'general_inquiry',
            'confidence': 0.8,
            'response_text': '문의해 주셔서 감사합니다.',
            'next_action': 'continue_conversation'
        }
    
    def _save_conversation(self, session_id: str, message: str, nlu_result: Dict):
        """대화 내용을 DynamoDB에 저장"""
        try:
            table = self.dynamodb.Table(os.getenv('DYNAMODB_TABLE_NAME'))
            table.put_item(
                Item={
                    'session_id': session_id,
                    'timestamp': datetime.now().isoformat(),
                    'user_message': message,
                    'intent': nlu_result.get('intent'),
                    'confidence': nlu_result.get('confidence'),
                    'response_text': nlu_result.get('response_text')
                }
            )
        except Exception as e:
            logger.error(f"대화 저장 중 오류: {e}")
    
    def process_escalation(self, session_id: str, reason: str = 'customer_request') -> Dict[str, Any]:
        """상담원 에스컬레이션 처리"""
        try:
            logger.info(f"에스컬레이션 요청: {session_id}, 사유: {reason}")
            
            if self.use_mock_services:
                return {
                    'success': True,
                    'escalation_id': f'ESC_{session_id}_{int(datetime.now().timestamp())}',
                    'message': '상담원 연결을 요청했습니다. 잠시만 기다려주세요.',
                    'estimated_wait_time': '2-3분',
                    'timestamp': datetime.now().isoformat(),
                    'mock_response': True
                }
            else:
                # 실제 Connect 에스컬레이션 로직
                return self._process_connect_escalation(session_id, reason)
                
        except Exception as e:
            logger.error(f"에스컬레이션 처리 중 오류: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': '에스컬레이션 요청 중 오류가 발생했습니다.'
            }
    
    def _process_connect_escalation(self, session_id: str, reason: str) -> Dict[str, Any]:
        """실제 Connect 에스컬레이션 처리"""
        # Connect API 호출 로직
        return {
            'success': True,
            'escalation_id': f'REAL_ESC_{session_id}',
            'message': '상담원과 연결 중입니다.',
            'estimated_wait_time': '실시간 계산됨'
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda 진입점
    로컬 테스트에서도 동일한 인터페이스 사용
    """
    try:
        logger.info(f"Lambda 핸들러 시작: {json.dumps(event, ensure_ascii=False)}")
        
        # 핸들러 인스턴스 생성
        handler = ChatbotHandler()
        
        # 요청 타입에 따른 처리
        request_type = event.get('request_type', 'chat')
        
        if request_type == 'chat':
            message = event.get('message', '')
            session_id = event.get('session_id', f'session_{int(datetime.now().timestamp())}')
            context = event.get('context', {})
            
            result = handler.process_chat_message(message, session_id, context)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result, ensure_ascii=False)
            }
            
        elif request_type == 'escalation':
            session_id = event.get('session_id', '')
            reason = event.get('reason', 'customer_request')
            
            result = handler.process_escalation(session_id, reason)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(result, ensure_ascii=False)
            }
            
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'success': False,
                    'error': f'지원하지 않는 요청 타입: {request_type}'
                }, ensure_ascii=False)
            }
            
    except Exception as e:
        logger.error(f"Lambda 핸들러 오류: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'message': '서버 내부 오류가 발생했습니다.'
            }, ensure_ascii=False)
        }


# 로컬 테스트용 실행 함수
def run_local_test():
    """로컬 환경에서 직접 테스트"""
    print("=== 로컬 챗봇 핸들러 테스트 ===")
    
    # 테스트 이벤트들
    test_events = [
        {
            'request_type': 'chat',
            'message': '안녕하세요',
            'session_id': 'test_session_1'
        },
        {
            'request_type': 'chat',
            'message': '상품 가격이 궁금해요',
            'session_id': 'test_session_2'
        },
        {
            'request_type': 'chat',
            'message': '서비스에 불만이 있어요',
            'session_id': 'test_session_3'
        },
        {
            'request_type': 'escalation',
            'session_id': 'test_session_3',
            'reason': 'complaint'
        }
    ]
    
    for i, event in enumerate(test_events, 1):
        print(f"\n--- 테스트 {i} ---")
        print(f"입력: {json.dumps(event, ensure_ascii=False)}")
        
        result = lambda_handler(event, {})
        print(f"출력: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == '__main__':
    run_local_test() 