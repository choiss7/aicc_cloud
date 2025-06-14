# AWS Connect 구성 자동화

> 🚀 **AWS Connect 인스턴스 및 관련 리소스 자동 구성**  
> CloudFormation, Terraform, CDK를 활용한 Infrastructure as Code (IaC) 구현

## 📋 목차

- [개요](#-개요)
- [구성 요소](#-구성-요소)
- [사전 요구사항](#-사전-요구사항)
- [CloudFormation 배포](#-cloudformation-배포)
- [Terraform 배포](#-terraform-배포)
- [AWS CDK 배포](#-aws-cdk-배포)
- [수동 설정 가이드](#-수동-설정-가이드)
- [Contact Flow 관리](#-contact-flow-관리)
- [모니터링 설정](#-모니터링-설정)
- [보안 설정](#-보안-설정)
- [문제 해결](#-문제-해결)

## 🎯 개요

이 디렉토리는 AWS Connect 기반 AI 콜센터 구축을 위한 인프라 자동화 스크립트와 설정 파일들을 포함합니다. Infrastructure as Code (IaC) 방식을 통해 일관되고 반복 가능한 환경 구성을 제공합니다.

### 🎯 목표
- **자동화된 인프라 구성**: 수동 설정 오류 최소화
- **일관된 환경**: 개발/스테이징/프로덕션 환경 일관성 보장
- **버전 관리**: 인프라 변경사항 추적 및 롤백 지원
- **확장성**: 트래픽 증가에 따른 자동 확장 지원

## 🏗️ 구성 요소

### AWS Connect 핵심 리소스
- **Connect Instance**: 콜센터 인스턴스
- **Contact Flows**: 통화 흐름 정의
- **Queues**: 상담 대기열 구성
- **Routing Profiles**: 라우팅 프로필
- **Users**: 상담원 계정 관리
- **Phone Numbers**: 전화번호 할당

### 연동 서비스
- **AWS Lex**: 챗봇 및 음성봇
- **AWS Lambda**: 비즈니스 로직 처리
- **DynamoDB**: 데이터 저장
- **S3**: 녹취 파일 저장
- **CloudWatch**: 모니터링 및 로깅
- **IAM**: 권한 관리

## 📋 사전 요구사항

### AWS 계정 설정
- AWS 계정 및 적절한 권한
- AWS CLI 설치 및 구성
- Connect 서비스 활성화

### 필요 권한
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "connect:*",
        "lex:*",
        "lambda:*",
        "dynamodb:*",
        "s3:*",
        "iam:*",
        "cloudformation:*",
        "logs:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 도구 설치
```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Terraform (선택사항)
wget https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_linux_amd64.zip
unzip terraform_1.5.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# AWS CDK (선택사항)
npm install -g aws-cdk
```

## ☁️ CloudFormation 배포

### 1. 기본 Connect 인스턴스 생성
```bash
# 스택 배포
aws cloudformation create-stack \
  --stack-name aicc-connect-instance \
  --template-body file://cloudformation/connect-instance.yaml \
  --parameters ParameterKey=InstanceAlias,ParameterValue=aicc-prod \
  --capabilities CAPABILITY_IAM

# 배포 상태 확인
aws cloudformation describe-stacks \
  --stack-name aicc-connect-instance \
  --query 'Stacks[0].StackStatus'
```

### 2. Contact Flow 배포
```bash
# Contact Flow 생성
aws cloudformation create-stack \
  --stack-name aicc-contact-flows \
  --template-body file://cloudformation/contact-flows.yaml \
  --parameters ParameterKey=ConnectInstanceId,ParameterValue=your-instance-id
```

### 3. 통합 서비스 배포
```bash
# Lex, Lambda, DynamoDB 등 연동 서비스
aws cloudformation create-stack \
  --stack-name aicc-integration-services \
  --template-body file://cloudformation/integration-services.yaml \
  --capabilities CAPABILITY_IAM
```

## 🌍 Terraform 배포

### 1. 초기화 및 계획
```bash
cd terraform/
terraform init
terraform plan -var-file="environments/prod.tfvars"
```

### 2. 배포 실행
```bash
# 프로덕션 환경 배포
terraform apply -var-file="environments/prod.tfvars" -auto-approve

# 개발 환경 배포
terraform apply -var-file="environments/dev.tfvars" -auto-approve
```

### 3. 리소스 확인
```bash
# 생성된 리소스 확인
terraform show
terraform output
```

## 🚀 AWS CDK 배포

### 1. CDK 프로젝트 초기화
```bash
cd cdk/
npm install
cdk bootstrap
```

### 2. 스택 배포
```bash
# 개발 환경
cdk deploy AiccConnectStack-dev

# 프로덕션 환경
cdk deploy AiccConnectStack-prod
```

### 3. 스택 관리
```bash
# 스택 목록 확인
cdk list

# 차이점 확인
cdk diff AiccConnectStack-prod

# 스택 삭제
cdk destroy AiccConnectStack-dev
```

## 🔧 수동 설정 가이드

### 1. Connect 인스턴스 생성
1. AWS Console → Connect 서비스 이동
2. "인스턴스 생성" 클릭
3. 인스턴스 별칭 입력: `aicc-prod`
4. 관리자 사용자 생성
5. 전화번호 할당

### 2. Contact Flow 설정
```json
{
  "Version": "2019-10-30",
  "StartAction": "12345678-1234-1234-1234-123456789012",
  "Actions": [
    {
      "Identifier": "12345678-1234-1234-1234-123456789012",
      "Type": "MessageParticipant",
      "Parameters": {
        "Text": "안녕하세요. AI 콜센터에 연결되었습니다."
      },
      "Transitions": {
        "NextAction": "87654321-4321-4321-4321-210987654321"
      }
    }
  ]
}
```

### 3. 큐 및 라우팅 프로필 설정
```bash
# 큐 생성
aws connect create-queue \
  --instance-id your-instance-id \
  --name "General Support" \
  --description "일반 고객 지원 큐"

# 라우팅 프로필 생성
aws connect create-routing-profile \
  --instance-id your-instance-id \
  --name "Customer Service" \
  --description "고객 서비스 라우팅 프로필"
```

## 📞 Contact Flow 관리

### Contact Flow 템플릿
```
connect/
├── contact-flows/
│   ├── inbound-flow.json          # 인바운드 통화 흐름
│   ├── chatbot-flow.json          # 챗봇 연동 흐름
│   ├── escalation-flow.json       # 상담원 연결 흐름
│   ├── ivr-flow.json              # IVR 메뉴 흐름
│   └── outbound-flow.json         # 아웃바운드 통화 흐름
```

### Contact Flow 배포 스크립트
```bash
#!/bin/bash
# deploy-contact-flows.sh

INSTANCE_ID="your-instance-id"
FLOWS_DIR="contact-flows"

for flow_file in $FLOWS_DIR/*.json; do
  flow_name=$(basename "$flow_file" .json)
  
  aws connect create-contact-flow \
    --instance-id $INSTANCE_ID \
    --name "$flow_name" \
    --type CONTACT_FLOW \
    --content file://"$flow_file"
    
  echo "Deployed: $flow_name"
done
```

## 📊 모니터링 설정

### CloudWatch 대시보드
```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Connect", "CallsPerInterval", "InstanceId", "your-instance-id"],
          ["AWS/Connect", "ConcurrentCalls", "InstanceId", "your-instance-id"],
          ["AWS/Connect", "MissedCalls", "InstanceId", "your-instance-id"]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "ap-northeast-2",
        "title": "Connect 통화 메트릭"
      }
    }
  ]
}
```

### 알람 설정
```bash
# 높은 대기 시간 알람
aws cloudwatch put-metric-alarm \
  --alarm-name "Connect-High-Queue-Wait-Time" \
  --alarm-description "큐 대기 시간이 높음" \
  --metric-name "QueueTime" \
  --namespace "AWS/Connect" \
  --statistic "Average" \
  --period 300 \
  --threshold 120 \
  --comparison-operator "GreaterThanThreshold"
```

## 🔒 보안 설정

### IAM 역할 및 정책
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "connect:GetContactAttributes",
        "connect:UpdateContactAttributes"
      ],
      "Resource": "arn:aws:connect:*:*:instance/*/contact/*"
    }
  ]
}
```

### 데이터 암호화
- **전송 중 암호화**: TLS 1.2 이상
- **저장 시 암호화**: S3 KMS 암호화
- **데이터베이스 암호화**: DynamoDB 암호화

### 접근 제어
```bash
# IP 기반 접근 제어
aws connect put-user-security-profiles \
  --instance-id your-instance-id \
  --user-id user-id \
  --security-profile-ids security-profile-id
```

## 🔧 문제 해결

### 일반적인 문제

#### 1. Connect 인스턴스 생성 실패
```bash
# 권한 확인
aws iam get-user
aws iam list-attached-user-policies --user-name your-username

# 서비스 한도 확인
aws service-quotas get-service-quota \
  --service-code connect \
  --quota-code L-1234567890
```

#### 2. Contact Flow 배포 실패
```bash
# Contact Flow 유효성 검사
aws connect describe-contact-flow \
  --instance-id your-instance-id \
  --contact-flow-id your-flow-id
```

#### 3. 전화번호 할당 문제
```bash
# 사용 가능한 전화번호 확인
aws connect list-phone-numbers \
  --instance-id your-instance-id
```

### 로그 확인
```bash
# CloudWatch 로그 확인
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/connect"

# 특정 로그 스트림 확인
aws logs get-log-events \
  --log-group-name "/aws/connect/your-instance-id" \
  --log-stream-name "your-log-stream"
```

### 성능 최적화
- **동시 통화 수 모니터링**
- **큐 대기 시간 최적화**
- **Contact Flow 효율성 개선**
- **Lambda 함수 성능 튜닝**

## 📚 참고 자료

### AWS 공식 문서
- [AWS Connect 관리 가이드](https://docs.aws.amazon.com/connect/latest/adminguide/)
- [AWS Connect API 참조](https://docs.aws.amazon.com/connect/latest/APIReference/)
- [Contact Flow 언어 참조](https://docs.aws.amazon.com/connect/latest/adminguide/contact-flow-language.html)

### 모범 사례
- [Connect 보안 모범 사례](https://docs.aws.amazon.com/connect/latest/adminguide/security-best-practices.html)
- [성능 최적화 가이드](https://docs.aws.amazon.com/connect/latest/adminguide/optimization.html)
- [비용 최적화 전략](https://docs.aws.amazon.com/connect/latest/adminguide/cost-optimization.html)

## 🤝 기여하기

1. 새로운 Contact Flow 템플릿 추가
2. IaC 스크립트 개선
3. 모니터링 대시보드 확장
4. 문서 업데이트

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

---

**Made with ❤️ by AICC Cloud Team** 