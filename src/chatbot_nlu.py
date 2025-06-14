"""
AWS Connect 콜센터용 자연어 이해(NLU) 모듈
"""
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

@dataclass
class IntentResult:
    """의도 분석 결과"""
    intent: str
    confidence: float
    entities: Dict[str, str]
    slots: Dict[str, str]

@dataclass
class NLUResponse:
    """NLU 응답 구조"""
    intent_result: IntentResult
    response_text: str
    next_action: str
    session_attributes: Dict[str, str]

class ChatbotNLU:
    """AWS Connect 챗봇 자연어 이해 처리기"""
    
    def __init__(self, lex_bot_name: str, lex_bot_alias: str = "DRAFT"):
        self.lex_bot_name = lex_bot_name
        self.lex_bot_alias = lex_bot_alias
        self.lex_client = boto3.client('lexv2-runtime')
        
        # 의도별 신뢰도 임계값
        self.confidence_threshold = {
            'greeting': 0.7,
            'product_inquiry': 0.8,
            'complaint': 0.75,
            'reservation': 0.85,
            'cancel_request': 0.9,
            'technical_support': 0.8,
            'payment_inquiry': 0.85,
            'default': 0.7
        }
    
    def process_message(self, user_input: str, session_id: str, 
                       session_attributes: Optional[Dict] = None) -> NLUResponse:
        """
        사용자 입력을 처리하고 의도를 분석합니다.
        
        Args:
            user_input: 사용자 입력 텍스트
            session_id: 세션 ID
            session_attributes: 세션 속성
            
        Returns:
            NLUResponse: 처리 결과
        """
        try:
            # AWS Lex를 통한 의도 분석
            lex_response = self._call_lex(user_input, session_id, session_attributes or {})
            
            # 의도 분석 결과 추출
            intent_result = self._extract_intent(lex_response)
            
            # 응답 생성
            response_text, next_action = self._generate_response(intent_result)
            
            # 세션 속성 업데이트
            updated_session_attributes = self._update_session_attributes(
                intent_result, session_attributes or {}
            )
            
            return NLUResponse(
                intent_result=intent_result,
                response_text=response_text,
                next_action=next_action,
                session_attributes=updated_session_attributes
            )
            
        except Exception as e:
            logger.error(f"NLU 처리 중 오류 발생: {str(e)}")
            return self._create_error_response()
    
    def _call_lex(self, text: str, session_id: str, 
                  session_attributes: Dict) -> Dict:
        """AWS Lex 호출"""
        try:
            response = self.lex_client.recognize_text(
                botId=self.lex_bot_name,
                botAliasId=self.lex_bot_alias,
                localeId='ko_KR',
                sessionId=session_id,
                text=text,
                sessionState={
                    'sessionAttributes': session_attributes
                }
            )
            return response
            
        except ClientError as e:
            logger.error(f"Lex 호출 오류: {e}")
            raise
    
    def _extract_intent(self, lex_response: Dict) -> IntentResult:
        """Lex 응답에서 의도 정보 추출"""
        session_state = lex_response.get('sessionState', {})
        intent = session_state.get('intent', {})
        
        intent_name = intent.get('name', 'unknown')
        confidence = intent.get('nluIntentConfidence', {}).get('score', 0.0)
        
        # 슬롯 정보 추출
        slots = intent.get('slots', {})
        entities = {}
        
        for slot_name, slot_data in slots.items():
            if slot_data and slot_data.get('value'):
                entities[slot_name] = slot_data['value']['interpretedValue']
        
        return IntentResult(
            intent=intent_name,
            confidence=confidence,
            entities=entities,
            slots=slots
        )
    
    def _generate_response(self, intent_result: IntentResult) -> Tuple[str, str]:
        """의도에 따른 응답 생성"""
        intent = intent_result.intent
        confidence = intent_result.confidence
        
        # 신뢰도 확인
        threshold = self.confidence_threshold.get(intent, 
                                                 self.confidence_threshold['default'])
        
        if confidence < threshold:
            return self._get_clarification_response(intent), "clarify"
        
        # 의도별 응답 생성
        response_map = {
            'greeting': ("안녕하세요! 무엇을 도와드릴까요?", "continue"),
            'product_inquiry': ("상품에 대해 문의해주셔서 감사합니다. 어떤 상품이 궁금하신가요?", "product_flow"),
            'complaint': ("불편을 끼쳐드려 죄송합니다. 상담원에게 연결해드리겠습니다.", "escalate"),
            'reservation': ("예약 도움을 드리겠습니다.", "reservation_flow"),
            'cancel_request': ("취소 요청을 접수하겠습니다.", "cancel_flow"),
            'technical_support': ("기술 지원이 필요하시군요. 상담원에게 연결하겠습니다.", "escalate"),
            'payment_inquiry': ("결제 관련 문의입니다. 보안을 위해 상담원에게 연결하겠습니다.", "escalate")
        }
        
        return response_map.get(intent, ("죄송합니다. 다시 말씀해 주시겠어요?", "retry"))
    
    def _get_clarification_response(self, intent: str) -> str:
        """명확화 응답 생성"""
        clarification_map = {
            'product_inquiry': "상품 문의에 대해 좀 더 구체적으로 말씀해 주시겠어요?",
            'complaint': "불편사항에 대해 자세히 설명해 주시겠어요?",
            'technical_support': "기술적인 문제가 어떤 것인지 좀 더 설명해 주시겠어요?"
        }
        
        return clarification_map.get(intent, "죄송합니다. 좀 더 자세히 말씀해 주시겠어요?")
    
    def _update_session_attributes(self, intent_result: IntentResult, 
                                 current_attributes: Dict) -> Dict:
        """세션 속성 업데이트"""
        updated_attributes = current_attributes.copy()
        
        # 의도 정보 저장
        updated_attributes['last_intent'] = intent_result.intent
        updated_attributes['last_confidence'] = str(intent_result.confidence)
        
        # 엔티티 정보 저장
        for key, value in intent_result.entities.items():
            updated_attributes[f'entity_{key}'] = value
        
        return updated_attributes
    
    def _create_error_response(self) -> NLUResponse:
        """오류 응답 생성"""
        return NLUResponse(
            intent_result=IntentResult(
                intent="error",
                confidence=0.0,
                entities={},
                slots={}
            ),
            response_text="죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            next_action="error",
            session_attributes={}
        )
    
    def get_supported_intents(self) -> List[str]:
        """지원되는 의도 목록 반환"""
        return [
            'greeting',
            'product_inquiry', 
            'complaint',
            'reservation',
            'cancel_request',
            'technical_support',
            'payment_inquiry'
        ]
    
    def update_confidence_threshold(self, intent: str, threshold: float):
        """의도별 신뢰도 임계값 업데이트"""
        if 0.0 <= threshold <= 1.0:
            self.confidence_threshold[intent] = threshold
            logger.info(f"{intent} 의도의 신뢰도 임계값을 {threshold}로 업데이트")
        else:
            raise ValueError("신뢰도 임계값은 0.0과 1.0 사이여야 합니다.") 