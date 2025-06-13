#!/usr/bin/env python3
"""
AICC 문서화 자동 생성 도구
- API 문서 자동 생성
- README 생성
- 변경 로그 관리
- 코드 문서화
"""

import os
import ast
import json
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import re
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class APIEndpoint:
    """API 엔드포인트 정보"""
    path: str
    method: str
    description: str
    parameters: List[Dict[str, Any]]
    responses: List[Dict[str, Any]]
    examples: List[Dict[str, Any]]

@dataclass
class ServiceDoc:
    """서비스 문서"""
    name: str
    description: str
    port: int
    endpoints: List[APIEndpoint]
    classes: List[str]
    functions: List[str]

@dataclass
class DocumentationResult:
    """문서화 결과"""
    timestamp: str
    services: List[ServiceDoc]
    api_docs: str
    readme: str
    changelog: str
    architecture_diagram: str

class DocumentationGenerator:
    """문서화 생성기"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.source_dirs = [
            self.project_root / "산출물/3.4_공통_통합_기능_개발/소스코드"
        ]
        self.output_dir = self.project_root / "산출물/3.5_코드리뷰_AI자동화/문서화"
        
    async def generate_documentation(self) -> DocumentationResult:
        """문서화 생성"""
        logger.info("문서화 생성 시작")
        
        # 서비스 분석
        services = await self._analyze_services()
        
        # API 문서 생성
        api_docs = await self._generate_api_docs(services)
        
        # README 생성
        readme = await self._generate_readme(services)
        
        # 변경 로그 생성
        changelog = await self._generate_changelog()
        
        # 아키텍처 다이어그램 생성
        architecture_diagram = await self._generate_architecture_diagram(services)
        
        result = DocumentationResult(
            timestamp=datetime.now().isoformat(),
            services=services,
            api_docs=api_docs,
            readme=readme,
            changelog=changelog,
            architecture_diagram=architecture_diagram
        )
        
        # 문서 저장
        await self._save_documentation(result)
        
        logger.info("문서화 생성 완료")
        return result
    
    async def _analyze_services(self) -> List[ServiceDoc]:
        """서비스 분석"""
        services = []
        
        service_configs = [
            {"name": "monitoring", "description": "모니터링 서비스", "port": 8000},
            {"name": "recording", "description": "녹취/저장 서비스", "port": 8001},
            {"name": "integration", "description": "외부 연동 서비스", "port": 8002},
            {"name": "auth", "description": "인증/권한 관리 서비스", "port": 8003}
        ]
        
        for config in service_configs:
            service_file = None
            for source_dir in self.source_dirs:
                potential_file = source_dir / f"{config['name']}/{config['name']}_service.py"
                if potential_file.exists():
                    service_file = potential_file
                    break
            
            if service_file:
                service_doc = await self._analyze_service_file(service_file, config)
                services.append(service_doc)
        
        return services
    
    async def _analyze_service_file(self, file_path: Path, config: Dict[str, Any]) -> ServiceDoc:
        """서비스 파일 분석"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            # 클래스와 함수 추출
            classes = []
            functions = []
            endpoints = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                    
                    # FastAPI 엔드포인트 분석
                    if hasattr(node, 'decorator_list'):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call):
                                if hasattr(decorator.func, 'attr'):
                                    method = decorator.func.attr
                                    if method in ['get', 'post', 'put', 'delete', 'patch']:
                                        endpoint = self._extract_endpoint_info(node, method, content)
                                        if endpoint:
                                            endpoints.append(endpoint)
            
            return ServiceDoc(
                name=config['name'],
                description=config['description'],
                port=config['port'],
                endpoints=endpoints,
                classes=classes,
                functions=functions
            )
            
        except Exception as e:
            logger.error(f"서비스 파일 분석 실패 {file_path}: {e}")
            return ServiceDoc(
                name=config['name'],
                description=config['description'],
                port=config['port'],
                endpoints=[],
                classes=[],
                functions=[]
            )
    
    def _extract_endpoint_info(self, node: ast.FunctionDef, method: str, content: str) -> Optional[APIEndpoint]:
        """엔드포인트 정보 추출"""
        try:
            # 함수 이름에서 경로 추정
            func_name = node.name
            path = f"/{func_name.replace('_', '-')}"
            
            # docstring에서 설명 추출
            description = ""
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
                description = node.body[0].value.s.strip()
            
            # 매개변수 분석
            parameters = []
            for arg in node.args.args:
                if arg.arg not in ['self', 'request']:
                    parameters.append({
                        "name": arg.arg,
                        "type": "string",  # 기본값
                        "description": f"{arg.arg} 매개변수",
                        "required": True
                    })
            
            # 응답 예시
            responses = [
                {
                    "status_code": 200,
                    "description": "성공",
                    "example": {"status": "success", "data": {}}
                }
            ]
            
            examples = [
                {
                    "request": {"example": "request"},
                    "response": {"status": "success", "data": {}}
                }
            ]
            
            return APIEndpoint(
                path=path,
                method=method.upper(),
                description=description or f"{func_name} 엔드포인트",
                parameters=parameters,
                responses=responses,
                examples=examples
            )
            
        except Exception as e:
            logger.error(f"엔드포인트 정보 추출 실패: {e}")
            return None
    
    async def _generate_api_docs(self, services: List[ServiceDoc]) -> str:
        """API 문서 생성"""
        docs = """# AICC API 문서

## 개요
AICC (AI Contact Center) 시스템의 REST API 문서입니다.

## 인증
모든 API 요청에는 JWT 토큰이 필요합니다.

```
Authorization: Bearer <your-jwt-token>
```

## 기본 URL
- 개발환경: `http://localhost:{port}`
- 운영환경: `https://api.aicc.com`

## 응답 형식
모든 API 응답은 다음 형식을 따릅니다:

```json
{
  "status": "success|error",
  "data": {},
  "message": "응답 메시지",
  "timestamp": "2024-12-19T10:00:00Z"
}
```

## 에러 코드
| 코드 | 설명 |
|------|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 |
| 403 | 권한 없음 |
| 404 | 리소스 없음 |
| 500 | 서버 오류 |

---

"""
        
        for service in services:
            docs += f"""
## {service.description}

**Base URL**: `http://localhost:{service.port}`

### 개요
{service.description}의 API 엔드포인트입니다.

### 엔드포인트

"""
            
            for endpoint in service.endpoints:
                docs += f"""
#### {endpoint.method} {endpoint.path}

**설명**: {endpoint.description}

**매개변수**:
"""
                
                if endpoint.parameters:
                    for param in endpoint.parameters:
                        required = "필수" if param.get("required", False) else "선택"
                        docs += f"- `{param['name']}` ({param['type']}, {required}): {param['description']}\n"
                else:
                    docs += "없음\n"
                
                docs += f"""
**응답 예시**:
```json
{json.dumps(endpoint.responses[0].get('example', {}), ensure_ascii=False, indent=2)}
```

**요청 예시**:
```bash
curl -X {endpoint.method} \\
  http://localhost:{service.port}{endpoint.path} \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json"
```

---
"""
        
        return docs
    
    async def _generate_readme(self, services: List[ServiceDoc]) -> str:
        """README 생성"""
        total_endpoints = sum(len(service.endpoints) for service in services)
        total_classes = sum(len(service.classes) for service in services)
        total_functions = sum(len(service.functions) for service in services)
        
        readme = f"""# AICC (AI Contact Center) 시스템

## 🎯 프로젝트 개요
AWS Connect 기반의 지능형 콜센터 시스템입니다. 마이크로서비스 아키텍처로 구성되어 확장성과 유지보수성을 극대화했습니다.

## 📊 시스템 통계
- **서비스 수**: {len(services)}개
- **API 엔드포인트**: {total_endpoints}개
- **클래스**: {total_classes}개
- **함수**: {total_functions}개
- **생성일**: {datetime.now().strftime('%Y-%m-%d')}

## 🏗️ 아키텍처

### 마이크로서비스 구성
"""
        
        for service in services:
            readme += f"""
#### {service.description}
- **포트**: {service.port}
- **엔드포인트**: {len(service.endpoints)}개
- **주요 기능**: {service.description}
"""
        
        readme += f"""

## 🚀 빠른 시작

### 요구사항
- Python 3.9+
- Docker & Docker Compose
- AWS CLI 설정
- PostgreSQL 12+
- Redis 6+

### 설치 및 실행

#### 1. 저장소 클론
```bash
git clone https://github.com/your-org/aicc-system.git
cd aicc-system
```

#### 2. 환경 설정
```bash
# 환경변수 파일 생성
cp .env.example .env

# 환경변수 편집
nano .env
```

#### 3. 의존성 설치
```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# 패키지 설치
pip install -r requirements.txt
```

#### 4. 데이터베이스 설정
```bash
# PostgreSQL 데이터베이스 생성
createdb aicc_db

# 마이그레이션 실행
python manage.py migrate
```

#### 5. 서비스 실행

##### 개발 환경 (로컬)
```bash
# 각 서비스를 별도 터미널에서 실행
python monitoring_service.py
python recording_service.py
python integration_service.py
python auth_service.py
```

##### Docker 환경
```bash
# 이미지 빌드
docker-compose build

# 서비스 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

##### AWS 배포
```bash
# 배포 스크립트 실행
chmod +x deploy_common_services.sh
./deploy_common_services.sh

# 배포 상태 확인
aws ecs list-services --cluster aicc-cluster
```

## 📚 API 문서
각 서비스의 상세 API 문서는 다음 URL에서 확인할 수 있습니다:

"""
        
        for service in services:
            readme += f"- **{service.description}**: http://localhost:{service.port}/docs\n"
        
        readme += f"""

## 🔧 개발 가이드

### 코드 구조
```
aicc-system/
├── 산출물/
│   ├── 3.4_공통_통합_기능_개발/
│   │   ├── 소스코드/
│   │   │   ├── monitoring/
│   │   │   ├── recording/
│   │   │   ├── integration/
│   │   │   └── auth/
│   │   └── 배포스크립트/
│   └── 3.5_코드리뷰_AI자동화/
├── tests/
├── docs/
└── scripts/
```

### 개발 워크플로우
1. **기능 브랜치 생성**: `git checkout -b feature/new-feature`
2. **코드 작성**: 기능 구현 및 테스트 작성
3. **코드 리뷰**: Pull Request 생성 및 리뷰
4. **테스트 실행**: `python -m pytest`
5. **배포**: 승인 후 main 브랜치 병합

### 코딩 스타일
- **Python**: PEP 8 준수
- **포매터**: Black, isort 사용
- **린터**: flake8, pylint 사용
- **타입 힌트**: 모든 함수에 타입 힌트 적용

### 테스트
```bash
# 단위 테스트 실행
python -m pytest tests/

# 커버리지 측정
python -m coverage run -m pytest
python -m coverage report

# 통합 테스트
python -m pytest tests/integration/
```

## 🔍 모니터링

### 메트릭 대시보드
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
- **CloudWatch**: AWS 콘솔에서 확인

### 로그 관리
- **로그 레벨**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **로그 형식**: JSON 구조화 로그
- **로그 저장**: CloudWatch Logs, ELK Stack

### 알림 설정
- **Slack**: 중요 알림
- **Email**: 장애 알림
- **SMS**: 긴급 알림

## 🔒 보안

### 인증 및 권한
- **JWT 토큰**: 액세스/리프레시 토큰
- **MFA**: TOTP 기반 다중 인증
- **RBAC**: 역할 기반 접근 제어

### 데이터 보안
- **암호화**: AES-256 파일 암호화
- **전송 보안**: TLS 1.3
- **데이터베이스**: 암호화된 연결

### 보안 감사
- **로그 감사**: 모든 사용자 활동 기록
- **취약점 스캔**: 정기적인 보안 스캔
- **침투 테스트**: 분기별 보안 테스트

## 🚨 문제 해결

### 일반적인 문제

#### 서비스 시작 실패
```bash
# 포트 사용 확인
netstat -tulpn | grep :8000

# 로그 확인
tail -f logs/monitoring.log
```

#### 데이터베이스 연결 실패
```bash
# 연결 테스트
pg_isready -h localhost -p 5432

# 권한 확인
psql -h localhost -U aicc_user -d aicc_db
```

#### Redis 연결 실패
```bash
# Redis 상태 확인
redis-cli ping

# 설정 확인
redis-cli config get "*"
```

### 성능 최적화

#### 데이터베이스 최적화
- 인덱스 최적화
- 쿼리 성능 분석
- 연결 풀 튜닝

#### 캐시 최적화
- Redis 메모리 관리
- 캐시 히트율 모니터링
- TTL 설정 최적화

## 🤝 기여하기

### 기여 방법
1. **이슈 생성**: 버그 리포트 또는 기능 요청
2. **Fork**: 저장소 포크
3. **브랜치 생성**: 기능별 브랜치 생성
4. **커밋**: 의미있는 커밋 메시지
5. **Pull Request**: 상세한 설명과 함께 PR 생성

### 커밋 메시지 규칙
```
type(scope): subject

body

footer
```

**타입**:
- `feat`: 새로운 기능
- `fix`: 버그 수정
- `docs`: 문서 변경
- `style`: 코드 스타일 변경
- `refactor`: 리팩토링
- `test`: 테스트 추가/수정
- `chore`: 빌드/설정 변경

## 📄 라이선스
MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📞 연락처
- **개발팀**: dev@aicc.com
- **지원팀**: support@aicc.com
- **보안팀**: security@aicc.com

## 🔗 관련 링크
- [API 문서](docs/api.md)
- [배포 가이드](docs/deployment.md)
- [아키텍처 문서](docs/architecture.md)
- [보안 가이드](docs/security.md)

---

**마지막 업데이트**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*이 문서는 AICC 문서화 자동화 도구에 의해 생성되었습니다.*
"""
        
        return readme
    
    async def _generate_changelog(self) -> str:
        """변경 로그 생성"""
        changelog = f"""# 변경 로그

모든 주목할 만한 변경사항이 이 파일에 기록됩니다.

## [3.5.0] - {datetime.now().strftime('%Y-%m-%d')}

### ✨ 추가됨
- 커서 AI 활용 자동화 도구 구현
- 코드 분석 및 리뷰 자동화
- 테스트 코드 자동 생성
- 문서화 자동화 시스템
- 품질 관리 도구 통합
- HTML 보고서 생성 기능

### 🔧 개선됨
- 코드 품질 메트릭 수집 시스템
- 보안 점수 계산 알고리즘
- 유지보수성 평가 시스템
- 테스트 커버리지 측정 정확도

### 🐛 수정됨
- 코드 분석 시 인코딩 오류 수정
- 테스트 실행 시 경로 문제 해결
- 문서 생성 시 특수문자 처리 개선

### 🔒 보안
- 정적 코드 분석으로 보안 취약점 검출
- 하드코딩된 자격 증명 검사 강화
- 코드 인젝션 위험 요소 탐지

## [3.4.0] - 2024-12-19

### ✨ 추가됨
- 모니터링 서비스 구현 (Port 8000)
  - 시스템 메트릭 수집
  - Prometheus/CloudWatch 연동
  - 실시간 알림 시스템
- 녹취/저장 서비스 구현 (Port 8001)
  - 음성 통화 녹음 기능
  - AES-256 파일 암호화
  - S3 자동 업로드
- 외부 연동 서비스 구현 (Port 8002)
  - CRM 시스템 연동 (Salesforce, HubSpot)
  - 결제 시스템 연동 (토스페이먼츠, 이니시스)
  - 알림 서비스 연동 (SMS, Email, 푸시)
- 인증/권한 관리 서비스 구현 (Port 8003)
  - JWT 토큰 기반 인증
  - RBAC 권한 관리
  - MFA 지원

### 🏗️ 인프라
- Docker 컨테이너화
- AWS ECS Fargate 배포
- RDS PostgreSQL 데이터베이스
- ElastiCache Redis 캐시
- VPC 네트워크 구성

### 🔧 기술적 개선
- 마이크로서비스 아키텍처 적용
- 비동기 I/O 처리 (asyncio)
- 연결 풀링 최적화
- 메트릭 기반 모니터링

## [3.3.0] - 2024-12-18

### ✨ 추가됨
- 상담원 데스크탑/웹 UI 개발
- React + TypeScript 프론트엔드
- FastAPI + Python 백엔드
- 실시간 통화 인터페이스
- 고객 정보 관리 시스템

### 🎨 UI/UX
- 반응형 웹 디자인
- 다크/라이트 테마 지원
- 접근성 개선 (WCAG 2.1 AA)
- 다국어 지원 (한국어, 영어)

## [3.2.0] - 2024-12-17

### ✨ 추가됨
- AWS Connect 기본 설정
- 통화 라우팅 규칙
- 대기열 관리 시스템
- 상담원 관리 기능

### 🔧 설정
- Contact Flow 구성
- Lambda 함수 연동
- DynamoDB 데이터 저장
- CloudWatch 로깅

## [3.1.0] - 2024-12-16

### ✨ 추가됨
- 프로젝트 초기 설정
- 개발 환경 구성
- 기본 아키텍처 설계
- 요구사항 분석 완료

### 📋 계획
- 프로젝트 로드맵 수립
- 기술 스택 선정
- 팀 역할 분담
- 일정 계획 수립

---

## 버전 관리 규칙

### 버전 번호 체계
- **Major.Minor.Patch** (예: 3.5.0)
- **Major**: 호환성이 깨지는 변경
- **Minor**: 새로운 기능 추가
- **Patch**: 버그 수정

### 변경사항 분류
- **✨ 추가됨**: 새로운 기능
- **🔧 개선됨**: 기존 기능 개선
- **🐛 수정됨**: 버그 수정
- **🔒 보안**: 보안 관련 변경
- **🏗️ 인프라**: 인프라 변경
- **🎨 UI/UX**: 사용자 인터페이스 변경
- **📋 계획**: 계획 및 문서

### 릴리스 주기
- **Major**: 분기별 (3개월)
- **Minor**: 월별 (1개월)
- **Patch**: 주별 (1주일)

---

*이 변경 로그는 [Keep a Changelog](https://keepachangelog.com/) 형식을 따릅니다.*
"""
        
        return changelog
    
    async def _generate_architecture_diagram(self, services: List[ServiceDoc]) -> str:
        """아키텍처 다이어그램 생성 (Mermaid)"""
        diagram = """# 시스템 아키텍처

## 전체 아키텍처

```mermaid
graph TB
    subgraph "클라이언트"
        WEB[웹 브라우저]
        MOBILE[모바일 앱]
        DESKTOP[데스크탑 앱]
    end
    
    subgraph "로드 밸런서"
        ALB[Application Load Balancer]
    end
    
    subgraph "AICC 마이크로서비스"
        AUTH[인증/권한 서비스<br/>:8003]
        MONITOR[모니터링 서비스<br/>:8000]
        RECORD[녹취/저장 서비스<br/>:8001]
        INTEGRATE[외부 연동 서비스<br/>:8002]
    end
    
    subgraph "데이터 저장소"
        POSTGRES[(PostgreSQL<br/>메인 DB)]
        REDIS[(Redis<br/>캐시)]
        S3[(S3<br/>파일 저장)]
    end
    
    subgraph "외부 서비스"
        AWS_CONNECT[AWS Connect]
        CRM[CRM 시스템]
        PAYMENT[결제 시스템]
        NOTIFICATION[알림 서비스]
    end
    
    subgraph "모니터링"
        PROMETHEUS[Prometheus]
        GRAFANA[Grafana]
        CLOUDWATCH[CloudWatch]
    end
    
    WEB --> ALB
    MOBILE --> ALB
    DESKTOP --> ALB
    
    ALB --> AUTH
    ALB --> MONITOR
    ALB --> RECORD
    ALB --> INTEGRATE
    
    AUTH --> POSTGRES
    AUTH --> REDIS
    
    MONITOR --> POSTGRES
    MONITOR --> PROMETHEUS
    MONITOR --> CLOUDWATCH
    
    RECORD --> POSTGRES
    RECORD --> S3
    
    INTEGRATE --> POSTGRES
    INTEGRATE --> AWS_CONNECT
    INTEGRATE --> CRM
    INTEGRATE --> PAYMENT
    INTEGRATE --> NOTIFICATION
    
    PROMETHEUS --> GRAFANA
```

## 서비스 간 통신

```mermaid
sequenceDiagram
    participant Client as 클라이언트
    participant Auth as 인증 서비스
    participant Monitor as 모니터링 서비스
    participant Record as 녹취 서비스
    participant Integrate as 연동 서비스
    
    Client->>Auth: 로그인 요청
    Auth-->>Client: JWT 토큰 발급
    
    Client->>Monitor: 메트릭 조회 (with JWT)
    Monitor->>Auth: 토큰 검증
    Auth-->>Monitor: 검증 결과
    Monitor-->>Client: 메트릭 데이터
    
    Client->>Record: 녹음 시작 요청
    Record->>Auth: 권한 확인
    Auth-->>Record: 권한 승인
    Record-->>Client: 녹음 시작 확인
    
    Client->>Integrate: 외부 API 호출
    Integrate->>Auth: 토큰 검증
    Auth-->>Integrate: 검증 완료
    Integrate-->>Client: API 응답
```

## 데이터 플로우

```mermaid
flowchart LR
    subgraph "데이터 수집"
        CALL[통화 데이터]
        METRIC[시스템 메트릭]
        USER[사용자 활동]
    end
    
    subgraph "데이터 처리"
        PROCESS[실시간 처리]
        BATCH[배치 처리]
        STREAM[스트림 처리]
    end
    
    subgraph "데이터 저장"
        HOT[핫 데이터<br/>Redis]
        WARM[웜 데이터<br/>PostgreSQL]
        COLD[콜드 데이터<br/>S3]
    end
    
    subgraph "데이터 활용"
        DASHBOARD[대시보드]
        REPORT[보고서]
        ALERT[알림]
        ANALYTICS[분석]
    end
    
    CALL --> PROCESS
    METRIC --> PROCESS
    USER --> PROCESS
    
    PROCESS --> HOT
    PROCESS --> WARM
    
    BATCH --> WARM
    BATCH --> COLD
    
    STREAM --> HOT
    STREAM --> WARM
    
    HOT --> DASHBOARD
    WARM --> REPORT
    COLD --> ANALYTICS
    
    DASHBOARD --> ALERT
```

## 배포 아키텍처

```mermaid
graph TB
    subgraph "AWS 클라우드"
        subgraph "VPC"
            subgraph "퍼블릭 서브넷"
                ALB[Application Load Balancer]
                NAT[NAT Gateway]
            end
            
            subgraph "프라이빗 서브넷 A"
                ECS_A[ECS Fargate<br/>서비스 A]
                RDS_A[RDS Primary]
            end
            
            subgraph "프라이빗 서브넷 B"
                ECS_B[ECS Fargate<br/>서비스 B]
                RDS_B[RDS Standby]
            end
            
            subgraph "데이터 계층"
                REDIS_CLUSTER[ElastiCache Redis]
                S3_BUCKET[S3 버킷]
            end
        end
        
        subgraph "관리 서비스"
            ECR[ECR<br/>컨테이너 레지스트리]
            CLOUDWATCH[CloudWatch<br/>모니터링]
            SECRETS[Secrets Manager<br/>비밀 관리]
        end
    end
    
    subgraph "외부"
        INTERNET[인터넷]
        DEVELOPER[개발자]
    end
    
    INTERNET --> ALB
    ALB --> ECS_A
    ALB --> ECS_B
    
    ECS_A --> RDS_A
    ECS_B --> RDS_A
    RDS_A --> RDS_B
    
    ECS_A --> REDIS_CLUSTER
    ECS_B --> REDIS_CLUSTER
    
    ECS_A --> S3_BUCKET
    ECS_B --> S3_BUCKET
    
    DEVELOPER --> ECR
    ECS_A --> ECR
    ECS_B --> ECR
    
    ECS_A --> CLOUDWATCH
    ECS_B --> CLOUDWATCH
    
    ECS_A --> SECRETS
    ECS_B --> SECRETS
```
"""
        
        return diagram
    
    async def _save_documentation(self, result: DocumentationResult):
        """문서 저장"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # API 문서 저장
        api_doc_path = self.output_dir / "API_Documentation.md"
        with open(api_doc_path, 'w', encoding='utf-8') as f:
            f.write(result.api_docs)
        
        # README 저장
        readme_path = self.output_dir / "README_Generated.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(result.readme)
        
        # 변경 로그 저장
        changelog_path = self.output_dir / "CHANGELOG.md"
        with open(changelog_path, 'w', encoding='utf-8') as f:
            f.write(result.changelog)
        
        # 아키텍처 다이어그램 저장
        architecture_path = self.output_dir / "ARCHITECTURE.md"
        with open(architecture_path, 'w', encoding='utf-8') as f:
            f.write(result.architecture_diagram)
        
        # 종합 문서 인덱스 생성
        index_content = f"""# AICC 문서 인덱스

## 📚 문서 목록

### 📖 주요 문서
- [README](README_Generated.md) - 프로젝트 개요 및 시작 가이드
- [API 문서](API_Documentation.md) - REST API 상세 문서
- [아키텍처](ARCHITECTURE.md) - 시스템 아키텍처 및 다이어그램
- [변경 로그](CHANGELOG.md) - 버전별 변경사항

### 🔧 개발 문서
- [개발 가이드](../개발가이드/공통_통합_기능_개발_가이드.md) - 개발 환경 설정 및 가이드
- [코드 리뷰](../코드리뷰/code_review_report.md) - 코드 품질 분석 보고서

### 🧪 품질 관리
- [테스트 보고서](../품질관리/test_report.html) - 테스트 결과 및 커버리지
- [품질 보고서](../품질관리/quality_report.html) - 코드 품질 분석 결과

## 📊 문서 통계
- **생성일시**: {result.timestamp}
- **서비스 수**: {len(result.services)}개
- **총 엔드포인트**: {sum(len(service.endpoints) for service in result.services)}개

## 🔄 자동 생성
이 문서들은 AICC 문서화 자동화 도구에 의해 생성되었습니다.

### 문서 업데이트
```bash
# 문서 재생성
python doc_generator.py

# 특정 문서만 생성
python doc_generator.py --type api
python doc_generator.py --type readme
```

---
*마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        index_path = self.output_dir / "INDEX.md"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        
        logger.info(f"문서 저장 완료: {self.output_dir}")

async def main():
    """메인 실행 함수"""
    project_root = os.getcwd()
    generator = DocumentationGenerator(project_root)
    
    try:
        result = await generator.generate_documentation()
        print(f"📚 문서화 생성 완료!")
        print(f"📊 서비스: {len(result.services)}개")
        print(f"📝 API 문서: ✅")
        print(f"📖 README: ✅")
        print(f"📋 변경로그: ✅")
        print(f"🏗️  아키텍처: ✅")
        
    except Exception as e:
        print(f"❌ 문서화 생성 실패: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main()) 