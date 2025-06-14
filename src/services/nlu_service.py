"""
AWS Connect 콜센터용 자연어 이해(NLU) 서비스
"""
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import re

from ..chatbot_nlu import ChatbotNLU, NLUResponse, IntentResult

logger = logging.getLogger(__name__)

class NLUService:
    """자연어 이해 서비스"""
    
    def __init__(self, lex_bot_name: str, dynamodb_table_name: str = "nlu_analytics"):
        self.nlu_engine = ChatbotNLU(lex_bot_name)
        
        # DynamoDB for analytics and training data
        self.dynamodb = boto3.resource('dynamodb')
        self.analytics_table = self.dynamodb.Table(dynamodb_table_name)
        self.training_table = self.dynamodb.Table(f"{dynamodb_table_name}_training")
        
        # Comprehend for sentiment analysis
        self.comprehend = boto3.client('comprehend')
        
        # CloudWatch for metrics
        self.cloudwatch = boto3.client('cloudwatch')
        
        # 감정 분석 설정
        self.sentiment_threshold = {
            'positive': 0.7,
            'neutral': 0.5,
            'negative': 0.3
        }
        
        # 언어 감지 설정
        self.supported_languages = ['ko', 'en', 'ja', 'zh']
        self.default_language = 'ko'
    
    def process_user_input(self, user_input: str, session_id: str,
                          session_attributes: Optional[Dict] = None,
                          include_sentiment: bool = True) -> Dict[str, Any]:
        """
        사용자 입력을 종합적으로 처리
        
        Args:
            user_input: 사용자 입력 텍스트
            session_id: 세션 ID
            session_attributes: 세션 속성
            include_sentiment: 감정 분석 포함 여부
            
        Returns:
            Dict: 처리 결과
        """
        try:
            # 입력 전처리
            preprocessed_input = self._preprocess_input(user_input)
            
            # 언어 감지
            detected_language = self._detect_language(preprocessed_input)
            
            # 기본 NLU 처리
            nlu_response = self.nlu_engine.process_message(
                preprocessed_input, session_id, session_attributes
            )
            
            # 감정 분석
            sentiment_result = None
            if include_sentiment:
                sentiment_result = self._analyze_sentiment(preprocessed_input, detected_language)
            
            # 엔티티 추출 보강
            enhanced_entities = self._enhance_entity_extraction(
                preprocessed_input, nlu_response.intent_result.entities
            )
            
            # 컨텍스트 분석
            context_analysis = self._analyze_context(
                session_attributes or {}, nlu_response.intent_result
            )
            
            # 응답 생성
            enhanced_response = self._enhance_response(
                nlu_response, sentiment_result, context_analysis
            )
            
            # 분석 결과 저장
            self._save_analysis_result(
                session_id, user_input, nlu_response, sentiment_result,
                detected_language, enhanced_entities
            )
            
            # 메트릭 전송
            self._send_metrics(nlu_response.intent_result, sentiment_result)
            
            return {
                'success': True,
                'intent': nlu_response.intent_result.intent,
                'confidence': nlu_response.intent_result.confidence,
                'entities': enhanced_entities,
                'sentiment': sentiment_result,
                'language': detected_language,
                'response_text': enhanced_response,
                'next_action': nlu_response.next_action,
                'session_attributes': nlu_response.session_attributes,
                'context_analysis': context_analysis
            }
            
        except Exception as e:
            logger.error(f"NLU 서비스 처리 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'response_text': '죄송합니다. 요청을 처리할 수 없습니다.',
                'next_action': 'error'
            }
    
    def analyze_conversation_intent(self, conversation_history: List[Dict]) -> Dict[str, Any]:
        """
        대화 전체의 의도 분석
        
        Args:
            conversation_history: 대화 이력
            
        Returns:
            Dict: 대화 의도 분석 결과
        """
        try:
            if not conversation_history:
                return {'primary_intent': 'unknown', 'confidence': 0.0}
            
            # 사용자 메시지만 추출
            user_messages = [
                msg['content'] for msg in conversation_history 
                if msg.get('source') == 'user'
            ]
            
            if not user_messages:
                return {'primary_intent': 'unknown', 'confidence': 0.0}
            
            # 각 메시지별 의도 분석
            intent_scores = {}
            total_confidence = 0.0
            
            for message in user_messages:
                # 임시 세션으로 의도 분석
                temp_session = f"analysis_{datetime.now().timestamp()}"
                result = self.nlu_engine.process_message(message, temp_session)
                
                intent = result.intent_result.intent
                confidence = result.intent_result.confidence
                
                if intent in intent_scores:
                    intent_scores[intent] += confidence
                else:
                    intent_scores[intent] = confidence
                
                total_confidence += confidence
            
            # 가장 높은 점수의 의도 선택
            if intent_scores:
                primary_intent = max(intent_scores, key=intent_scores.get)
                primary_confidence = intent_scores[primary_intent] / len(user_messages)
                
                return {
                    'primary_intent': primary_intent,
                    'confidence': primary_confidence,
                    'intent_distribution': intent_scores,
                    'message_count': len(user_messages)
                }
            
            return {'primary_intent': 'unknown', 'confidence': 0.0}
            
        except Exception as e:
            logger.error(f"대화 의도 분석 오류: {str(e)}")
            return {'primary_intent': 'error', 'confidence': 0.0}
    
    def get_intent_suggestions(self, partial_input: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        부분 입력에 대한 의도 제안
        
        Args:
            partial_input: 부분 입력 텍스트
            limit: 제안 개수 제한
            
        Returns:
            List[Dict]: 의도 제안 목록
        """
        try:
            # 지원되는 의도 목록 가져오기
            supported_intents = self.nlu_engine.get_supported_intents()
            
            # 부분 입력과 유사한 의도 찾기
            suggestions = []
            
            for intent in supported_intents:
                # 의도명과 유사도 계산
                similarity = self._calculate_string_similarity(partial_input, intent)
                
                if similarity > 0.3:  # 임계값 이상만 포함
                    suggestions.append({
                        'intent': intent,
                        'similarity': similarity,
                        'description': self._get_intent_description(intent)
                    })
            
            # 유사도 기준으로 정렬
            suggestions.sort(key=lambda x: x['similarity'], reverse=True)
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"의도 제안 오류: {str(e)}")
            return []
    
    def train_with_feedback(self, user_input: str, expected_intent: str,
                           actual_intent: str, session_id: str) -> bool:
        """
        피드백을 통한 학습 데이터 수집
        
        Args:
            user_input: 사용자 입력
            expected_intent: 기대된 의도
            actual_intent: 실제 분석된 의도
            session_id: 세션 ID
            
        Returns:
            bool: 성공 여부
        """
        try:
            training_data = {
                'training_id': f"train_{datetime.now().timestamp()}",
                'user_input': user_input,
                'expected_intent': expected_intent,
                'actual_intent': actual_intent,
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'processed': False
            }
            
            self.training_table.put_item(Item=training_data)
            
            logger.info(f"학습 데이터 저장: {expected_intent} vs {actual_intent}")
            return True
            
        except Exception as e:
            logger.error(f"학습 데이터 저장 오류: {str(e)}")
            return False
    
    def get_nlu_analytics(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        NLU 분석 통계 조회
        
        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
            
        Returns:
            Dict: 분석 통계
        """
        try:
            response = self.analytics_table.scan(
                FilterExpression='created_at BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':start': start_date,
                    ':end': end_date
                }
            )
            
            analytics_data = response.get('Items', [])
            
            # 통계 계산
            total_requests = len(analytics_data)
            intent_distribution = {}
            confidence_scores = []
            sentiment_distribution = {}
            language_distribution = {}
            
            for item in analytics_data:
                # 의도 분포
                intent = item.get('intent', 'unknown')
                intent_distribution[intent] = intent_distribution.get(intent, 0) + 1
                
                # 신뢰도 점수
                confidence = item.get('confidence', 0.0)
                confidence_scores.append(confidence)
                
                # 감정 분포
                sentiment = item.get('sentiment', {}).get('sentiment', 'neutral')
                sentiment_distribution[sentiment] = sentiment_distribution.get(sentiment, 0) + 1
                
                # 언어 분포
                language = item.get('language', 'unknown')
                language_distribution[language] = language_distribution.get(language, 0) + 1
            
            # 평균 신뢰도 계산
            average_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            return {
                'total_requests': total_requests,
                'average_confidence': average_confidence,
                'intent_distribution': intent_distribution,
                'sentiment_distribution': sentiment_distribution,
                'language_distribution': language_distribution,
                'low_confidence_rate': len([c for c in confidence_scores if c < 0.7]) / total_requests * 100 if total_requests > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"NLU 분석 통계 조회 오류: {str(e)}")
            return {}
    
    def _preprocess_input(self, user_input: str) -> str:
        """입력 전처리"""
        # 공백 정리
        processed = re.sub(r'\s+', ' ', user_input.strip())
        
        # 이모티콘 처리 (선택적)
        processed = re.sub(r'[😀-🙏💀-🙈👀-🔗]', '', processed)
        
        # 연속된 특수문자 정리
        processed = re.sub(r'[!?]{2,}', '!', processed)
        
        return processed
    
    def _detect_language(self, text: str) -> str:
        """언어 감지"""
        try:
            if len(text.strip()) < 3:
                return self.default_language
            
            response = self.comprehend.detect_dominant_language(Text=text)
            languages = response.get('Languages', [])
            
            if languages:
                detected_lang = languages[0]['LanguageCode']
                confidence = languages[0]['Score']
                
                if confidence > 0.8 and detected_lang in self.supported_languages:
                    return detected_lang
            
            return self.default_language
            
        except Exception as e:
            logger.error(f"언어 감지 오류: {str(e)}")
            return self.default_language
    
    def _analyze_sentiment(self, text: str, language: str) -> Optional[Dict[str, Any]]:
        """감정 분석"""
        try:
            if language not in ['ko', 'en']:  # Comprehend 지원 언어 확인
                return None
            
            response = self.comprehend.detect_sentiment(
                Text=text,
                LanguageCode=language
            )
            
            sentiment = response.get('Sentiment', 'NEUTRAL')
            scores = response.get('SentimentScore', {})
            
            return {
                'sentiment': sentiment.lower(),
                'confidence': scores.get(sentiment.capitalize(), 0.0),
                'scores': {
                    'positive': scores.get('Positive', 0.0),
                    'negative': scores.get('Negative', 0.0),
                    'neutral': scores.get('Neutral', 0.0),
                    'mixed': scores.get('Mixed', 0.0)
                }
            }
            
        except Exception as e:
            logger.error(f"감정 분석 오류: {str(e)}")
            return None
    
    def _enhance_entity_extraction(self, text: str, basic_entities: Dict) -> Dict[str, Any]:
        """엔티티 추출 보강"""
        enhanced_entities = basic_entities.copy()
        
        # 전화번호 추출
        phone_pattern = r'01[0-9]-[0-9]{4}-[0-9]{4}'
        phone_matches = re.findall(phone_pattern, text)
        if phone_matches:
            enhanced_entities['phone_number'] = phone_matches[0]
        
        # 이메일 추출
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_matches = re.findall(email_pattern, text)
        if email_matches:
            enhanced_entities['email'] = email_matches[0]
        
        # 날짜 패턴 추출 (간단한 예시)
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',
            r'(\d{2})/(\d{2})/(\d{4})',
            r'(\d{1,2})월\s*(\d{1,2})일'
        ]
        
        for pattern in date_patterns:
            date_matches = re.findall(pattern, text)
            if date_matches:
                enhanced_entities['date'] = date_matches[0]
                break
        
        # 금액 추출
        amount_pattern = r'(\d{1,3}(?:,\d{3})*)\s*원'
        amount_matches = re.findall(amount_pattern, text)
        if amount_matches:
            enhanced_entities['amount'] = amount_matches[0]
        
        return enhanced_entities
    
    def _analyze_context(self, session_attributes: Dict, intent_result: IntentResult) -> Dict[str, Any]:
        """컨텍스트 분석"""
        context_analysis = {
            'is_repeat_request': False,
            'escalation_indicators': [],
            'urgency_level': 'normal',
            'customer_journey_stage': 'inquiry'
        }
        
        # 반복 요청 감지
        last_intent = session_attributes.get('last_intent')
        if last_intent and last_intent == intent_result.intent:
            context_analysis['is_repeat_request'] = True
        
        # 에스컬레이션 지표 감지
        escalation_keywords = ['상담원', '사람', '매니저', '책임자', '화나', '짜증']
        for keyword in escalation_keywords:
            if keyword in intent_result.entities.values():
                context_analysis['escalation_indicators'].append(keyword)
        
        # 긴급도 분석
        urgency_keywords = ['긴급', '당장', '즉시', '빨리']
        for keyword in urgency_keywords:
            if any(keyword in str(value) for value in intent_result.entities.values()):
                context_analysis['urgency_level'] = 'high'
                break
        
        # 고객 여정 단계 추정
        journey_mapping = {
            'greeting': 'initial',
            'product_inquiry': 'consideration',
            'reservation': 'decision',
            'complaint': 'post_purchase',
            'technical_support': 'post_purchase'
        }
        
        context_analysis['customer_journey_stage'] = journey_mapping.get(
            intent_result.intent, 'inquiry'
        )
        
        return context_analysis
    
    def _enhance_response(self, nlu_response: NLUResponse, 
                         sentiment_result: Optional[Dict],
                         context_analysis: Dict) -> str:
        """응답 개선"""
        base_response = nlu_response.response_text
        
        # 감정에 따른 응답 조정
        if sentiment_result:
            sentiment = sentiment_result.get('sentiment', 'neutral')
            
            if sentiment == 'negative':
                # 부정적 감정에 대한 공감 표현 추가
                base_response = f"불편을 끼쳐드려 죄송합니다. {base_response}"
            elif sentiment == 'positive':
                # 긍정적 감정에 대한 감사 표현 추가
                base_response = f"문의해 주셔서 감사합니다. {base_response}"
        
        # 반복 요청에 대한 추가 안내
        if context_analysis.get('is_repeat_request'):
            base_response += "\n\n추가 도움이 필요하시면 상담원에게 연결해드릴 수도 있습니다."
        
        # 긴급도에 따른 우선 처리 안내
        if context_analysis.get('urgency_level') == 'high':
            base_response = f"긴급한 요청으로 접수되었습니다. {base_response}"
        
        return base_response
    
    def _save_analysis_result(self, session_id: str, user_input: str,
                            nlu_response: NLUResponse, sentiment_result: Optional[Dict],
                            language: str, entities: Dict):
        """분석 결과 저장"""
        try:
            analysis_data = {
                'analysis_id': f"nlu_{datetime.now().timestamp()}",
                'session_id': session_id,
                'user_input': user_input,
                'intent': nlu_response.intent_result.intent,
                'confidence': nlu_response.intent_result.confidence,
                'entities': entities,
                'sentiment': sentiment_result,
                'language': language,
                'created_at': datetime.now().isoformat()
            }
            
            self.analytics_table.put_item(Item=analysis_data)
            
        except Exception as e:
            logger.error(f"분석 결과 저장 오류: {str(e)}")
    
    def _send_metrics(self, intent_result: IntentResult, sentiment_result: Optional[Dict]):
        """메트릭 전송"""
        try:
            # 의도 분석 메트릭
            self.cloudwatch.put_metric_data(
                Namespace='AICC/NLU',
                MetricData=[
                    {
                        'MetricName': 'IntentAnalysis',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {'Name': 'Intent', 'Value': intent_result.intent},
                            {'Name': 'Confidence', 'Value': str(int(intent_result.confidence * 10) / 10)}
                        ]
                    }
                ]
            )
            
            # 감정 분석 메트릭
            if sentiment_result:
                self.cloudwatch.put_metric_data(
                    Namespace='AICC/NLU',
                    MetricData=[
                        {
                            'MetricName': 'SentimentAnalysis',
                            'Value': 1,
                            'Unit': 'Count',
                            'Dimensions': [
                                {'Name': 'Sentiment', 'Value': sentiment_result['sentiment']}
                            ]
                        }
                    ]
                )
            
        except Exception as e:
            logger.error(f"메트릭 전송 오류: {str(e)}")
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """문자열 유사도 계산 (간단한 Jaccard 유사도)"""
        set1 = set(str1.lower())
        set2 = set(str2.lower())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _get_intent_description(self, intent: str) -> str:
        """의도 설명 반환"""
        descriptions = {
            'greeting': '인사 및 대화 시작',
            'product_inquiry': '상품 문의 및 정보 요청',
            'complaint': '불만 및 컴플레인',
            'reservation': '예약 및 스케줄링',
            'cancel_request': '취소 요청',
            'technical_support': '기술 지원 요청',
            'payment_inquiry': '결제 관련 문의'
        }
        
        return descriptions.get(intent, '기타 문의') 