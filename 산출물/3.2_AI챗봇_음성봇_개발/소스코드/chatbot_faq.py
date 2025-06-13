"""
AI 챗봇 FAQ 관리 모듈
자주 묻는 질문 관리 및 검색 기능
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re
from difflib import SequenceMatcher
import boto3
from elasticsearch import Elasticsearch

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FAQManager:
    """
    FAQ 관리 클래스
    """
    
    def __init__(self, elasticsearch_host: str = None, aws_region: str = 'ap-northeast-2'):
        """
        FAQ 관리자 초기화
        
        Args:
            elasticsearch_host: Elasticsearch 호스트
            aws_region: AWS 리전
        """
        self.aws_region = aws_region
        self.faq_data = self._load_faq_data()
        
        # Elasticsearch 클라이언트 (선택적)
        self.es_client = None
        if elasticsearch_host:
            try:
                self.es_client = Elasticsearch([elasticsearch_host])
                self._create_faq_index()
            except Exception as e:
                logger.warning(f"Elasticsearch 연결 실패: {str(e)}")
        
        # AWS OpenSearch 클라이언트 (선택적)
        self.opensearch_client = None
        try:
            self.opensearch_client = boto3.client('opensearch', region_name=aws_region)
        except Exception as e:
            logger.warning(f"AWS OpenSearch 클라이언트 초기화 실패: {str(e)}")
    
    def _load_faq_data(self) -> Dict:
        """
        FAQ 데이터 로드
        
        Returns:
            FAQ 데이터 딕셔너리
        """
        return {
            "banking": {
                "category": "은행 업무",
                "faqs": [
                    {
                        "id": "bank_001",
                        "question": "계좌 잔액은 어떻게 확인하나요?",
                        "answer": "계좌 잔액은 다음과 같은 방법으로 확인할 수 있습니다:\n1. 인터넷뱅킹 또는 모바일뱅킹 앱\n2. ATM 기기\n3. 전화뱅킹(ARS)\n4. 영업점 방문\n\n가장 편리한 방법은 모바일뱅킹 앱을 이용하는 것입니다.",
                        "keywords": ["잔액", "확인", "계좌", "조회"],
                        "category": "계좌조회",
                        "priority": 1,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z"
                    },
                    {
                        "id": "bank_002",
                        "question": "계좌 이체는 어떻게 하나요?",
                        "answer": "계좌 이체 방법:\n1. 인터넷뱅킹/모바일뱅킹: 로그인 후 이체 메뉴 선택\n2. ATM: 이체 메뉴에서 받는 계좌번호와 금액 입력\n3. 영업점 방문: 이체 신청서 작성\n\n이체 한도와 수수료는 이체 방법에 따라 다릅니다.",
                        "keywords": ["이체", "송금", "계좌이체", "돈보내기"],
                        "category": "이체",
                        "priority": 1,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z"
                    },
                    {
                        "id": "bank_003",
                        "question": "카드를 분실했어요. 어떻게 해야 하나요?",
                        "answer": "카드 분실 시 즉시 해야 할 일:\n1. 카드 이용정지: 고객센터(1588-0000) 또는 모바일앱에서 즉시 정지\n2. 재발급 신청: 영업점 방문 또는 온라인 신청\n3. 부정사용 확인: 최근 거래내역 확인\n\n24시간 긴급정지 서비스를 이용하시면 언제든 카드를 정지할 수 있습니다.",
                        "keywords": ["카드", "분실", "정지", "재발급", "도난"],
                        "category": "카드",
                        "priority": 2,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z"
                    }
                ]
            },
            "insurance": {
                "category": "보험",
                "faqs": [
                    {
                        "id": "ins_001",
                        "question": "보험금 청구는 어떻게 하나요?",
                        "answer": "보험금 청구 절차:\n1. 사고 발생 즉시 보험회사에 신고\n2. 필요 서류 준비 (진단서, 영수증 등)\n3. 보험금 청구서 작성 및 제출\n4. 보험회사 심사\n5. 보험금 지급\n\n청구 시 필요한 서류는 보험 종류에 따라 다르므로 상담원에게 문의하세요.",
                        "keywords": ["보험금", "청구", "신청", "지급"],
                        "category": "보험금청구",
                        "priority": 1,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z"
                    }
                ]
            },
            "general": {
                "category": "일반",
                "faqs": [
                    {
                        "id": "gen_001",
                        "question": "고객센터 운영시간은 언제인가요?",
                        "answer": "고객센터 운영시간:\n- 평일: 오전 9시 ~ 오후 6시\n- 토요일: 오전 9시 ~ 오후 1시\n- 일요일 및 공휴일: 휴무\n\n긴급상황 시에는 24시간 자동응답서비스(ARS)를 이용하실 수 있습니다.",
                        "keywords": ["고객센터", "운영시간", "상담시간", "전화"],
                        "category": "고객서비스",
                        "priority": 1,
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2024-01-01T00:00:00Z"
                    }
                ]
            }
        }
    
    def _create_faq_index(self):
        """Elasticsearch FAQ 인덱스 생성"""
        if not self.es_client:
            return
        
        index_name = "faq_index"
        
        # 인덱스 매핑 정의
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "question": {
                        "type": "text",
                        "analyzer": "korean",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "answer": {
                        "type": "text",
                        "analyzer": "korean"
                    },
                    "keywords": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "priority": {"type": "integer"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"}
                }
            }
        }
        
        try:
            if not self.es_client.indices.exists(index=index_name):
                self.es_client.indices.create(index=index_name, body=mapping)
                self._index_faq_data()
                logger.info("FAQ 인덱스 생성 완료")
        except Exception as e:
            logger.error(f"FAQ 인덱스 생성 실패: {str(e)}")
    
    def _index_faq_data(self):
        """FAQ 데이터를 Elasticsearch에 인덱싱"""
        if not self.es_client:
            return
        
        for category_key, category_data in self.faq_data.items():
            for faq in category_data["faqs"]:
                try:
                    self.es_client.index(
                        index="faq_index",
                        id=faq["id"],
                        body=faq
                    )
                except Exception as e:
                    logger.error(f"FAQ 인덱싱 실패 ({faq['id']}): {str(e)}")
    
    def search_faq(self, query: str, category: str = None, limit: int = 5) -> List[Dict]:
        """
        FAQ 검색
        
        Args:
            query: 검색 쿼리
            category: 카테고리 필터
            limit: 결과 개수 제한
            
        Returns:
            검색 결과 리스트
        """
        # Elasticsearch 검색 (우선)
        if self.es_client:
            return self._search_with_elasticsearch(query, category, limit)
        
        # 기본 검색 (fallback)
        return self._search_with_similarity(query, category, limit)
    
    def _search_with_elasticsearch(self, query: str, category: str = None, limit: int = 5) -> List[Dict]:
        """
        Elasticsearch를 이용한 FAQ 검색
        
        Args:
            query: 검색 쿼리
            category: 카테고리 필터
            limit: 결과 개수 제한
            
        Returns:
            검색 결과 리스트
        """
        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["question^2", "answer", "keywords^1.5"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "match_phrase": {
                                "question": {
                                    "query": query,
                                    "boost": 3
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [
                {"priority": {"order": "asc"}},
                {"_score": {"order": "desc"}}
            ],
            "size": limit
        }
        
        # 카테고리 필터 추가
        if category:
            search_body["query"]["bool"]["filter"] = [
                {"term": {"category": category}}
            ]
        
        try:
            response = self.es_client.search(index="faq_index", body=search_body)
            
            results = []
            for hit in response["hits"]["hits"]:
                faq = hit["_source"]
                faq["score"] = hit["_score"]
                results.append(faq)
            
            return results
            
        except Exception as e:
            logger.error(f"Elasticsearch 검색 실패: {str(e)}")
            return self._search_with_similarity(query, category, limit)
    
    def _search_with_similarity(self, query: str, category: str = None, limit: int = 5) -> List[Dict]:
        """
        유사도 기반 FAQ 검색
        
        Args:
            query: 검색 쿼리
            category: 카테고리 필터
            limit: 결과 개수 제한
            
        Returns:
            검색 결과 리스트
        """
        query_lower = query.lower()
        results = []
        
        for category_key, category_data in self.faq_data.items():
            # 카테고리 필터 적용
            if category and category_key != category:
                continue
            
            for faq in category_data["faqs"]:
                score = 0
                
                # 질문 유사도 계산
                question_similarity = SequenceMatcher(
                    None, query_lower, faq["question"].lower()
                ).ratio()
                score += question_similarity * 0.6
                
                # 키워드 매칭
                keyword_matches = sum(1 for keyword in faq["keywords"] 
                                    if keyword.lower() in query_lower)
                if keyword_matches > 0:
                    score += (keyword_matches / len(faq["keywords"])) * 0.4
                
                # 부분 문자열 매칭
                if any(keyword.lower() in query_lower for keyword in faq["keywords"]):
                    score += 0.2
                
                if score > 0.1:  # 최소 임계값
                    faq_result = faq.copy()
                    faq_result["score"] = score
                    results.append(faq_result)
        
        # 점수순으로 정렬
        results.sort(key=lambda x: (-x["score"], x["priority"]))
        return results[:limit]
    
    def get_faq_by_id(self, faq_id: str) -> Optional[Dict]:
        """
        ID로 FAQ 조회
        
        Args:
            faq_id: FAQ ID
            
        Returns:
            FAQ 정보
        """
        for category_data in self.faq_data.values():
            for faq in category_data["faqs"]:
                if faq["id"] == faq_id:
                    return faq
        return None
    
    def get_faqs_by_category(self, category: str) -> List[Dict]:
        """
        카테고리별 FAQ 조회
        
        Args:
            category: 카테고리명
            
        Returns:
            FAQ 리스트
        """
        category_data = self.faq_data.get(category)
        if category_data:
            return category_data["faqs"]
        return []
    
    def get_popular_faqs(self, limit: int = 10) -> List[Dict]:
        """
        인기 FAQ 조회 (우선순위 기준)
        
        Args:
            limit: 결과 개수 제한
            
        Returns:
            인기 FAQ 리스트
        """
        all_faqs = []
        for category_data in self.faq_data.values():
            all_faqs.extend(category_data["faqs"])
        
        # 우선순위순으로 정렬
        all_faqs.sort(key=lambda x: x["priority"])
        return all_faqs[:limit]
    
    def add_faq(self, category: str, question: str, answer: str, 
                keywords: List[str], priority: int = 5) -> str:
        """
        새 FAQ 추가
        
        Args:
            category: 카테고리
            question: 질문
            answer: 답변
            keywords: 키워드 리스트
            priority: 우선순위
            
        Returns:
            생성된 FAQ ID
        """
        # FAQ ID 생성
        category_prefix = category[:3].upper()
        existing_count = len(self.get_faqs_by_category(category))
        faq_id = f"{category_prefix}_{existing_count + 1:03d}"
        
        new_faq = {
            "id": faq_id,
            "question": question,
            "answer": answer,
            "keywords": keywords,
            "category": category,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 메모리에 추가
        if category not in self.faq_data:
            self.faq_data[category] = {
                "category": category,
                "faqs": []
            }
        
        self.faq_data[category]["faqs"].append(new_faq)
        
        # Elasticsearch에 인덱싱
        if self.es_client:
            try:
                self.es_client.index(
                    index="faq_index",
                    id=faq_id,
                    body=new_faq
                )
            except Exception as e:
                logger.error(f"FAQ 인덱싱 실패: {str(e)}")
        
        logger.info(f"새 FAQ 추가: {faq_id}")
        return faq_id
    
    def update_faq(self, faq_id: str, updates: Dict) -> bool:
        """
        FAQ 업데이트
        
        Args:
            faq_id: FAQ ID
            updates: 업데이트할 필드들
            
        Returns:
            업데이트 성공 여부
        """
        for category_data in self.faq_data.values():
            for faq in category_data["faqs"]:
                if faq["id"] == faq_id:
                    faq.update(updates)
                    faq["updated_at"] = datetime.now().isoformat()
                    
                    # Elasticsearch 업데이트
                    if self.es_client:
                        try:
                            self.es_client.update(
                                index="faq_index",
                                id=faq_id,
                                body={"doc": faq}
                            )
                        except Exception as e:
                            logger.error(f"FAQ 업데이트 실패: {str(e)}")
                    
                    logger.info(f"FAQ 업데이트: {faq_id}")
                    return True
        return False
    
    def delete_faq(self, faq_id: str) -> bool:
        """
        FAQ 삭제
        
        Args:
            faq_id: FAQ ID
            
        Returns:
            삭제 성공 여부
        """
        for category_data in self.faq_data.values():
            faqs = category_data["faqs"]
            for i, faq in enumerate(faqs):
                if faq["id"] == faq_id:
                    del faqs[i]
                    
                    # Elasticsearch에서 삭제
                    if self.es_client:
                        try:
                            self.es_client.delete(index="faq_index", id=faq_id)
                        except Exception as e:
                            logger.error(f"FAQ 삭제 실패: {str(e)}")
                    
                    logger.info(f"FAQ 삭제: {faq_id}")
                    return True
        return False
    
    def get_categories(self) -> List[Dict]:
        """
        모든 카테고리 조회
        
        Returns:
            카테고리 리스트
        """
        categories = []
        for category_key, category_data in self.faq_data.items():
            categories.append({
                "key": category_key,
                "name": category_data["category"],
                "count": len(category_data["faqs"])
            })
        return categories
    
    def get_search_suggestions(self, partial_query: str, limit: int = 5) -> List[str]:
        """
        검색 자동완성 제안
        
        Args:
            partial_query: 부분 검색어
            limit: 제안 개수 제한
            
        Returns:
            제안 검색어 리스트
        """
        suggestions = set()
        partial_lower = partial_query.lower()
        
        for category_data in self.faq_data.values():
            for faq in category_data["faqs"]:
                # 질문에서 매칭되는 부분 찾기
                question_words = faq["question"].split()
                for word in question_words:
                    if word.lower().startswith(partial_lower):
                        suggestions.add(word)
                
                # 키워드에서 매칭되는 부분 찾기
                for keyword in faq["keywords"]:
                    if keyword.lower().startswith(partial_lower):
                        suggestions.add(keyword)
        
        return list(suggestions)[:limit]

# 사용 예시
if __name__ == "__main__":
    faq_manager = FAQManager()
    
    # FAQ 검색 테스트
    search_queries = [
        "계좌 잔액 확인",
        "카드 분실",
        "보험금 청구",
        "고객센터 전화번호"
    ]
    
    for query in search_queries:
        print(f"\n검색어: {query}")
        results = faq_manager.search_faq(query, limit=3)
        
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['question']}")
            print(f"   점수: {result.get('score', 0):.3f}")
            print(f"   카테고리: {result['category']}")
    
    # 카테고리별 FAQ 조회
    print(f"\n은행 업무 FAQ:")
    banking_faqs = faq_manager.get_faqs_by_category("banking")
    for faq in banking_faqs:
        print(f"- {faq['question']}")
    
    # 인기 FAQ 조회
    print(f"\n인기 FAQ:")
    popular_faqs = faq_manager.get_popular_faqs(limit=5)
    for faq in popular_faqs:
        print(f"- {faq['question']} (우선순위: {faq['priority']})") 