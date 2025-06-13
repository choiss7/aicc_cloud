# API 명세서

## 1. 고객 관련 API

### 1.1 고객 정보 조회
- 엔드포인트: `GET /api/customers/{customer_id}`
- 파라미터: customer_id (path)
- 응답 예시:
```json
{
  "customer_id": 1,
  "name": "홍길동",
  "phone": "010-1234-5678",
  "email": "hong@test.com"
}
```
- 설명: 고객 상세 정보 조회

## 2. 상담 관련 API

### 2.1 상담 등록
- 엔드포인트: `POST /api/consults`
- 파라미터: customer_id, agent_id, channel
- 응답 예시:
```json
{
  "consult_id": 1001,
  "status": "진행중"
}
```
- 설명: 신규 상담 등록

### 2.2 상담 이력 조회
- 엔드포인트: `GET /api/consults?customer_id={customer_id}`
- 파라미터: customer_id (query)
- 응답 예시:
```json
[
  { "consult_id": 1001, "start_time": "2024-06-01T10:00:00", "status": "완료" }
]
```
- 설명: 고객별 상담 이력 목록 조회

## 3. 챗봇 관련 API

### 3.1 챗봇 응답
- 엔드포인트: `POST /api/chatbot/respond`
- 파라미터: message, customer_id
- 응답 예시:
```json
{
  "response": "안녕하세요, 무엇을 도와드릴까요?"
}
```
- 설명: 챗봇의 자동 응답 반환

## 4. 외부 연동 API

### 4.1 CRM 연동
- 엔드포인트: `POST /api/integrations/crm`
- 파라미터: customer_id, data
- 설명: 외부 CRM 시스템으로 데이터 전송

## 5. 참고
- 인증/보안, 에러코드 등은 별도 상세화

## 6. 인증/보안
- 모든 API는 JWT 토큰 기반 인증 필요
- 민감 정보 접근 시 추가 인증(OAuth2 등) 적용 가능

## 7. 에러코드 및 예외 처리
| 코드 | 메시지           | 설명                 |
|------|------------------|----------------------|
| 200  | OK               | 정상 처리            |
| 400  | Bad Request      | 파라미터 오류        |
| 401  | Unauthorized     | 인증 실패            |
| 404  | Not Found        | 데이터 없음          |
| 500  | Internal Error   | 서버 내부 오류       |

## 8. 페이징/필터링
- 목록 조회 API는 page, size, filter 파라미터 지원
- 예시: `GET /api/consults?page=1&size=20&status=완료` 