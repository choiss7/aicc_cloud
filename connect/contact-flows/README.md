# AWS Connect Contact Flow

이 디렉토리에는 AWS Connect 콜센터의 Contact Flow 정의 파일들이 포함되어 있습니다.

## 주요 Contact Flow

### inbound-flow.json
- 인바운드 고객 통화를 처리하는 기본 Contact Flow
- 주요 기능:
  - 영업시간 확인
  - 고객 메뉴 선택 처리
  - 고객 인증
  - Amazon Lex 챗봇 연동
  - 상담원 연결
  - 콜백 예약

## Contact Flow 배포 방법

### AWS Console을 통한 배포
1. AWS Connect 콘솔에 로그인
2. 해당 Connect 인스턴스 선택
3. "Contact flows" 메뉴 선택
4. "Create contact flow" 클릭
5. 메뉴에서 "Import flow" 선택
6. JSON 파일 업로드
7. 필요한 경우 설정 조정
8. "Save" 및 "Publish" 클릭

### AWS CLI를 통한 배포
```bash
aws connect create-contact-flow \
  --instance-id your-instance-id \
  --name "Inbound Flow" \
  --type CONTACT_FLOW \
  --content file://inbound-flow.json
```

## Contact Flow 수정 시 주의사항

1. ARN 참조 업데이트
   - 모든 리소스 ARN(Lambda, Queue, Bot 등)은 환경에 맞게 업데이트 필요

2. 흐름 테스트
   - 배포 전 Amazon Connect 콘솔에서 테스트 필수
   - 모든 경로와 조건 확인

3. 버전 관리
   - 변경 전 기존 Flow 백업
   - 주요 변경사항 문서화

## Contact Flow 구조 설명

### 기본 구조
```
시작 → 환영 메시지 → 영업시간 확인 → 메인 메뉴 → 
  ├── 일반 문의 → 챗봇 연동
  ├── 기술 지원 → 챗봇 연동
  ├── 계정 관련 → 고객 인증 → 챗봇 연동
  └── 상담원 연결 → 대기열 설정 → 상담원 연결
```

### 에러 처리
- 인증 실패: 상담원 직접 연결
- 챗봇 오류: 상담원 직접 연결
- 대기열 가득 참: 콜백 옵션 제공 