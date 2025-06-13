"""
AI 챗봇 NLU (Natural Language Understanding) 모듈
AWS Comprehend와 Lex를 활용한 자연어 이해 처리
"""

import boto3
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatbotNLU:
    """
    AI 챗봇 자연어 이해 처리 클래스
    """
    
    def __init__(self, region_name: str = 'ap-northeast-2'):
        """
        NLU 클래스 초기화
        
        Args:
            region_name: AWS 리전명
        """
        self.region_name = region_name
        self.comprehend = boto3.client('comprehend', region_name=region_name)
        self.lex = boto3.client('lexv2-runtime', region_name=region_name)
        
        # 의도 분류 매핑
        self.intent_mapping = {
            'greeting': ['안녕', '안녕하세요', '반갑습니다', '처음뵙겠습니다'],
            'inquiry': ['문의', '질문', '궁금', '알고싶어요', '어떻게'],
            'complaint': ['불만', '항의', '문제', '오류', '잘못'],
            'request': ['요청', '신청', '부탁', '도와주세요', '처리'],
            'goodbye': ['안녕히', '감사합니다', '고맙습니다', '끝', '종료']
        }
        
        # 엔티티 패턴
        self.entity_patterns = {
            'phone': r'(\d{2,3}-\d{3,4}-\d{4})',
            'email': r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            'date': r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            'time': r'(\d{1,2}:\d{2})',
            'number': r'(\d+)'
        }
    
    def analyze_sentiment(self, text: str) -> Dict:
        """
        텍스트 감정 분석
        
        Args:
            text: 분석할 텍스트
            
        Returns:
            감정 분석 결과
        """
        try:
            response = self.comprehend.detect_sentiment(
                Text=text,
                LanguageCode='ko'
            )
            
            return {
                'sentiment': response['Sentiment'],
                'confidence': response['SentimentScore'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"감정 분석 오류: {str(e)}")
            return {
                'sentiment': 'NEUTRAL',
                'confidence': {'Neutral': 0.5},
                'error': str(e)
            }
    
    def extract_entities(self, text: str) -> Dict:
        """
        엔티티 추출
        
        Args:
            text: 분석할 텍스트
            
        Returns:
            추출된 엔티티 정보
        """
        entities = {}
        
        # 정규식 패턴으로 엔티티 추출
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                entities[entity_type] = matches
        
        # AWS Comprehend로 추가 엔티티 추출
        try:
            response = self.comprehend.detect_entities(
                Text=text,
                LanguageCode='ko'
            )
            
            aws_entities = []
            for entity in response['Entities']:
                aws_entities.append({
                    'text': entity['Text'],
                    'type': entity['Type'],
                    'confidence': entity['Score']
                })
            
            entities['aws_entities'] = aws_entities
            
        except Exception as e:
            logger.error(f"엔티티 추출 오류: {str(e)}")
            entities['error'] = str(e)
        
        return entities
    
    def classify_intent(self, text: str) -> Dict:
        """
        의도 분류
        
        Args:
            text: 분석할 텍스트
            
        Returns:
            분류된 의도 정보
        """
        text_lower = text.lower()
        intent_scores = {}
        
        # 키워드 기반 의도 분류
        for intent, keywords in self.intent_mapping.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            
            if score > 0:
                intent_scores[intent] = score / len(keywords)
        
        # 가장 높은 점수의 의도 선택
        if intent_scores:
            best_intent = max(intent_scores, key=intent_scores.get)
            confidence = intent_scores[best_intent]
        else:
            best_intent = 'unknown'
            confidence = 0.0
        
        return {
            'intent': best_intent,
            'confidence': confidence,
            'all_scores': intent_scores,
            'timestamp': datetime.now().isoformat()
        }
    
    def process_lex_bot(self, text: str, session_id: str, bot_id: str, bot_alias_id: str) -> Dict:
        """
        Amazon Lex 봇 처리
        
        Args:
            text: 사용자 입력 텍스트
            session_id: 세션 ID
            bot_id: Lex 봇 ID
            bot_alias_id: Lex 봇 별칭 ID
            
        Returns:
            Lex 봇 응답
        """
        try:
            response = self.lex.recognize_text(
                botId=bot_id,
                botAliasId=bot_alias_id,
                localeId='ko_KR',
                sessionId=session_id,
                text=text
            )
            
            return {
                'intent': response.get('sessionState', {}).get('intent', {}),
                'slots': response.get('sessionState', {}).get('intent', {}).get('slots', {}),
                'messages': response.get('messages', []),
                'session_state': response.get('sessionState', {}),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Lex 봇 처리 오류: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def comprehensive_analysis(self, text: str, session_id: str = None, 
                             bot_id: str = None, bot_alias_id: str = None) -> Dict:
        """
        종합적인 NLU 분석
        
        Args:
            text: 분석할 텍스트
            session_id: 세션 ID (Lex 사용시)
            bot_id: Lex 봇 ID (Lex 사용시)
            bot_alias_id: Lex 봇 별칭 ID (Lex 사용시)
            
        Returns:
            종합 분석 결과
        """
        analysis_result = {
            'input_text': text,
            'timestamp': datetime.now().isoformat(),
            'sentiment': self.analyze_sentiment(text),
            'entities': self.extract_entities(text),
            'intent': self.classify_intent(text)
        }
        
        # Lex 봇 분석 추가 (선택적)
        if all([session_id, bot_id, bot_alias_id]):
            analysis_result['lex_analysis'] = self.process_lex_bot(
                text, session_id, bot_id, bot_alias_id
            )
        
        return analysis_result
    
    def get_response_template(self, intent: str, sentiment: str) -> str:
        """
        의도와 감정에 따른 응답 템플릿 반환
        
        Args:
            intent: 분류된 의도
            sentiment: 감정 분석 결과
            
        Returns:
            응답 템플릿
        """
        templates = {
            'greeting': {
                'POSITIVE': "안녕하세요! 무엇을 도와드릴까요?",
                'NEUTRAL': "안녕하세요. 어떤 도움이 필요하신가요?",
                'NEGATIVE': "안녕하세요. 불편하신 점이 있으시면 언제든 말씀해 주세요."
            },
            'inquiry': {
                'POSITIVE': "궁금한 점이 있으시군요. 자세히 알려드리겠습니다.",
                'NEUTRAL': "문의사항에 대해 안내해 드리겠습니다.",
                'NEGATIVE': "문제가 있으신 것 같네요. 빠르게 해결해 드리겠습니다."
            },
            'complaint': {
                'POSITIVE': "불편을 끼쳐드려 죄송합니다. 개선하도록 하겠습니다.",
                'NEUTRAL': "말씀해 주신 내용을 검토하여 개선하겠습니다.",
                'NEGATIVE': "정말 죄송합니다. 즉시 담당자에게 연결해 드리겠습니다."
            },
            'request': {
                'POSITIVE': "요청사항을 처리해 드리겠습니다.",
                'NEUTRAL': "어떤 도움이 필요하신지 구체적으로 말씀해 주세요.",
                'NEGATIVE': "문제 해결을 위해 최선을 다하겠습니다."
            },
            'goodbye': {
                'POSITIVE': "감사합니다. 좋은 하루 되세요!",
                'NEUTRAL': "도움이 되었기를 바랍니다. 감사합니다.",
                'NEGATIVE': "더 도움이 필요하시면 언제든 연락주세요."
            }
        }
        
        return templates.get(intent, {}).get(sentiment, 
            "죄송합니다. 다시 한 번 말씀해 주시겠어요?")

# 사용 예시
if __name__ == "__main__":
    nlu = ChatbotNLU()
    
    # 테스트 텍스트
    test_texts = [
        "안녕하세요, 계좌 잔액을 확인하고 싶습니다.",
        "카드가 분실되어서 정말 급합니다. 어떻게 해야 하나요?",
        "대출 신청은 어떻게 하나요?",
        "감사합니다. 도움이 많이 되었어요."
    ]
    
    for text in test_texts:
        print(f"\n입력: {text}")
        result = nlu.comprehensive_analysis(text)
        print(f"의도: {result['intent']['intent']}")
        print(f"감정: {result['sentiment']['sentiment']}")
        print(f"엔티티: {result['entities']}")
        
        # 응답 템플릿 생성
        response = nlu.get_response_template(
            result['intent']['intent'],
            result['sentiment']['sentiment']
        )
        print(f"응답: {response}") 