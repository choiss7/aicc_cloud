"""
AWS Connect 콜센터용 FAQ 관리 모듈
"""
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError
import re
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class FAQItem:
    """FAQ 항목"""
    faq_id: str
    category: str
    question: str
    answer: str
    keywords: List[str]
    priority: int
    is_active: bool
    created_at: str
    updated_at: str
    view_count: int

@dataclass
class FAQSearchResult:
    """FAQ 검색 결과"""
    faq_items: List[FAQItem]
    total_count: int
    search_query: str
    confidence_score: float

class ChatbotFAQ:
    """AWS Connect 챗봇 FAQ 관리자"""
    
    def __init__(self, dynamodb_table_name: str = "chatbot_faq"):
        self.dynamodb = boto3.resource('dynamodb')
        self.faq_table = self.dynamodb.Table(dynamodb_table_name)
        self.analytics_table = self.dynamodb.Table(f"{dynamodb_table_name}_analytics")
        
        # 검색 설정
        self.min_similarity_score = 0.6
        self.max_results = 5
        
        # 내장 FAQ 데이터
        self._initialize_default_faqs()
    
    def search_faq(self, query: str, category: Optional[str] = None, 
                   max_results: Optional[int] = None) -> FAQSearchResult:
        """
        FAQ 검색
        
        Args:
            query: 검색 질의
            category: 카테고리 필터
            max_results: 최대 결과 수
            
        Returns:
            FAQSearchResult: 검색 결과
        """
        try:
            # 검색어 전처리
            processed_query = self._preprocess_query(query)
            
            # DynamoDB에서 FAQ 검색
            faq_items = self._search_in_dynamodb(processed_query, category)
            
            # 유사도 계산 및 정렬
            scored_items = self._calculate_similarity_scores(processed_query, faq_items)
            
            # 필터링 및 제한
            filtered_items = [
                item for item in scored_items 
                if item['similarity_score'] >= self.min_similarity_score
            ]
            
            result_limit = max_results or self.max_results
            top_items = filtered_items[:result_limit]
            
            # FAQ 조회 통계 업데이트
            self._update_search_analytics(query, len(top_items))
            
            # 결과 변환
            faq_results = []
            for item in top_items:
                faq_item = FAQItem(
                    faq_id=item['faq_id'],
                    category=item['category'],
                    question=item['question'],
                    answer=item['answer'],
                    keywords=item.get('keywords', []),
                    priority=item.get('priority', 0),
                    is_active=item.get('is_active', True),
                    created_at=item.get('created_at', ''),
                    updated_at=item.get('updated_at', ''),
                    view_count=item.get('view_count', 0)
                )
                faq_results.append(faq_item)
            
            confidence = self._calculate_overall_confidence(top_items)
            
            return FAQSearchResult(
                faq_items=faq_results,
                total_count=len(faq_results),
                search_query=query,
                confidence_score=confidence
            )
            
        except Exception as e:
            logger.error(f"FAQ 검색 오류: {str(e)}")
            return FAQSearchResult(
                faq_items=[],
                total_count=0,
                search_query=query,
                confidence_score=0.0
            )
    
    def get_faq_by_id(self, faq_id: str) -> Optional[FAQItem]:
        """FAQ ID로 특정 FAQ 조회"""
        try:
            response = self.faq_table.get_item(Key={'faq_id': faq_id})
            item = response.get('Item')
            
            if not item:
                return None
            
            # 조회수 증가
            self._increment_view_count(faq_id)
            
            return FAQItem(
                faq_id=item['faq_id'],
                category=item['category'],
                question=item['question'],
                answer=item['answer'],
                keywords=item.get('keywords', []),
                priority=item.get('priority', 0),
                is_active=item.get('is_active', True),
                created_at=item.get('created_at', ''),
                updated_at=item.get('updated_at', ''),
                view_count=item.get('view_count', 0)
            )
            
        except Exception as e:
            logger.error(f"FAQ 조회 오류: {str(e)}")
            return None
    
    def get_popular_faqs(self, category: Optional[str] = None, 
                        limit: int = 10) -> List[FAQItem]:
        """인기 FAQ 조회"""
        try:
            # 조회수 기준으로 정렬하여 가져오기
            scan_kwargs = {
                'FilterExpression': 'is_active = :active',
                'ExpressionAttributeValues': {':active': True}
            }
            
            if category:
                scan_kwargs['FilterExpression'] += ' AND category = :category'
                scan_kwargs['ExpressionAttributeValues'][':category'] = category
            
            response = self.faq_table.scan(**scan_kwargs)
            items = response.get('Items', [])
            
            # 조회수 기준 정렬
            sorted_items = sorted(items, key=lambda x: x.get('view_count', 0), reverse=True)
            
            # 상위 N개 반환
            popular_items = []
            for item in sorted_items[:limit]:
                faq_item = FAQItem(
                    faq_id=item['faq_id'],
                    category=item['category'],
                    question=item['question'],
                    answer=item['answer'],
                    keywords=item.get('keywords', []),
                    priority=item.get('priority', 0),
                    is_active=item.get('is_active', True),
                    created_at=item.get('created_at', ''),
                    updated_at=item.get('updated_at', ''),
                    view_count=item.get('view_count', 0)
                )
                popular_items.append(faq_item)
            
            return popular_items
            
        except Exception as e:
            logger.error(f"인기 FAQ 조회 오류: {str(e)}")
            return []
    
    def get_categories(self) -> List[str]:
        """FAQ 카테고리 목록 조회"""
        try:
            response = self.faq_table.scan(
                ProjectionExpression='category',
                FilterExpression='is_active = :active',
                ExpressionAttributeValues={':active': True}
            )
            
            categories = set()
            for item in response.get('Items', []):
                categories.add(item['category'])
            
            return sorted(list(categories))
            
        except Exception as e:
            logger.error(f"카테고리 조회 오류: {str(e)}")
            return []
    
    def add_faq(self, category: str, question: str, answer: str, 
                keywords: List[str], priority: int = 0) -> bool:
        """새 FAQ 추가"""
        try:
            faq_id = self._generate_faq_id()
            current_time = datetime.now().isoformat()
            
            item = {
                'faq_id': faq_id,
                'category': category,
                'question': question,
                'answer': answer,
                'keywords': keywords,
                'priority': priority,
                'is_active': True,
                'created_at': current_time,
                'updated_at': current_time,
                'view_count': 0
            }
            
            self.faq_table.put_item(Item=item)
            logger.info(f"새 FAQ 추가됨: {faq_id}")
            return True
            
        except Exception as e:
            logger.error(f"FAQ 추가 오류: {str(e)}")
            return False
    
    def update_faq(self, faq_id: str, **kwargs) -> bool:
        """FAQ 업데이트"""
        try:
            update_expression = "SET updated_at = :updated_at"
            expression_values = {':updated_at': datetime.now().isoformat()}
            
            for key, value in kwargs.items():
                if key in ['category', 'question', 'answer', 'keywords', 'priority', 'is_active']:
                    update_expression += f", {key} = :{key}"
                    expression_values[f':{key}'] = value
            
            self.faq_table.update_item(
                Key={'faq_id': faq_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            
            logger.info(f"FAQ 업데이트됨: {faq_id}")
            return True
            
        except Exception as e:
            logger.error(f"FAQ 업데이트 오류: {str(e)}")
            return False
    
    def delete_faq(self, faq_id: str) -> bool:
        """FAQ 삭제 (비활성화)"""
        try:
            self.faq_table.update_item(
                Key={'faq_id': faq_id},
                UpdateExpression="SET is_active = :inactive, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ':inactive': False,
                    ':updated_at': datetime.now().isoformat()
                }
            )
            
            logger.info(f"FAQ 비활성화됨: {faq_id}")
            return True
            
        except Exception as e:
            logger.error(f"FAQ 삭제 오류: {str(e)}")
            return False
    
    def get_faq_analytics(self, start_date: str, end_date: str) -> Dict:
        """FAQ 분석 데이터 조회"""
        try:
            response = self.analytics_table.scan(
                FilterExpression='search_date BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':start': start_date,
                    ':end': end_date
                }
            )
            
            analytics_data = {
                'total_searches': 0,
                'successful_searches': 0,
                'failed_searches': 0,
                'popular_queries': {},
                'category_distribution': {}
            }
            
            for item in response.get('Items', []):
                analytics_data['total_searches'] += item.get('search_count', 0)
                
                if item.get('result_count', 0) > 0:
                    analytics_data['successful_searches'] += item.get('search_count', 0)
                else:
                    analytics_data['failed_searches'] += item.get('search_count', 0)
            
            return analytics_data
            
        except Exception as e:
            logger.error(f"FAQ 분석 데이터 조회 오류: {str(e)}")
            return {}
    
    def _preprocess_query(self, query: str) -> str:
        """검색어 전처리"""
        # 소문자 변환
        processed = query.lower().strip()
        
        # 특수문자 제거
        processed = re.sub(r'[^\w\s가-힣]', ' ', processed)
        
        # 다중 공백 제거
        processed = re.sub(r'\s+', ' ', processed)
        
        return processed
    
    def _search_in_dynamodb(self, query: str, category: Optional[str]) -> List[Dict]:
        """DynamoDB에서 FAQ 검색"""
        try:
            scan_kwargs = {
                'FilterExpression': 'is_active = :active',
                'ExpressionAttributeValues': {':active': True}
            }
            
            if category:
                scan_kwargs['FilterExpression'] += ' AND category = :category'
                scan_kwargs['ExpressionAttributeValues'][':category'] = category
            
            response = self.faq_table.scan(**scan_kwargs)
            return response.get('Items', [])
            
        except Exception as e:
            logger.error(f"DynamoDB 검색 오류: {str(e)}")
            return []
    
    def _calculate_similarity_scores(self, query: str, faq_items: List[Dict]) -> List[Dict]:
        """유사도 점수 계산"""
        scored_items = []
        query_words = set(query.split())
        
        for item in faq_items:
            # 질문 텍스트와의 유사도
            question_words = set(self._preprocess_query(item['question']).split())
            question_similarity = self._calculate_jaccard_similarity(query_words, question_words)
            
            # 키워드와의 유사도
            keyword_similarity = 0.0
            if item.get('keywords'):
                keyword_words = set()
                for keyword in item['keywords']:
                    keyword_words.update(self._preprocess_query(keyword).split())
                keyword_similarity = self._calculate_jaccard_similarity(query_words, keyword_words)
            
            # 최종 유사도 (질문 70%, 키워드 30%)
            final_score = (question_similarity * 0.7) + (keyword_similarity * 0.3)
            
            # 우선순위 보정
            priority_boost = item.get('priority', 0) * 0.1
            final_score = min(1.0, final_score + priority_boost)
            
            item['similarity_score'] = final_score
            scored_items.append(item)
        
        # 점수 기준 정렬
        return sorted(scored_items, key=lambda x: x['similarity_score'], reverse=True)
    
    def _calculate_jaccard_similarity(self, set1: set, set2: set) -> float:
        """자카드 유사도 계산"""
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_overall_confidence(self, scored_items: List[Dict]) -> float:
        """전체 신뢰도 계산"""
        if not scored_items:
            return 0.0
        
        # 최고 점수 항목의 점수를 기준으로 신뢰도 계산
        max_score = scored_items[0]['similarity_score']
        
        # 여러 항목이 비슷한 점수를 가질 때 신뢰도 증가
        similar_count = sum(1 for item in scored_items[:3] if item['similarity_score'] >= max_score * 0.8)
        
        confidence = max_score * (1 + (similar_count - 1) * 0.1)
        return min(1.0, confidence)
    
    def _increment_view_count(self, faq_id: str):
        """조회수 증가"""
        try:
            self.faq_table.update_item(
                Key={'faq_id': faq_id},
                UpdateExpression="ADD view_count :inc",
                ExpressionAttributeValues={':inc': 1}
            )
        except Exception as e:
            logger.error(f"조회수 증가 오류: {str(e)}")
    
    def _update_search_analytics(self, query: str, result_count: int):
        """검색 분석 데이터 업데이트"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            search_key = f"{today}_{query}"
            
            self.analytics_table.update_item(
                Key={'search_key': search_key},
                UpdateExpression="ADD search_count :inc SET search_date = :date, query = :query, result_count = :count",
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':date': today,
                    ':query': query,
                    ':count': result_count
                }
            )
        except Exception as e:
            logger.error(f"검색 분석 업데이트 오류: {str(e)}")
    
    def _generate_faq_id(self) -> str:
        """FAQ ID 생성"""
        import uuid
        return f"faq_{uuid.uuid4().hex[:8]}"
    
    def _initialize_default_faqs(self):
        """기본 FAQ 데이터 초기화"""
        default_faqs = [
            {
                'category': '일반',
                'question': '영업시간이 어떻게 되나요?',
                'answer': '평일 오전 9시부터 오후 6시까지 운영합니다. 주말 및 공휴일은 휴무입니다.',
                'keywords': ['영업시간', '운영시간', '몇시', '언제', '시간']
            },
            {
                'category': '일반',
                'question': '고객센터 전화번호는 무엇인가요?',
                'answer': '고객센터 전화번호는 1588-0000입니다. 평일 오전 9시부터 오후 6시까지 상담 가능합니다.',
                'keywords': ['전화번호', '연락처', '고객센터', '상담']
            },
            {
                'category': '주문/배송',
                'question': '주문 취소는 어떻게 하나요?',
                'answer': '주문 취소는 배송 준비 전까지 가능합니다. 마이페이지에서 직접 취소하거나 고객센터로 연락주세요.',
                'keywords': ['주문취소', '취소', '주문', '배송취소']
            },
            {
                'category': '주문/배송',
                'question': '배송기간은 얼마나 걸리나요?',
                'answer': '일반 배송은 주문 후 2-3일, 당일배송은 오후 2시 이전 주문 시 당일 배송됩니다.',
                'keywords': ['배송기간', '배송일', '언제', '며칠', '당일배송']
            },
            {
                'category': '결제',
                'question': '어떤 결제 방법을 지원하나요?',
                'answer': '신용카드, 체크카드, 계좌이체, 무통장입금, 카카오페이, 네이버페이를 지원합니다.',
                'keywords': ['결제방법', '결제', '카드', '계좌이체', '카카오페이', '네이버페이']
            },
            {
                'category': '결제',
                'question': '결제 영수증은 어디서 확인하나요?',
                'answer': '마이페이지 > 주문내역에서 영수증을 확인하고 출력할 수 있습니다.',
                'keywords': ['영수증', '결제확인', '주문내역', '마이페이지']
            },
            {
                'category': '회원',
                'question': '회원가입은 필수인가요?',
                'answer': '비회원으로도 주문 가능하지만, 회원가입 시 다양한 혜택과 편리한 서비스를 이용할 수 있습니다.',
                'keywords': ['회원가입', '비회원', '필수', '가입']
            },
            {
                'category': '회원',
                'question': '비밀번호를 잊어버렸어요.',
                'answer': '로그인 페이지에서 "비밀번호 찾기"를 클릭하여 이메일로 재설정 링크를 받으실 수 있습니다.',
                'keywords': ['비밀번호', '비밀번호찾기', '잊어버림', '재설정']
            },
            {
                'category': '반품/교환',
                'question': '반품은 언제까지 가능한가요?',
                'answer': '상품 수령 후 7일 이내에 반품 신청이 가능합니다. 상품의 상태가 양호해야 합니다.',
                'keywords': ['반품', '반품기간', '언제까지', '7일', '교환']
            },
            {
                'category': '반품/교환',
                'question': '교환 비용은 누가 부담하나요?',
                'answer': '제품 불량의 경우 무료 교환, 단순 변심의 경우 배송비를 고객이 부담합니다.',
                'keywords': ['교환비용', '배송비', '교환', '불량', '변심']
            }
        ]
        
        # 기본 FAQ가 없을 경우에만 추가
        try:
            response = self.faq_table.scan(Limit=1)
            if not response.get('Items'):
                for faq_data in default_faqs:
                    self.add_faq(
                        category=faq_data['category'],
                        question=faq_data['question'],
                        answer=faq_data['answer'],
                        keywords=faq_data['keywords'],
                        priority=1
                    )
                logger.info("기본 FAQ 데이터 초기화 완료")
        except Exception as e:
            logger.error(f"기본 FAQ 초기화 오류: {str(e)}") 