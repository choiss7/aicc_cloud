"""
AWS Connect Contact Flow와 연동되는 Lambda 함수
"""
import json
import logging
import os
from typing import Dict, Any, Optional
import boto3
from datetime import datetime

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS 클라이언트 초기화
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# 환경 변수
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'aicc-conversations')
CHATBOT_RESPONSES_BUCKET = os.environ.get('CHATBOT_RESPONSES_BUCKET', 'aicc-chatbot-responses')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Connect Contact Flow에서 호출되는 메인 핸들러
    
    Args:
        event: Connect에서 전달되는 이벤트 데이터
        context: Lambda 컨텍스트
        
    Returns:
        Dict: Connect로 반환할 응답 데이터
    """
    try:
        logger.info(f"Lambda 이벤트 수신: {json.dumps(event, ensure_ascii=False)}")
        
        # Connect 이벤트에서 필요한 정보 추출
        contact_data = event.get('Details', {}).get('ContactData', {})
        parameters = event.get('Details', {}).get('Parameters', {})
        
        # 고객 정보 추출
        customer_endpoint = contact_data.get('CustomerEndpoint', {})
        customer_phone = customer_endpoint.get('Address', '')
        contact_id = contact_data.get('ContactId', '')
        
        # 사용자 입력 (음성 인식 결과 또는 DTMF)
        user_input = parameters.get('userInput', '')
        intent_name = parameters.get('intentName', '')
        session_attributes = parameters.get('sessionAttributes', {})
        
        # 요청 타입 확인
        request_type = parameters.get('requestType', 'chat')
        
        logger.info(f"처리 요청 - Contact ID: {contact_id}, 입력: {user_input}, 의도: {intent_name}")
        
        # 요청 타입별 처리
        if request_type == 'chat':
            response = handle_chat_request(contact_id, user_input, session_attributes, customer_phone)
        elif request_type == 'voice':
            response = handle_voice_request(contact_id, user_input, session_attributes, customer_phone)
        elif request_type == 'escalation':
            response = handle_escalation_request(contact_id, session_attributes, customer_phone)
        elif request_type == 'business_hours':
            response = handle_business_hours_check()
        elif request_type == 'queue_status':
            response = handle_queue_status_check()
        else:
            response = handle_default_request(contact_id, user_input, session_attributes)
        
        logger.info(f"응답 생성 완료: {json.dumps(response, ensure_ascii=False)}")
        return response
        
    except Exception as e:
        logger.error(f"Lambda 처리 중 오류 발생: {str(e)}", exc_info=True)
        return create_error_response(str(e))

def handle_chat_request(contact_id: str, user_input: str, 
                       session_attributes: Dict, customer_phone: str) -> Dict[str, Any]:
    """채팅 요청 처리"""
    try:
        # NLU 모듈 임포트 (여기서 임포트하여 콜드 스타트 최적화)
        from src.chatbot_nlu_bedrock import BedrockChatbotNLU
        
        # NLU 처리
        nlu = BedrockChatbotNLU()
        nlu_result = nlu.process_message(user_input, contact_id, session_attributes)
        
        # 대화 로그 저장
        save_conversation_log(contact_id, user_input, nlu_result, customer_phone)
        
        # Connect 응답 형식으로 변환
        response = {
            'statusCode': 200,
            'body': {
                'intent': nlu_result.intent_result.intent,
                'confidence': nlu_result.intent_result.confidence,
                'responseText': nlu_result.response_text,
                'nextAction': nlu_result.next_action,
                'sessionAttributes': nlu_result.session_attributes,
                'entities': nlu_result.intent_result.entities
            }
        }
        
        # 에스컬레이션 필요 시 추가 정보
        if nlu_result.next_action == 'escalate':
            response['body']['escalationReason'] = nlu_result.intent_result.reasoning
            response['body']['escalationPriority'] = get_escalation_priority(nlu_result.intent_result.intent)
        
        return response
        
    except Exception as e:
        logger.error(f"채팅 요청 처리 오류: {str(e)}")
        return create_error_response(f"채팅 처리 오류: {str(e)}")

def handle_voice_request(contact_id: str, user_input: str, 
                        session_attributes: Dict, customer_phone: str) -> Dict[str, Any]:
    """음성 요청 처리"""
    try:
        # 음성 인식 결과 처리
        if not user_input:
            return {
                'statusCode': 200,
                'body': {
                    'responseText': '죄송합니다. 음성을 인식하지 못했습니다. 다시 말씀해 주시겠어요?',
                    'nextAction': 'retry',
                    'sessionAttributes': session_attributes
                }
            }
        
        # 채팅과 동일한 NLU 처리
        return handle_chat_request(contact_id, user_input, session_attributes, customer_phone)
        
    except Exception as e:
        logger.error(f"음성 요청 처리 오류: {str(e)}")
        return create_error_response(f"음성 처리 오류: {str(e)}")

def handle_escalation_request(contact_id: str, session_attributes: Dict, 
                            customer_phone: str) -> Dict[str, Any]:
    """에스컬레이션 요청 처리"""
    try:
        # 상담원 대기열 상태 확인
        queue_info = get_agent_queue_status()
        
        # 고객 정보 조회
        customer_info = get_customer_info(customer_phone)
        
        # 에스컬레이션 로그 저장
        escalation_data = {
            'contact_id': contact_id,
            'customer_phone': customer_phone,
            'customer_info': customer_info,
            'session_attributes': session_attributes,
            'escalation_time': datetime.now().isoformat(),
            'queue_info': queue_info
        }
        
        save_escalation_log(escalation_data)
        
        # 대기 시간에 따른 응답 생성
        if queue_info['estimated_wait_time'] > 300:  # 5분 이상
            response_text = f"현재 상담 대기 고객이 많아 약 {queue_info['estimated_wait_time']//60}분 정도 기다리셔야 합니다. 계속 기다리시겠습니까?"
            next_action = 'confirm_wait'
        else:
            response_text = "상담원에게 연결해드리겠습니다. 잠시만 기다려 주세요."
            next_action = 'transfer_to_agent'
        
        return {
            'statusCode': 200,
            'body': {
                'responseText': response_text,
                'nextAction': next_action,
                'queueInfo': queue_info,
                'customerInfo': customer_info,
                'sessionAttributes': session_attributes
            }
        }
        
    except Exception as e:
        logger.error(f"에스컬레이션 처리 오류: {str(e)}")
        return create_error_response(f"에스컬레이션 오류: {str(e)}")

def handle_business_hours_check() -> Dict[str, Any]:
    """영업시간 확인"""
    try:
        current_time = datetime.now()
        current_hour = current_time.hour
        current_weekday = current_time.weekday()  # 0=월요일, 6=일요일
        
        # 영업시간 설정 (평일 9-18시, 주말 10-17시)
        if current_weekday < 5:  # 평일
            is_business_hours = 9 <= current_hour < 18
            business_hours_text = "평일 오전 9시부터 오후 6시까지"
        else:  # 주말
            is_business_hours = 10 <= current_hour < 17
            business_hours_text = "주말 오전 10시부터 오후 5시까지"
        
        if is_business_hours:
            response_text = "현재 영업시간입니다. 상담원 연결이 가능합니다."
            next_action = "transfer_to_agent"
        else:
            response_text = f"현재 영업시간이 아닙니다. 영업시간은 {business_hours_text}입니다. 챗봇으로 도움을 드리거나 콜백 예약을 하시겠습니까?"
            next_action = "offer_alternatives"
        
        return {
            'statusCode': 200,
            'body': {
                'isBusinessHours': is_business_hours,
                'responseText': response_text,
                'nextAction': next_action,
                'businessHours': business_hours_text
            }
        }
        
    except Exception as e:
        logger.error(f"영업시간 확인 오류: {str(e)}")
        return create_error_response(f"영업시간 확인 오류: {str(e)}")

def handle_queue_status_check() -> Dict[str, Any]:
    """대기열 상태 확인"""
    try:
        queue_info = get_agent_queue_status()
        
        if queue_info['available_agents'] > 0:
            response_text = "상담원이 대기 중입니다. 바로 연결해드리겠습니다."
            next_action = "transfer_to_agent"
        else:
            wait_time_minutes = queue_info['estimated_wait_time'] // 60
            response_text = f"현재 모든 상담원이 통화 중입니다. 예상 대기시간은 약 {wait_time_minutes}분입니다."
            next_action = "queue_wait"
        
        return {
            'statusCode': 200,
            'body': {
                'queueInfo': queue_info,
                'responseText': response_text,
                'nextAction': next_action
            }
        }
        
    except Exception as e:
        logger.error(f"대기열 상태 확인 오류: {str(e)}")
        return create_error_response(f"대기열 상태 확인 오류: {str(e)}")

def handle_default_request(contact_id: str, user_input: str, 
                         session_attributes: Dict) -> Dict[str, Any]:
    """기본 요청 처리"""
    return {
        'statusCode': 200,
        'body': {
            'responseText': '안녕하세요! AICC 고객센터입니다. 무엇을 도와드릴까요?',
            'nextAction': 'continue',
            'sessionAttributes': session_attributes
        }
    }

def save_conversation_log(contact_id: str, user_input: str, 
                         nlu_result, customer_phone: str):
    """대화 로그 DynamoDB 저장"""
    try:
        table = dynamodb.Table(CONVERSATIONS_TABLE)
        
        log_item = {
            'contact_id': contact_id,
            'timestamp': datetime.now().isoformat(),
            'customer_phone': customer_phone,
            'user_input': user_input,
            'intent': nlu_result.intent_result.intent,
            'confidence': str(nlu_result.intent_result.confidence),
            'bot_response': nlu_result.response_text,
            'next_action': nlu_result.next_action,
            'entities': nlu_result.intent_result.entities,
            'session_attributes': nlu_result.session_attributes,
            'claude_reasoning': nlu_result.claude_reasoning
        }
        
        table.put_item(Item=log_item)
        logger.info(f"대화 로그 저장 완료: {contact_id}")
        
    except Exception as e:
        logger.error(f"대화 로그 저장 오류: {str(e)}")

def save_escalation_log(escalation_data: Dict):
    """에스컬레이션 로그 저장"""
    try:
        # S3에 에스컬레이션 로그 저장
        log_key = f"escalations/{escalation_data['contact_id']}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        s3_client.put_object(
            Bucket=CHATBOT_RESPONSES_BUCKET,
            Key=log_key,
            Body=json.dumps(escalation_data, ensure_ascii=False),
            ContentType='application/json'
        )
        
        logger.info(f"에스컬레이션 로그 저장 완료: {log_key}")
        
    except Exception as e:
        logger.error(f"에스컬레이션 로그 저장 오류: {str(e)}")

def get_customer_info(customer_phone: str) -> Dict[str, Any]:
    """고객 정보 조회"""
    try:
        # 실제 구현에서는 CRM 시스템이나 고객 DB에서 조회
        # 여기서는 예시 데이터 반환
        return {
            'phone': customer_phone,
            'customer_id': f"CUST_{customer_phone[-4:]}",
            'tier': 'STANDARD',
            'last_contact_date': '2024-01-15',
            'preferred_language': 'ko'
        }
        
    except Exception as e:
        logger.error(f"고객 정보 조회 오류: {str(e)}")
        return {'phone': customer_phone}

def get_agent_queue_status() -> Dict[str, Any]:
    """상담원 대기열 상태 조회"""
    try:
        # 실제 구현에서는 Connect API를 통해 실시간 대기열 정보 조회
        # 여기서는 예시 데이터 반환
        return {
            'available_agents': 2,
            'busy_agents': 8,
            'queue_length': 5,
            'estimated_wait_time': 180,  # 초 단위
            'average_handle_time': 300
        }
        
    except Exception as e:
        logger.error(f"대기열 상태 조회 오류: {str(e)}")
        return {
            'available_agents': 0,
            'busy_agents': 0,
            'queue_length': 0,
            'estimated_wait_time': 600
        }

def get_escalation_priority(intent: str) -> str:
    """의도에 따른 에스컬레이션 우선순위 결정"""
    priority_map = {
        'complaint': 'HIGH',
        'payment_inquiry': 'HIGH',
        'cancel_request': 'MEDIUM',
        'technical_support': 'MEDIUM',
        'product_inquiry': 'LOW',
        'general_inquiry': 'LOW'
    }
    
    return priority_map.get(intent, 'MEDIUM')

def create_error_response(error_message: str) -> Dict[str, Any]:
    """오류 응답 생성"""
    return {
        'statusCode': 500,
        'body': {
            'error': True,
            'message': error_message,
            'responseText': '죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주시거나 상담원에게 연결을 요청해 주세요.',
            'nextAction': 'error',
            'sessionAttributes': {}
        }
    }

# Contact Flow에서 사용할 수 있는 유틸리티 함수들
def format_phone_number(phone: str) -> str:
    """전화번호 포맷팅"""
    # 한국 전화번호 포맷팅 (010-1234-5678)
    if phone.startswith('+82'):
        phone = '0' + phone[3:]
    
    phone = phone.replace('-', '').replace(' ', '')
    
    if len(phone) == 11 and phone.startswith('010'):
        return f"{phone[:3]}-{phone[3:7]}-{phone[7:]}"
    elif len(phone) == 10:
        return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    
    return phone

def validate_business_hours() -> bool:
    """영업시간 검증"""
    current_time = datetime.now()
    current_hour = current_time.hour
    current_weekday = current_time.weekday()
    
    if current_weekday < 5:  # 평일
        return 9 <= current_hour < 18
    else:  # 주말
        return 10 <= current_hour < 17 