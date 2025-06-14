"""
AWS Bedrock Claude 기반 자연어 이해(NLU) 모듈
"""
import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import re

# .env 파일 로드
load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class IntentResult:
    """의도 분석 결과"""
    intent: str
    confidence: float
    entities: Dict[str, str]
    reasoning: str
    suggested_actions: List[str]

@dataclass
class NLUResponse:
    """NLU 응답 구조"""
    intent_result: IntentResult
    response_text: str
    next_action: str
    session_attributes: Dict[str, str]
    claude_reasoning: str

class BedrockChatbotNLU:
    """AWS Bedrock Claude 기반 챗봇 자연어 이해 처리기"""
    
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
        
        # AWS 클라이언트 초기화
        session = boto3.Session(
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')  # Bedrock은 us-east-1 사용
        )
        self.bedrock_client = session.client('bedrock-runtime')
        
        # 의도 정의 및 설명
        self.intent_definitions = {
            'greeting': {
                'description': '인사, 안녕하세요, 처음 대화 시작',
                'examples': ['안녕하세요', '안녕', '반갑습니다', '처음 뵙겠습니다'],
                'confidence_threshold': 0.8
            },
            'product_inquiry': {
                'description': '상품 문의, 제품 정보, 가격, 스펙 문의',
                'examples': ['상품이 궁금해요', '가격이 얼마인가요', '스펙을 알고 싶어요'],
                'confidence_threshold': 0.85
            },
            'complaint': {
                'description': '불만, 항의, 문제 제기, 서비스 불만족',
                'examples': ['불만이 있어요', '서비스가 별로예요', '문제가 있어요'],
                'confidence_threshold': 0.9
            },
            'reservation': {
                'description': '예약, 예약 변경, 예약 취소',
                'examples': ['예약하고 싶어요', '예약을 변경하고 싶어요', '예약을 취소해주세요'],
                'confidence_threshold': 0.85
            },
            'cancel_request': {
                'description': '취소 요청, 환불 요청, 주문 취소',
                'examples': ['취소하고 싶어요', '환불해주세요', '주문을 취소해주세요'],
                'confidence_threshold': 0.9
            },
            'technical_support': {
                'description': '기술 지원, 사용법 문의, 오류 해결',
                'examples': ['사용법을 모르겠어요', '오류가 발생해요', '기술 지원이 필요해요'],
                'confidence_threshold': 0.85
            },
            'payment_inquiry': {
                'description': '결제 문의, 결제 방법, 결제 오류',
                'examples': ['결제가 안돼요', '결제 방법이 궁금해요', '결제 오류가 발생했어요'],
                'confidence_threshold': 0.9
            },
            'general_inquiry': {
                'description': '일반 문의, 기타 질문',
                'examples': ['문의가 있어요', '질문이 있어요', '도움이 필요해요'],
                'confidence_threshold': 0.7
            }
        }
        
        # Claude 프롬프트 템플릿
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Claude용 시스템 프롬프트 구성"""
        intent_descriptions = []
        for intent, info in self.intent_definitions.items():
            examples = ', '.join(info['examples'][:3])
            intent_descriptions.append(f"- {intent}: {info['description']} (예: {examples})")
        
        return f"""
당신은 한국어 고객센터 AI 어시스턴트입니다. 고객의 메시지를 분석하여 의도를 파악하고 적절한 응답을 제공해야 합니다.

## 지원하는 의도 (Intent):
{chr(10).join(intent_descriptions)}

## 분석 규칙:
1. 고객의 메시지에서 핵심 의도를 파악하세요
2. 신뢰도(confidence)를 0.0~1.0 사이로 평가하세요
3. 메시지에서 중요한 엔티티(이름, 날짜, 상품명 등)를 추출하세요
4. 고객에게 도움이 되는 응답을 생성하세요
5. 다음 단계 액션을 제안하세요

## 응답 형식:
반드시 다음 JSON 형식으로 응답하세요:
{{
    "intent": "의도명",
    "confidence": 0.0~1.0,
    "entities": {{"엔티티명": "값"}},
    "reasoning": "분석 근거",
    "response_text": "고객 응답 메시지",
    "next_action": "다음 액션",
    "suggested_actions": ["제안 액션1", "제안 액션2"]
}}

## 응답 가이드라인:
- 친근하고 정중한 톤으로 응답하세요
- 고객의 감정을 고려하여 공감적으로 응답하세요
- 불만이나 문제 상황에서는 사과와 해결 의지를 표현하세요
- 복잡한 문제는 상담원 연결을 제안하세요
"""
    
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
            # Claude를 통한 의도 분석
            claude_response = self._call_claude(user_input, session_attributes or {})
            
            # 응답 파싱
            parsed_response = self._parse_claude_response(claude_response)
            
            # 의도 분석 결과 생성
            intent_result = IntentResult(
                intent=parsed_response.get('intent', 'general_inquiry'),
                confidence=parsed_response.get('confidence', 0.5),
                entities=parsed_response.get('entities', {}),
                reasoning=parsed_response.get('reasoning', ''),
                suggested_actions=parsed_response.get('suggested_actions', [])
            )
            
            # 신뢰도 검증 및 응답 조정
            response_text, next_action = self._validate_and_adjust_response(
                intent_result, parsed_response
            )
            
            # 세션 속성 업데이트
            updated_session_attributes = self._update_session_attributes(
                intent_result, session_attributes or {}
            )
            
            return NLUResponse(
                intent_result=intent_result,
                response_text=response_text,
                next_action=next_action,
                session_attributes=updated_session_attributes,
                claude_reasoning=parsed_response.get('reasoning', '')
            )
            
        except Exception as e:
            logger.error(f"Bedrock NLU 처리 중 오류 발생: {str(e)}")
            return self._create_error_response()
    
    def _call_claude(self, text: str, session_attributes: Dict) -> str:
        """AWS Bedrock Claude 호출"""
        try:
            # 대화 컨텍스트 구성
            context = self._build_context(session_attributes)
            
            # 사용자 프롬프트 구성
            user_prompt = f"""
## 대화 컨텍스트:
{context}

## 고객 메시지:
"{text}"

위 고객 메시지를 분석하여 JSON 형식으로 응답해주세요.
"""
            
            # Claude 요청 구성
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "temperature": 0.1,
                "system": self.system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            }
            
            # Bedrock 호출
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            # 응답 파싱
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except ClientError as e:
            logger.error(f"Bedrock 호출 오류: {e}")
            raise
        except Exception as e:
            logger.error(f"Claude 호출 중 예상치 못한 오류: {e}")
            raise
    
    def _build_context(self, session_attributes: Dict) -> str:
        """대화 컨텍스트 구성"""
        context_parts = []
        
        if session_attributes.get('user_id'):
            context_parts.append(f"고객 ID: {session_attributes['user_id']}")
        
        if session_attributes.get('last_intent'):
            context_parts.append(f"이전 의도: {session_attributes['last_intent']}")
        
        if session_attributes.get('conversation_stage'):
            context_parts.append(f"대화 단계: {session_attributes['conversation_stage']}")
        
        if session_attributes.get('customer_mood'):
            context_parts.append(f"고객 감정: {session_attributes['customer_mood']}")
        
        return '\n'.join(context_parts) if context_parts else "새로운 대화"
    
    def _parse_claude_response(self, claude_response: str) -> Dict[str, Any]:
        """Claude 응답 파싱"""
        try:
            # JSON 부분 추출
            json_match = re.search(r'\{.*\}', claude_response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                # JSON이 없는 경우 기본값 반환
                return {
                    'intent': 'general_inquiry',
                    'confidence': 0.5,
                    'entities': {},
                    'reasoning': 'JSON 파싱 실패',
                    'response_text': '죄송합니다. 다시 말씀해 주시겠어요?',
                    'next_action': 'retry',
                    'suggested_actions': ['다시 시도', '상담원 연결']
                }
        except json.JSONDecodeError as e:
            logger.error(f"Claude 응답 JSON 파싱 오류: {e}")
            return {
                'intent': 'general_inquiry',
                'confidence': 0.3,
                'entities': {},
                'reasoning': f'JSON 파싱 오류: {str(e)}',
                'response_text': '죄송합니다. 다시 말씀해 주시겠어요?',
                'next_action': 'retry',
                'suggested_actions': ['다시 시도', '상담원 연결']
            }
    
    def _validate_and_adjust_response(self, intent_result: IntentResult, 
                                    parsed_response: Dict) -> Tuple[str, str]:
        """신뢰도 검증 및 응답 조정"""
        intent = intent_result.intent
        confidence = intent_result.confidence
        
        # 의도별 신뢰도 임계값 확인
        threshold = self.intent_definitions.get(intent, {}).get('confidence_threshold', 0.7)
        
        if confidence < threshold:
            # 신뢰도가 낮은 경우 명확화 요청
            return self._get_clarification_response(intent), "clarify"
        
        # 의도별 특별 처리
        if intent == 'complaint' and confidence > 0.8:
            # 불만 사항은 즉시 상담원 연결
            return (
                "불편을 끼쳐드려 죄송합니다. 전문 상담원에게 연결해드리겠습니다.",
                "escalate"
            )
        elif intent in ['payment_inquiry', 'cancel_request'] and confidence > 0.85:
            # 결제/취소 관련은 보안상 상담원 연결
            return (
                "보안을 위해 전문 상담원에게 연결해드리겠습니다.",
                "escalate"
            )
        
        # Claude가 생성한 응답 사용
        response_text = parsed_response.get('response_text', '도움을 드리겠습니다.')
        next_action = parsed_response.get('next_action', 'continue')
        
        return response_text, next_action
    
    def _get_clarification_response(self, intent: str) -> str:
        """명확화 응답 생성"""
        clarification_map = {
            'product_inquiry': "어떤 상품에 대해 문의하시는 건가요? 좀 더 구체적으로 말씀해 주세요.",
            'complaint': "어떤 부분에서 불편을 겪으셨는지 자세히 말씀해 주시겠어요?",
            'technical_support': "어떤 기술적인 문제가 발생했는지 구체적으로 설명해 주시겠어요?",
            'reservation': "어떤 예약에 대해 문의하시는 건가요?",
            'cancel_request': "어떤 것을 취소하고 싶으신가요?",
            'payment_inquiry': "결제와 관련해서 어떤 문제가 있으신가요?"
        }
        
        return clarification_map.get(intent, "좀 더 자세히 말씀해 주시겠어요?")
    
    def _update_session_attributes(self, intent_result: IntentResult, 
                                 current_attributes: Dict) -> Dict:
        """세션 속성 업데이트"""
        updated_attributes = current_attributes.copy()
        
        # 의도 정보 저장
        updated_attributes['last_intent'] = intent_result.intent
        updated_attributes['last_confidence'] = str(intent_result.confidence)
        updated_attributes['last_reasoning'] = intent_result.reasoning
        
        # 엔티티 정보 저장
        for key, value in intent_result.entities.items():
            updated_attributes[f'entity_{key}'] = value
        
        # 고객 감정 추론 (간단한 규칙 기반)
        if intent_result.intent == 'complaint':
            updated_attributes['customer_mood'] = 'frustrated'
        elif intent_result.intent == 'greeting':
            updated_attributes['customer_mood'] = 'neutral'
        elif intent_result.confidence < 0.5:
            updated_attributes['customer_mood'] = 'confused'
        
        # 대화 단계 업데이트
        if intent_result.intent == 'greeting':
            updated_attributes['conversation_stage'] = 'greeting'
        elif intent_result.intent in ['product_inquiry', 'technical_support']:
            updated_attributes['conversation_stage'] = 'inquiry'
        elif intent_result.intent in ['complaint', 'cancel_request']:
            updated_attributes['conversation_stage'] = 'problem_solving'
        
        return updated_attributes
    
    def _create_error_response(self) -> NLUResponse:
        """오류 응답 생성"""
        return NLUResponse(
            intent_result=IntentResult(
                intent="error",
                confidence=0.0,
                entities={},
                reasoning="시스템 오류 발생",
                suggested_actions=["다시 시도", "상담원 연결"]
            ),
            response_text="죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            next_action="error",
            session_attributes={},
            claude_reasoning="시스템 오류로 인한 기본 응답"
        )
    
    def get_supported_intents(self) -> List[str]:
        """지원되는 의도 목록 반환"""
        return list(self.intent_definitions.keys())
    
    def update_intent_definition(self, intent: str, definition: Dict):
        """의도 정의 업데이트"""
        if intent in self.intent_definitions:
            self.intent_definitions[intent].update(definition)
            # 시스템 프롬프트 재구성
            self.system_prompt = self._build_system_prompt()
            logger.info(f"의도 정의 업데이트: {intent}")
    
    def add_custom_intent(self, intent: str, definition: Dict):
        """사용자 정의 의도 추가"""
        required_fields = ['description', 'examples', 'confidence_threshold']
        if all(field in definition for field in required_fields):
            self.intent_definitions[intent] = definition
            # 시스템 프롬프트 재구성
            self.system_prompt = self._build_system_prompt()
            logger.info(f"사용자 정의 의도 추가: {intent}")
        else:
            raise ValueError(f"의도 정의에 필수 필드가 누락됨: {required_fields}")
    
    def analyze_conversation_sentiment(self, conversation_history: List[str]) -> Dict[str, Any]:
        """대화 전체의 감정 분석"""
        try:
            conversation_text = '\n'.join(conversation_history)
            
            sentiment_prompt = f"""
다음 고객센터 대화를 분석하여 고객의 전반적인 감정과 만족도를 평가해주세요:

{conversation_text}

다음 JSON 형식으로 응답해주세요:
{{
    "overall_sentiment": "positive/neutral/negative",
    "satisfaction_score": 0.0-1.0,
    "key_emotions": ["emotion1", "emotion2"],
    "escalation_risk": 0.0-1.0,
    "summary": "분석 요약"
}}
"""
            
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "user",
                        "content": sentiment_prompt
                    }
                ]
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            claude_response = response_body['content'][0]['text']
            
            return self._parse_claude_response(claude_response)
            
        except Exception as e:
            logger.error(f"감정 분석 오류: {e}")
            return {
                "overall_sentiment": "neutral",
                "satisfaction_score": 0.5,
                "key_emotions": ["unknown"],
                "escalation_risk": 0.5,
                "summary": "분석 실패"
            }


# 기존 NLU와의 호환성을 위한 래퍼 클래스
class ChatbotNLU(BedrockChatbotNLU):
    """기존 코드와의 호환성을 위한 래퍼 클래스"""
    
    def __init__(self, lex_bot_name: Optional[str] = None, lex_bot_alias: Optional[str] = None):
        # Bedrock 기반으로 초기화 (Lex 파라미터는 무시)
        super().__init__()
        logger.info("Bedrock Claude 기반 NLU로 초기화됨 (Lex 파라미터 무시)")


if __name__ == "__main__":
    # 테스트 코드
    nlu = BedrockChatbotNLU()
    
    test_messages = [
        "안녕하세요",
        "스마트폰 가격이 궁금해요",
        "서비스가 너무 별로예요",
        "예약을 취소하고 싶어요",
        "결제가 안되는데 도와주세요"
    ]
    
    for message in test_messages:
        print(f"\n입력: {message}")
        result = nlu.process_message(message, "test_session")
        print(f"의도: {result.intent_result.intent}")
        print(f"신뢰도: {result.intent_result.confidence}")
        print(f"응답: {result.response_text}")
        print(f"다음 액션: {result.next_action}") 