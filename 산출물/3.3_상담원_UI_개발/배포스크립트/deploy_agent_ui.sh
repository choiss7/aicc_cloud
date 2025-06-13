#!/bin/bash

# 상담원 UI 배포 스크립트
# AWS ECS Fargate를 사용한 컨테이너 배포

set -e

# 환경 변수 설정
PROJECT_NAME="agent-desktop-ui"
AWS_REGION="ap-northeast-2"
ECR_REPOSITORY_FRONTEND="${PROJECT_NAME}-frontend"
ECR_REPOSITORY_BACKEND="${PROJECT_NAME}-backend"
ECS_CLUSTER="${PROJECT_NAME}-cluster"
ECS_SERVICE_FRONTEND="${PROJECT_NAME}-frontend-service"
ECS_SERVICE_BACKEND="${PROJECT_NAME}-backend-service"
VPC_NAME="${PROJECT_NAME}-vpc"
ALB_NAME="${PROJECT_NAME}-alb"

# 색상 코드
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

# AWS CLI 설치 확인
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI가 설치되지 않았습니다."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS 자격 증명이 설정되지 않았습니다."
        exit 1
    fi
    
    log_success "AWS CLI 설정 확인 완료"
}

# Docker 설치 확인
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되지 않았습니다."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker 데몬이 실행되지 않았습니다."
        exit 1
    fi
    
    log_success "Docker 설정 확인 완료"
}

# Node.js 설치 확인
check_nodejs() {
    if ! command -v node &> /dev/null; then
        log_error "Node.js가 설치되지 않았습니다."
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        log_error "npm이 설치되지 않았습니다."
        exit 1
    fi
    
    log_success "Node.js 설정 확인 완료"
}

# ECR 리포지토리 생성
create_ecr_repositories() {
    log_info "ECR 리포지토리 생성 중..."
    
    # Frontend 리포지토리
    if ! aws ecr describe-repositories --repository-names $ECR_REPOSITORY_FRONTEND --region $AWS_REGION &> /dev/null; then
        aws ecr create-repository \
            --repository-name $ECR_REPOSITORY_FRONTEND \
            --region $AWS_REGION \
            --image-scanning-configuration scanOnPush=true
        log_success "Frontend ECR 리포지토리 생성 완료"
    else
        log_info "Frontend ECR 리포지토리가 이미 존재합니다"
    fi
    
    # Backend 리포지토리
    if ! aws ecr describe-repositories --repository-names $ECR_REPOSITORY_BACKEND --region $AWS_REGION &> /dev/null; then
        aws ecr create-repository \
            --repository-name $ECR_REPOSITORY_BACKEND \
            --region $AWS_REGION \
            --image-scanning-configuration scanOnPush=true
        log_success "Backend ECR 리포지토리 생성 완료"
    else
        log_info "Backend ECR 리포지토리가 이미 존재합니다"
    fi
}

# VPC 및 네트워크 인프라 생성
create_vpc_infrastructure() {
    log_info "VPC 인프라 생성 중..."
    
    # VPC 생성
    VPC_ID=$(aws ec2 create-vpc \
        --cidr-block 10.0.0.0/16 \
        --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$VPC_NAME}]" \
        --query 'Vpc.VpcId' \
        --output text \
        --region $AWS_REGION)
    
    log_success "VPC 생성 완료: $VPC_ID"
    
    # 인터넷 게이트웨이 생성
    IGW_ID=$(aws ec2 create-internet-gateway \
        --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=$VPC_NAME-igw}]" \
        --query 'InternetGateway.InternetGatewayId' \
        --output text \
        --region $AWS_REGION)
    
    # VPC에 인터넷 게이트웨이 연결
    aws ec2 attach-internet-gateway \
        --vpc-id $VPC_ID \
        --internet-gateway-id $IGW_ID \
        --region $AWS_REGION
    
    log_success "인터넷 게이트웨이 생성 및 연결 완료: $IGW_ID"
    
    # 퍼블릭 서브넷 생성
    SUBNET_1_ID=$(aws ec2 create-subnet \
        --vpc-id $VPC_ID \
        --cidr-block 10.0.1.0/24 \
        --availability-zone ${AWS_REGION}a \
        --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$VPC_NAME-public-1}]" \
        --query 'Subnet.SubnetId' \
        --output text \
        --region $AWS_REGION)
    
    SUBNET_2_ID=$(aws ec2 create-subnet \
        --vpc-id $VPC_ID \
        --cidr-block 10.0.2.0/24 \
        --availability-zone ${AWS_REGION}c \
        --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$VPC_NAME-public-2}]" \
        --query 'Subnet.SubnetId' \
        --output text \
        --region $AWS_REGION)
    
    log_success "퍼블릭 서브넷 생성 완료: $SUBNET_1_ID, $SUBNET_2_ID"
    
    # 라우팅 테이블 생성 및 설정
    ROUTE_TABLE_ID=$(aws ec2 create-route-table \
        --vpc-id $VPC_ID \
        --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=$VPC_NAME-public-rt}]" \
        --query 'RouteTable.RouteTableId' \
        --output text \
        --region $AWS_REGION)
    
    aws ec2 create-route \
        --route-table-id $ROUTE_TABLE_ID \
        --destination-cidr-block 0.0.0.0/0 \
        --gateway-id $IGW_ID \
        --region $AWS_REGION
    
    aws ec2 associate-route-table \
        --subnet-id $SUBNET_1_ID \
        --route-table-id $ROUTE_TABLE_ID \
        --region $AWS_REGION
    
    aws ec2 associate-route-table \
        --subnet-id $SUBNET_2_ID \
        --route-table-id $ROUTE_TABLE_ID \
        --region $AWS_REGION
    
    log_success "라우팅 테이블 설정 완료"
    
    # 보안 그룹 생성
    SECURITY_GROUP_ID=$(aws ec2 create-security-group \
        --group-name $PROJECT_NAME-sg \
        --description "Security group for $PROJECT_NAME" \
        --vpc-id $VPC_ID \
        --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$PROJECT_NAME-sg}]" \
        --query 'GroupId' \
        --output text \
        --region $AWS_REGION)
    
    # 보안 그룹 규칙 추가
    aws ec2 authorize-security-group-ingress \
        --group-id $SECURITY_GROUP_ID \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    aws ec2 authorize-security-group-ingress \
        --group-id $SECURITY_GROUP_ID \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    aws ec2 authorize-security-group-ingress \
        --group-id $SECURITY_GROUP_ID \
        --protocol tcp \
        --port 3000 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    aws ec2 authorize-security-group-ingress \
        --group-id $SECURITY_GROUP_ID \
        --protocol tcp \
        --port 8000 \
        --cidr 0.0.0.0/0 \
        --region $AWS_REGION
    
    log_success "보안 그룹 생성 및 설정 완료: $SECURITY_GROUP_ID"
    
    # 환경 변수 저장
    echo "export VPC_ID=$VPC_ID" > .env.deploy
    echo "export SUBNET_1_ID=$SUBNET_1_ID" >> .env.deploy
    echo "export SUBNET_2_ID=$SUBNET_2_ID" >> .env.deploy
    echo "export SECURITY_GROUP_ID=$SECURITY_GROUP_ID" >> .env.deploy
}

# Application Load Balancer 생성
create_load_balancer() {
    log_info "Application Load Balancer 생성 중..."
    
    source .env.deploy
    
    ALB_ARN=$(aws elbv2 create-load-balancer \
        --name $ALB_NAME \
        --subnets $SUBNET_1_ID $SUBNET_2_ID \
        --security-groups $SECURITY_GROUP_ID \
        --scheme internet-facing \
        --type application \
        --ip-address-type ipv4 \
        --tags Key=Name,Value=$ALB_NAME \
        --query 'LoadBalancers[0].LoadBalancerArn' \
        --output text \
        --region $AWS_REGION)
    
    log_success "ALB 생성 완료: $ALB_ARN"
    
    # 타겟 그룹 생성 (Frontend)
    FRONTEND_TG_ARN=$(aws elbv2 create-target-group \
        --name "${PROJECT_NAME}-frontend-tg" \
        --protocol HTTP \
        --port 3000 \
        --vpc-id $VPC_ID \
        --target-type ip \
        --health-check-path "/" \
        --health-check-interval-seconds 30 \
        --health-check-timeout-seconds 5 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 3 \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text \
        --region $AWS_REGION)
    
    # 타겟 그룹 생성 (Backend)
    BACKEND_TG_ARN=$(aws elbv2 create-target-group \
        --name "${PROJECT_NAME}-backend-tg" \
        --protocol HTTP \
        --port 8000 \
        --vpc-id $VPC_ID \
        --target-type ip \
        --health-check-path "/health" \
        --health-check-interval-seconds 30 \
        --health-check-timeout-seconds 5 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 3 \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text \
        --region $AWS_REGION)
    
    log_success "타겟 그룹 생성 완료"
    
    # 리스너 생성
    aws elbv2 create-listener \
        --load-balancer-arn $ALB_ARN \
        --protocol HTTP \
        --port 80 \
        --default-actions Type=forward,TargetGroupArn=$FRONTEND_TG_ARN \
        --region $AWS_REGION
    
    # API 경로 규칙 추가
    aws elbv2 create-rule \
        --listener-arn $(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[0].ListenerArn' --output text --region $AWS_REGION) \
        --priority 100 \
        --conditions Field=path-pattern,Values="/api/*" \
        --actions Type=forward,TargetGroupArn=$BACKEND_TG_ARN \
        --region $AWS_REGION
    
    log_success "ALB 리스너 및 규칙 설정 완료"
    
    # 환경 변수 추가
    echo "export ALB_ARN=$ALB_ARN" >> .env.deploy
    echo "export FRONTEND_TG_ARN=$FRONTEND_TG_ARN" >> .env.deploy
    echo "export BACKEND_TG_ARN=$BACKEND_TG_ARN" >> .env.deploy
}

# ECS 클러스터 생성
create_ecs_cluster() {
    log_info "ECS 클러스터 생성 중..."
    
    aws ecs create-cluster \
        --cluster-name $ECS_CLUSTER \
        --capacity-providers FARGATE \
        --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 \
        --tags key=Name,value=$ECS_CLUSTER \
        --region $AWS_REGION
    
    log_success "ECS 클러스터 생성 완료: $ECS_CLUSTER"
}

# IAM 역할 생성
create_iam_roles() {
    log_info "IAM 역할 생성 중..."
    
    # ECS 태스크 실행 역할
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
    
    aws iam create-role \
        --role-name ${PROJECT_NAME}-execution-role \
        --assume-role-policy-document file://trust-policy.json \
        --region $AWS_REGION || true
    
    aws iam attach-role-policy \
        --role-name ${PROJECT_NAME}-execution-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
        --region $AWS_REGION || true
    
    # ECS 태스크 역할
    aws iam create-role \
        --role-name ${PROJECT_NAME}-task-role \
        --assume-role-policy-document file://trust-policy.json \
        --region $AWS_REGION || true
    
    # 태스크 역할에 필요한 정책 연결
    cat > task-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "rds:*",
        "s3:*",
        "sns:*",
        "connect:*",
        "comprehend:*",
        "lex:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF
    
    aws iam put-role-policy \
        --role-name ${PROJECT_NAME}-task-role \
        --policy-name ${PROJECT_NAME}-task-policy \
        --policy-document file://task-policy.json \
        --region $AWS_REGION || true
    
    rm -f trust-policy.json task-policy.json
    
    log_success "IAM 역할 생성 완료"
}

# Frontend 빌드 및 배포
build_and_deploy_frontend() {
    log_info "Frontend 빌드 및 배포 시작..."
    
    cd frontend
    
    # 의존성 설치
    npm install
    
    # 프로덕션 빌드
    npm run build
    
    # Docker 이미지 빌드
    docker build -t $ECR_REPOSITORY_FRONTEND .
    
    # ECR 로그인
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com
    
    # 이미지 태그 및 푸시
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    docker tag $ECR_REPOSITORY_FRONTEND:latest $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_FRONTEND:latest
    docker push $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_FRONTEND:latest
    
    cd ..
    
    log_success "Frontend 이미지 빌드 및 푸시 완료"
}

# Backend 빌드 및 배포
build_and_deploy_backend() {
    log_info "Backend 빌드 및 배포 시작..."
    
    cd backend
    
    # Docker 이미지 빌드
    docker build -t $ECR_REPOSITORY_BACKEND .
    
    # ECR 로그인
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com
    
    # 이미지 태그 및 푸시
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    docker tag $ECR_REPOSITORY_BACKEND:latest $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_BACKEND:latest
    docker push $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_BACKEND:latest
    
    cd ..
    
    log_success "Backend 이미지 빌드 및 푸시 완료"
}

# ECS 서비스 배포
deploy_ecs_services() {
    log_info "ECS 서비스 배포 시작..."
    
    source .env.deploy
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    
    # Frontend 태스크 정의
    cat > frontend-task-definition.json << EOF
{
  "family": "${PROJECT_NAME}-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-execution-role",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-task-role",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_FRONTEND}:latest",
      "portMappings": [
        {
          "containerPort": 3000,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${PROJECT_NAME}-frontend",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
    
    # Backend 태스크 정의
    cat > backend-task-definition.json << EOF
{
  "family": "${PROJECT_NAME}-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-execution-role",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-task-role",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_BACKEND}:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "essential": true,
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://user:password@localhost:5432/agent_db"
        },
        {
          "name": "AWS_REGION",
          "value": "${AWS_REGION}"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${PROJECT_NAME}-backend",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
    
    # CloudWatch 로그 그룹 생성
    aws logs create-log-group --log-group-name "/ecs/${PROJECT_NAME}-frontend" --region $AWS_REGION || true
    aws logs create-log-group --log-group-name "/ecs/${PROJECT_NAME}-backend" --region $AWS_REGION || true
    
    # 태스크 정의 등록
    aws ecs register-task-definition \
        --cli-input-json file://frontend-task-definition.json \
        --region $AWS_REGION
    
    aws ecs register-task-definition \
        --cli-input-json file://backend-task-definition.json \
        --region $AWS_REGION
    
    # ECS 서비스 생성
    aws ecs create-service \
        --cluster $ECS_CLUSTER \
        --service-name $ECS_SERVICE_FRONTEND \
        --task-definition "${PROJECT_NAME}-frontend" \
        --desired-count 2 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1_ID,$SUBNET_2_ID],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
        --load-balancers "targetGroupArn=$FRONTEND_TG_ARN,containerName=frontend,containerPort=3000" \
        --region $AWS_REGION || true
    
    aws ecs create-service \
        --cluster $ECS_CLUSTER \
        --service-name $ECS_SERVICE_BACKEND \
        --task-definition "${PROJECT_NAME}-backend" \
        --desired-count 2 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1_ID,$SUBNET_2_ID],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
        --load-balancers "targetGroupArn=$BACKEND_TG_ARN,containerName=backend,containerPort=8000" \
        --region $AWS_REGION || true
    
    # 정리
    rm -f frontend-task-definition.json backend-task-definition.json
    
    log_success "ECS 서비스 배포 완료"
}

# 배포 상태 확인
check_deployment_status() {
    log_info "배포 상태 확인 중..."
    
    # ALB DNS 이름 가져오기
    source .env.deploy
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --load-balancer-arns $ALB_ARN \
        --query 'LoadBalancers[0].DNSName' \
        --output text \
        --region $AWS_REGION)
    
    log_success "배포 완료!"
    log_info "Frontend URL: http://$ALB_DNS"
    log_info "Backend API URL: http://$ALB_DNS/api"
    
    # 서비스 상태 확인
    log_info "서비스 상태 확인 중..."
    aws ecs describe-services \
        --cluster $ECS_CLUSTER \
        --services $ECS_SERVICE_FRONTEND $ECS_SERVICE_BACKEND \
        --region $AWS_REGION \
        --query 'services[*].[serviceName,runningCount,desiredCount,taskDefinition]' \
        --output table
}

# 메인 실행 함수
main() {
    log_info "상담원 UI 배포 시작..."
    
    # 사전 요구사항 확인
    check_aws_cli
    check_docker
    check_nodejs
    
    # 인프라 생성
    create_ecr_repositories
    create_vpc_infrastructure
    create_load_balancer
    create_ecs_cluster
    create_iam_roles
    
    # 애플리케이션 빌드 및 배포
    build_and_deploy_frontend
    build_and_deploy_backend
    deploy_ecs_services
    
    # 배포 상태 확인
    check_deployment_status
    
    log_success "모든 배포 작업이 완료되었습니다!"
}

# 스크립트 실행
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 