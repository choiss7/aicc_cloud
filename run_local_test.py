#!/usr/bin/env python3
"""
로컬 개발환경 테스트 실행 스크립트
"""
import os
import sys
import json
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv('env.local')

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.handlers.chatbot_handler import lambda_handler, ChatbotHandler


def test_handler_directly():
    """핸들러를 직접 테스트"""
    print("=== 챗봇 핸들러 직접 테스트 ===")
    
    handler = ChatbotHandler()
    
    test_cases = [
        ("안녕하세요", "greeting"),
        ("상품 가격이 궁금해요", "product_inquiry"),
        ("서비스에 불만이 있어요", "complaint"),
        ("예약하고 싶어요", "reservation"),
        ("도움이 필요해요", "general_inquiry")
    ]
    
    for message, expected_intent in test_cases:
        print(f"\n메시지: {message}")
        result = handler.process_chat_message(message, "test_session")
        print(f"예상 의도: {expected_intent}")
        print(f"실제 의도: {result['intent']}")
        print(f"신뢰도: {result['confidence']}")
        print(f"응답: {result['response_text']}")
        print(f"성공: {'✅' if result['intent'] == expected_intent else '❌'}")
        print("-" * 60)


def test_lambda_handler():
    """Lambda 핸들러 테스트"""
    print("\n=== Lambda 핸들러 테스트 ===")
    
    test_events = [
        {
            'request_type': 'chat',
            'message': '안녕하세요',
            'session_id': 'lambda_test_1'
        },
        {
            'request_type': 'chat',
            'message': '상품 문의드립니다',
            'session_id': 'lambda_test_2'
        },
        {
            'request_type': 'escalation',
            'session_id': 'lambda_test_3',
            'reason': 'complaint'
        },
        {
            'request_type': 'invalid_type',
            'message': '잘못된 요청'
        }
    ]
    
    for i, event in enumerate(test_events, 1):
        print(f"\n--- Lambda 테스트 {i} ---")
        print(f"입력 이벤트: {json.dumps(event, ensure_ascii=False)}")
        
        result = lambda_handler(event, {})
        print(f"상태 코드: {result['statusCode']}")
        
        if result['statusCode'] == 200:
            body = json.loads(result['body'])
            print(f"성공: {body.get('success')}")
            if 'intent' in body:
                print(f"의도: {body['intent']}")
            if 'response_text' in body:
                print(f"응답: {body['response_text']}")
        else:
            body = json.loads(result['body'])
            print(f"오류: {body.get('error')}")
        
        print("-" * 60)


def test_escalation():
    """에스컬레이션 테스트"""
    print("\n=== 에스컬레이션 테스트 ===")
    
    handler = ChatbotHandler()
    
    # 불만 메시지 처리
    complaint_result = handler.process_chat_message("서비스가 너무 별로예요", "escalation_test")
    print(f"불만 메시지 처리:")
    print(f"의도: {complaint_result['intent']}")
    print(f"응답: {complaint_result['response_text']}")
    
    # 에스컬레이션 처리
    escalation_result = handler.process_escalation("escalation_test", "complaint")
    print(f"\n에스컬레이션 처리:")
    print(f"성공: {escalation_result['success']}")
    print(f"에스컬레이션 ID: {escalation_result.get('escalation_id')}")
    print(f"메시지: {escalation_result.get('message')}")
    print(f"예상 대기시간: {escalation_result.get('estimated_wait_time')}")


def test_performance():
    """성능 테스트"""
    print("\n=== 성능 테스트 ===")
    
    import time
    import threading
    
    handler = ChatbotHandler()
    
    # 단일 요청 응답 시간 테스트
    start_time = time.time()
    result = handler.process_chat_message("성능 테스트 메시지", "perf_test")
    end_time = time.time()
    
    response_time = end_time - start_time
    print(f"단일 요청 응답 시간: {response_time:.3f}초")
    print(f"응답 성공: {result['success']}")
    
    # 동시 요청 테스트
    print("\n동시 요청 테스트 (10개 요청)...")
    results = []
    
    def make_request(i):
        result = handler.process_chat_message(f"동시 테스트 {i}", f"concurrent_{i}")
        results.append(result)
    
    start_time = time.time()
    threads = []
    
    for i in range(10):
        thread = threading.Thread(target=make_request, args=(i,))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    end_time = time.time()
    
    total_time = end_time - start_time
    success_count = sum(1 for r in results if r['success'])
    
    print(f"총 처리 시간: {total_time:.3f}초")
    print(f"성공한 요청: {success_count}/10")
    print(f"평균 응답 시간: {total_time/10:.3f}초")


def test_error_handling():
    """오류 처리 테스트"""
    print("\n=== 오류 처리 테스트 ===")
    
    handler = ChatbotHandler()
    
    # 빈 메시지
    result1 = handler.process_chat_message("", "error_test_1")
    print(f"빈 메시지 처리: {result1['success']}")
    
    # 매우 긴 메시지
    long_message = "테스트 " * 1000
    result2 = handler.process_chat_message(long_message, "error_test_2")
    print(f"긴 메시지 처리: {result2['success']}")
    
    # 특수 문자
    special_message = "!@#$%^&*()_+{}|:<>?[]\\;'\",./"
    result3 = handler.process_chat_message(special_message, "error_test_3")
    print(f"특수 문자 처리: {result3['success']}")
    
    # 유니코드 문자
    unicode_message = "🚀🎉💻🔥⭐️🌟✨🎯🎪🎨"
    result4 = handler.process_chat_message(unicode_message, "error_test_4")
    print(f"유니코드 처리: {result4['success']}")


def main():
    """메인 실행 함수"""
    print("🚀 AICC Cloud 로컬 개발환경 테스트 시작")
    print(f"환경: {os.getenv('ENVIRONMENT', 'development')}")
    print(f"디버그 모드: {os.getenv('APP_DEBUG', 'false')}")
    print("=" * 80)
    
    try:
        # 1. 핸들러 직접 테스트
        test_handler_directly()
        
        # 2. Lambda 핸들러 테스트
        test_lambda_handler()
        
        # 3. 에스컬레이션 테스트
        test_escalation()
        
        # 4. 성능 테스트
        test_performance()
        
        # 5. 오류 처리 테스트
        test_error_handling()
        
        print("\n" + "=" * 80)
        print("✅ 모든 테스트가 완료되었습니다!")
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main() 