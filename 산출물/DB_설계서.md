# DB 설계서

## 1. 주요 테이블 설계

### 1.1 고객 테이블 (customer)
| 컬럼명         | 타입         | 설명           |
|---------------|-------------|----------------|
| customer_id   | BIGINT      | 고객 고유번호  |
| name          | VARCHAR(50) | 고객명         |
| phone         | VARCHAR(20) | 연락처         |
| email         | VARCHAR(100)| 이메일         |
| reg_date      | DATETIME    | 등록일         |

### 1.2 상담 테이블 (consult)
| 컬럼명         | 타입         | 설명           |
|---------------|-------------|----------------|
| consult_id    | BIGINT      | 상담 고유번호  |
| customer_id   | BIGINT      | 고객 ID        |
| agent_id      | BIGINT      | 상담원 ID      |
| start_time    | DATETIME    | 상담 시작시간  |
| end_time      | DATETIME    | 상담 종료시간  |
| channel       | VARCHAR(20) | 채널(음성/채팅)|
| status        | VARCHAR(20) | 상담 상태      |

### 1.3 상담원 테이블 (agent)
| 컬럼명         | 타입         | 설명           |
|---------------|-------------|----------------|
| agent_id      | BIGINT      | 상담원 고유번호|
| name          | VARCHAR(50) | 상담원명       |
| team          | VARCHAR(50) | 소속팀         |
| status        | VARCHAR(20) | 상태(대기/상담)|

### 1.4 챗봇 시나리오 테이블 (chatbot_scenario)
| 컬럼명         | 타입         | 설명           |
|---------------|-------------|----------------|
| scenario_id   | BIGINT      | 시나리오 ID    |
| title         | VARCHAR(100)| 시나리오명     |
| content       | TEXT        | 시나리오 내용  |
| updated_at    | DATETIME    | 수정일         |

### 1.5 녹취 테이블 (recording)
| 컬럼명         | 타입         | 설명           |
|---------------|-------------|----------------|
| recording_id  | BIGINT      | 녹취 ID        |
| consult_id    | BIGINT      | 상담 ID        |
| file_path     | VARCHAR(255)| 파일 경로      |
| created_at    | DATETIME    | 생성일         |

## 2. 기타 참고
- 인덱스, 외래키 등 상세 설계는 추후 상세화 

## 3. 인덱스 및 외래키 예시
- consult.customer_id → customer.customer_id (외래키)
- consult.agent_id → agent.agent_id (외래키)
- recording.consult_id → consult.consult_id (외래키)
- 주요 검색 컬럼에 인덱스 생성 (예: customer_id, agent_id, start_time)

## 4. 샤딩/파티셔닝
- 상담 이력(consult) 테이블: 날짜 기준 파티셔닝 권장
- 대용량 데이터 분산 저장 필요시 샤딩 적용

## 5. 데이터 보안
- 개인정보(이름, 연락처, 이메일 등) 암호화/마스킹 적용
- 접근 권한별 DB 계정 분리 및 감사 로그 기록 