#!/bin/bash

# AI 챗봇 배포 스크립트
# AWS 환경에 챗봇 서비스 배포

set -e  # 오류 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 설정 변수
PROJECT_NAME="aicc-chatbot"
AWS_REGION="ap-northeast-2"
ECR_REPOSITORY="${PROJECT_NAME}"
ECS_CLUSTER="${PROJECT_NAME}-cluster"
ECS_SERVICE="${PROJECT_NAME}-service"
TASK_DEFINITION="${PROJECT_NAME}-task"

# 환경 변수 확인
check_prerequisites() {
    log_info "전제 조건 확인 중..."
    
    # AWS CLI 확인
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI가 설치되지 않았습니다."
        exit 1
    fi
    
    # Docker 확인
    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되지 않았습니다."
        exit 1
    fi
    
    # AWS 자격 증명 확인
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS 자격 증명이 설정되지 않았습니다."
        exit 1
    fi
    
    log_success "전제 조건 확인 완료"
}

# ECR 리포지토리 생성
create_ecr_repository() {
    log_info "ECR 리포지토리 확인/생성 중..."
    
    # 리포지토리 존재 확인
    if aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} &> /dev/null; then
        log_info "ECR 리포지토리가 이미 존재합니다: ${ECR_REPOSITORY}"
    else
        log_info "ECR 리포지토리 생성 중: ${ECR_REPOSITORY}"
        aws ecr create-repository \
            --repository-name ${ECR_REPOSITORY} \
            --region ${AWS_REGION} \
            --image-scanning-configuration scanOnPush=true
        log_success "ECR 리포지토리 생성 완료"
    fi
}

# Docker 이미지 빌드 및 푸시
build_and_push_image() {
    log_info "Docker 이미지 빌드 및 푸시 중..."
    
    # ECR 로그인
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION}.amazonaws.com
    
    # 이미지 태그 생성
    IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
    ECR_URI=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}
    
    # Docker 이미지 빌드
    log_info "Docker 이미지 빌드 중..."
    docker build -t ${PROJECT_NAME}:${IMAGE_TAG} -f ../Dockerfile ../
    
    # 이미지 태그 지정
    docker tag ${PROJECT_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}
    docker tag ${PROJECT_NAME}:${IMAGE_TAG} ${ECR_URI}:latest
    
    # ECR에 푸시
    log_info "ECR에 이미지 푸시 중..."
    docker push ${ECR_URI}:${IMAGE_TAG}
    docker push ${ECR_URI}:latest
    
    log_success "Docker 이미지 빌드 및 푸시 완료"
    echo "Image URI: ${ECR_URI}:${IMAGE_TAG}"
    
    # 환경 변수로 설정
    export IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"
}

# ECS 클러스터 생성
create_ecs_cluster() {
    log_info "ECS 클러스터 확인/생성 중..."
    
    # 클러스터 존재 확인
    if aws ecs describe-clusters --clusters ${ECS_CLUSTER} --region ${AWS_REGION} --query 'clusters[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
        log_info "ECS 클러스터가 이미 존재합니다: ${ECS_CLUSTER}"
    else
        log_info "ECS 클러스터 생성 중: ${ECS_CLUSTER}"
        aws ecs create-cluster \
            --cluster-name ${ECS_CLUSTER} \
            --capacity-providers FARGATE \
            --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 \
            --region ${AWS_REGION}
        log_success "ECS 클러스터 생성 완료"
    fi
}

# IAM 역할 생성
create_iam_roles() {
    log_info "IAM 역할 확인/생성 중..."
    
    # ECS Task Execution Role
    EXECUTION_ROLE_NAME="${PROJECT_NAME}-execution-role"
    if aws iam get-role --role-name ${EXECUTION_ROLE_NAME} &> /dev/null; then
        log_info "ECS 실행 역할이 이미 존재합니다: ${EXECUTION_ROLE_NAME}"
    else
        log_info "ECS 실행 역할 생성 중: ${EXECUTION_ROLE_NAME}"
        
        # Trust Policy 생성
        cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
        
        # 역할 생성
        aws iam create-role \
            --role-name ${EXECUTION_ROLE_NAME} \
            --assume-role-policy-document file://trust-policy.json
        
        # 정책 연결
        aws iam attach-role-policy \
            --role-name ${EXECUTION_ROLE_NAME} \
            --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
        
        rm trust-policy.json
        log_success "ECS 실행 역할 생성 완료"
    fi
    
    # ECS Task Role
    TASK_ROLE_NAME="${PROJECT_NAME}-task-role"
    if aws iam get-role --role-name ${TASK_ROLE_NAME} &> /dev/null; then
        log_info "ECS 태스크 역할이 이미 존재합니다: ${TASK_ROLE_NAME}"
    else
        log_info "ECS 태스크 역할 생성 중: ${TASK_ROLE_NAME}"
        
        # 역할 생성
        aws iam create-role \
            --role-name ${TASK_ROLE_NAME} \
            --assume-role-policy-document file://trust-policy.json
        
        # 챗봇 서비스에 필요한 정책 생성
        cat > chatbot-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectSentiment",
        "comprehend:DetectEntities",
        "lex:RecognizeText",
        "connect:StartOutboundVoiceContact",
        "sns:Publish",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "*"
    }
  ]
}
EOF
        
        # 정책 생성 및 연결
        POLICY_ARN=$(aws iam create-policy \
            --policy-name ${PROJECT_NAME}-policy \
            --policy-document file://chatbot-policy.json \
            --query 'Policy.Arn' --output text)
        
        aws iam attach-role-policy \
            --role-name ${TASK_ROLE_NAME} \
            --policy-arn ${POLICY_ARN}
        
        rm chatbot-policy.json
        log_success "ECS 태스크 역할 생성 완료"
    fi
    
    # 역할 ARN 가져오기
    export EXECUTION_ROLE_ARN=$(aws iam get-role --role-name ${EXECUTION_ROLE_NAME} --query 'Role.Arn' --output text)
    export TASK_ROLE_ARN=$(aws iam get-role --role-name ${TASK_ROLE_NAME} --query 'Role.Arn' --output text)
}

# VPC 및 보안 그룹 설정
setup_network() {
    log_info "네트워크 설정 확인 중..."
    
    # 기본 VPC 사용
    export VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION})
    
    if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
        log_error "기본 VPC를 찾을 수 없습니다."
        exit 1
    fi
    
    # 서브넷 가져오기
    export SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query 'Subnets[*].SubnetId' --output text --region ${AWS_REGION})
    
    # 보안 그룹 생성
    SG_NAME="${PROJECT_NAME}-sg"
    if aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" --region ${AWS_REGION} &> /dev/null; then
        export SECURITY_GROUP_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" --query 'SecurityGroups[0].GroupId' --output text --region ${AWS_REGION})
        log_info "보안 그룹이 이미 존재합니다: ${SG_NAME}"
    else
        log_info "보안 그룹 생성 중: ${SG_NAME}"
        export SECURITY_GROUP_ID=$(aws ec2 create-security-group \
            --group-name ${SG_NAME} \
            --description "Security group for ${PROJECT_NAME}" \
            --vpc-id ${VPC_ID} \
            --region ${AWS_REGION} \
            --query 'GroupId' --output text)
        
        # HTTP 트래픽 허용
        aws ec2 authorize-security-group-ingress \
            --group-id ${SECURITY_GROUP_ID} \
            --protocol tcp \
            --port 8000 \
            --cidr 0.0.0.0/0 \
            --region ${AWS_REGION}
        
        log_success "보안 그룹 생성 완료"
    fi
}

# ECS 태스크 정의 생성
create_task_definition() {
    log_info "ECS 태스크 정의 생성 중..."
    
    # 태스크 정의 JSON 생성
    cat > task-definition.json << EOF
{
  "family": "${TASK_DEFINITION}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "${PROJECT_NAME}",
      "image": "${IMAGE_URI}",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${PROJECT_NAME}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "environment": [
        {
          "name": "AWS_DEFAULT_REGION",
          "value": "${AWS_REGION}"
        },
        {
          "name": "ENVIRONMENT",
          "value": "production"
        }
      ]
    }
  ]
}
EOF
    
    # CloudWatch 로그 그룹 생성
    aws logs create-log-group --log-group-name "/ecs/${PROJECT_NAME}" --region ${AWS_REGION} 2>/dev/null || true
    
    # 태스크 정의 등록
    aws ecs register-task-definition \
        --cli-input-json file://task-definition.json \
        --region ${AWS_REGION}
    
    rm task-definition.json
    log_success "ECS 태스크 정의 생성 완료"
}

# ECS 서비스 생성
create_ecs_service() {
    log_info "ECS 서비스 확인/생성 중..."
    
    # 서비스 존재 확인
    if aws ecs describe-services --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --region ${AWS_REGION} --query 'services[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
        log_info "ECS 서비스가 이미 존재합니다. 업데이트 중..."
        aws ecs update-service \
            --cluster ${ECS_CLUSTER} \
            --service ${ECS_SERVICE} \
            --task-definition ${TASK_DEFINITION} \
            --region ${AWS_REGION}
    else
        log_info "ECS 서비스 생성 중: ${ECS_SERVICE}"
        
        # 첫 번째 서브넷 사용
        FIRST_SUBNET=$(echo ${SUBNET_IDS} | cut -d' ' -f1)
        
        aws ecs create-service \
            --cluster ${ECS_CLUSTER} \
            --service-name ${ECS_SERVICE} \
            --task-definition ${TASK_DEFINITION} \
            --desired-count 2 \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=[${FIRST_SUBNET}],securityGroups=[${SECURITY_GROUP_ID}],assignPublicIp=ENABLED}" \
            --region ${AWS_REGION}
    fi
    
    log_success "ECS 서비스 생성/업데이트 완료"
}

# Application Load Balancer 생성
create_load_balancer() {
    log_info "Application Load Balancer 설정 중..."
    
    ALB_NAME="${PROJECT_NAME}-alb"
    
    # ALB 존재 확인
    if aws elbv2 describe-load-balancers --names ${ALB_NAME} --region ${AWS_REGION} &> /dev/null; then
        log_info "ALB가 이미 존재합니다: ${ALB_NAME}"
        export ALB_ARN=$(aws elbv2 describe-load-balancers --names ${ALB_NAME} --query 'LoadBalancers[0].LoadBalancerArn' --output text --region ${AWS_REGION})
    else
        log_info "ALB 생성 중: ${ALB_NAME}"
        
        # 서브넷 배열 생성
        SUBNET_ARRAY=$(echo ${SUBNET_IDS} | tr ' ' ',')
        
        export ALB_ARN=$(aws elbv2 create-load-balancer \
            --name ${ALB_NAME} \
            --subnets ${SUBNET_ARRAY// /,} \
            --security-groups ${SECURITY_GROUP_ID} \
            --region ${AWS_REGION} \
            --query 'LoadBalancers[0].LoadBalancerArn' --output text)
        
        # 타겟 그룹 생성
        TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
            --name ${PROJECT_NAME}-tg \
            --protocol HTTP \
            --port 8000 \
            --vpc-id ${VPC_ID} \
            --target-type ip \
            --health-check-path /health \
            --region ${AWS_REGION} \
            --query 'TargetGroups[0].TargetGroupArn' --output text)
        
        # 리스너 생성
        aws elbv2 create-listener \
            --load-balancer-arn ${ALB_ARN} \
            --protocol HTTP \
            --port 80 \
            --default-actions Type=forward,TargetGroupArn=${TARGET_GROUP_ARN} \
            --region ${AWS_REGION}
        
        # ECS 서비스에 타겟 그룹 연결
        aws ecs update-service \
            --cluster ${ECS_CLUSTER} \
            --service ${ECS_SERVICE} \
            --load-balancers targetGroupArn=${TARGET_GROUP_ARN},containerName=${PROJECT_NAME},containerPort=8000 \
            --region ${AWS_REGION}
        
        log_success "ALB 생성 완료"
    fi
    
    # ALB DNS 이름 가져오기
    export ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns ${ALB_ARN} --query 'LoadBalancers[0].DNSName' --output text --region ${AWS_REGION})
}

# 배포 상태 확인
check_deployment_status() {
    log_info "배포 상태 확인 중..."
    
    # 서비스 안정화 대기
    log_info "ECS 서비스 안정화 대기 중... (최대 10분)"
    aws ecs wait services-stable \
        --cluster ${ECS_CLUSTER} \
        --services ${ECS_SERVICE} \
        --region ${AWS_REGION}
    
    # 서비스 상태 확인
    RUNNING_COUNT=$(aws ecs describe-services \
        --cluster ${ECS_CLUSTER} \
        --services ${ECS_SERVICE} \
        --region ${AWS_REGION} \
        --query 'services[0].runningCount' --output text)
    
    DESIRED_COUNT=$(aws ecs describe-services \
        --cluster ${ECS_CLUSTER} \
        --services ${ECS_SERVICE} \
        --region ${AWS_REGION} \
        --query 'services[0].desiredCount' --output text)
    
    if [ "$RUNNING_COUNT" = "$DESIRED_COUNT" ]; then
        log_success "배포 완료! 실행 중인 태스크: ${RUNNING_COUNT}/${DESIRED_COUNT}"
    else
        log_warning "일부 태스크가 아직 시작되지 않았습니다: ${RUNNING_COUNT}/${DESIRED_COUNT}"
    fi
}

# 배포 정보 출력
print_deployment_info() {
    log_info "배포 정보:"
    echo "=================================="
    echo "프로젝트: ${PROJECT_NAME}"
    echo "AWS 리전: ${AWS_REGION}"
    echo "ECS 클러스터: ${ECS_CLUSTER}"
    echo "ECS 서비스: ${ECS_SERVICE}"
    echo "Docker 이미지: ${IMAGE_URI}"
    if [ ! -z "${ALB_DNS}" ]; then
        echo "로드 밸런서 URL: http://${ALB_DNS}"
    fi
    echo "=================================="
}

# 정리 함수
cleanup() {
    log_info "임시 파일 정리 중..."
    rm -f trust-policy.json chatbot-policy.json task-definition.json
}

# 메인 실행 함수
main() {
    log_info "AI 챗봇 배포 시작..."
    
    # 전제 조건 확인
    check_prerequisites
    
    # ECR 리포지토리 생성
    create_ecr_repository
    
    # Docker 이미지 빌드 및 푸시
    build_and_push_image
    
    # ECS 클러스터 생성
    create_ecs_cluster
    
    # IAM 역할 생성
    create_iam_roles
    
    # 네트워크 설정
    setup_network
    
    # ECS 태스크 정의 생성
    create_task_definition
    
    # ECS 서비스 생성
    create_ecs_service
    
    # ALB 생성 (선택적)
    if [ "${CREATE_ALB:-true}" = "true" ]; then
        create_load_balancer
    fi
    
    # 배포 상태 확인
    check_deployment_status
    
    # 배포 정보 출력
    print_deployment_info
    
    # 정리
    cleanup
    
    log_success "AI 챗봇 배포 완료!"
}

# 스크립트 종료 시 정리
trap cleanup EXIT

# 도움말 출력
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "AI 챗봇 배포 스크립트"
    echo ""
    echo "사용법: $0 [옵션]"
    echo ""
    echo "환경 변수:"
    echo "  PROJECT_NAME     프로젝트 이름 (기본값: aicc-chatbot)"
    echo "  AWS_REGION       AWS 리전 (기본값: ap-northeast-2)"
    echo "  CREATE_ALB       ALB 생성 여부 (기본값: true)"
    echo ""
    echo "예시:"
    echo "  $0                           # 기본 설정으로 배포"
    echo "  PROJECT_NAME=my-bot $0       # 사용자 정의 프로젝트 이름으로 배포"
    echo "  CREATE_ALB=false $0          # ALB 없이 배포"
    exit 0
fi

# 메인 함수 실행
main "$@" 