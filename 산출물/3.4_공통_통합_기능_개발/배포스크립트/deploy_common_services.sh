#!/bin/bash

# AICC 공통/통합 기능 배포 스크립트
# 모니터링, 녹취/저장, 외부 연동, 인증/권한 관리 서비스 배포

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 설정 변수
PROJECT_NAME="aicc-common-services"
AWS_REGION="ap-northeast-2"
ECR_REPOSITORY_PREFIX="aicc"
ECS_CLUSTER_NAME="aicc-cluster"
VPC_NAME="aicc-vpc"

# 서비스 목록
SERVICES=("monitoring" "recording" "integration" "auth")

# 환경 변수 확인
check_prerequisites() {
    log_step "사전 요구사항 확인 중..."
    
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
    
    log_info "사전 요구사항 확인 완료"
}

# ECR 리포지토리 생성
create_ecr_repositories() {
    log_step "ECR 리포지토리 생성 중..."
    
    for service in "${SERVICES[@]}"; do
        REPO_NAME="${ECR_REPOSITORY_PREFIX}-${service}"
        
        if aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION &> /dev/null; then
            log_info "ECR 리포지토리 $REPO_NAME 이미 존재"
        else
            aws ecr create-repository \
                --repository-name $REPO_NAME \
                --region $AWS_REGION \
                --image-scanning-configuration scanOnPush=true \
                --encryption-configuration encryptionType=AES256
            
            log_info "ECR 리포지토리 $REPO_NAME 생성 완료"
        fi
    done
}

# Docker 이미지 빌드 및 푸시
build_and_push_images() {
    log_step "Docker 이미지 빌드 및 푸시 중..."
    
    # ECR 로그인
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_BASE_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    
    for service in "${SERVICES[@]}"; do
        log_info "빌드 중: $service 서비스"
        
        REPO_NAME="${ECR_REPOSITORY_PREFIX}-${service}"
        IMAGE_TAG="latest"
        FULL_IMAGE_NAME="$ECR_BASE_URI/$REPO_NAME:$IMAGE_TAG"
        
        # Dockerfile 빌드
        docker build -t $REPO_NAME:$IMAGE_TAG -f Dockerfile.$service .
        
        # 태그 지정
        docker tag $REPO_NAME:$IMAGE_TAG $FULL_IMAGE_NAME
        
        # ECR에 푸시
        docker push $FULL_IMAGE_NAME
        
        log_info "$service 이미지 푸시 완료: $FULL_IMAGE_NAME"
    done
}

# VPC 및 네트워킹 설정
setup_networking() {
    log_step "VPC 및 네트워킹 설정 중..."
    
    # VPC 존재 확인
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=$VPC_NAME" --query 'Vpcs[0].VpcId' --output text --region $AWS_REGION)
    
    if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
        log_info "VPC 생성 중..."
        
        # VPC 생성
        VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --region $AWS_REGION --query 'Vpc.VpcId' --output text)
        aws ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=$VPC_NAME --region $AWS_REGION
        
        # 인터넷 게이트웨이 생성
        IGW_ID=$(aws ec2 create-internet-gateway --region $AWS_REGION --query 'InternetGateway.InternetGatewayId' --output text)
        aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID --region $AWS_REGION
        aws ec2 create-tags --resources $IGW_ID --tags Key=Name,Value=${VPC_NAME}-igw --region $AWS_REGION
        
        # 퍼블릭 서브넷 생성
        SUBNET1_ID=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone ${AWS_REGION}a --region $AWS_REGION --query 'Subnet.SubnetId' --output text)
        SUBNET2_ID=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 --availability-zone ${AWS_REGION}c --region $AWS_REGION --query 'Subnet.SubnetId' --output text)
        
        aws ec2 create-tags --resources $SUBNET1_ID --tags Key=Name,Value=${VPC_NAME}-public-1 --region $AWS_REGION
        aws ec2 create-tags --resources $SUBNET2_ID --tags Key=Name,Value=${VPC_NAME}-public-2 --region $AWS_REGION
        
        # 라우팅 테이블 설정
        ROUTE_TABLE_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID --region $AWS_REGION --query 'RouteTable.RouteTableId' --output text)
        aws ec2 create-route --route-table-id $ROUTE_TABLE_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID --region $AWS_REGION
        aws ec2 associate-route-table --subnet-id $SUBNET1_ID --route-table-id $ROUTE_TABLE_ID --region $AWS_REGION
        aws ec2 associate-route-table --subnet-id $SUBNET2_ID --route-table-id $ROUTE_TABLE_ID --region $AWS_REGION
        
        log_info "VPC 생성 완료: $VPC_ID"
    else
        log_info "기존 VPC 사용: $VPC_ID"
    fi
    
    # 서브넷 ID 조회
    SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[].SubnetId' --output text --region $AWS_REGION)
    export VPC_ID SUBNET_IDS
}

# 보안 그룹 생성
create_security_groups() {
    log_step "보안 그룹 생성 중..."
    
    # 공통 서비스용 보안 그룹
    SG_NAME="${PROJECT_NAME}-sg"
    SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text --region $AWS_REGION)
    
    if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
        SG_ID=$(aws ec2 create-security-group --group-name $SG_NAME --description "Security group for AICC common services" --vpc-id $VPC_ID --region $AWS_REGION --query 'GroupId' --output text)
        
        # 인바운드 규칙 추가
        aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $AWS_REGION
        aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $AWS_REGION
        aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8000-8010 --cidr 10.0.0.0/16 --region $AWS_REGION
        
        log_info "보안 그룹 생성 완료: $SG_ID"
    else
        log_info "기존 보안 그룹 사용: $SG_ID"
    fi
    
    export SECURITY_GROUP_ID=$SG_ID
}

# RDS 인스턴스 생성
create_rds_instance() {
    log_step "RDS 인스턴스 생성 중..."
    
    DB_INSTANCE_ID="${PROJECT_NAME}-db"
    
    # RDS 인스턴스 존재 확인
    if aws rds describe-db-instances --db-instance-identifier $DB_INSTANCE_ID --region $AWS_REGION &> /dev/null; then
        log_info "RDS 인스턴스 이미 존재: $DB_INSTANCE_ID"
    else
        # DB 서브넷 그룹 생성
        DB_SUBNET_GROUP_NAME="${PROJECT_NAME}-db-subnet-group"
        
        if ! aws rds describe-db-subnet-groups --db-subnet-group-name $DB_SUBNET_GROUP_NAME --region $AWS_REGION &> /dev/null; then
            aws rds create-db-subnet-group \
                --db-subnet-group-name $DB_SUBNET_GROUP_NAME \
                --db-subnet-group-description "DB subnet group for AICC common services" \
                --subnet-ids $SUBNET_IDS \
                --region $AWS_REGION
        fi
        
        # RDS 인스턴스 생성
        aws rds create-db-instance \
            --db-instance-identifier $DB_INSTANCE_ID \
            --db-instance-class db.t3.micro \
            --engine postgres \
            --engine-version 13.7 \
            --master-username aiccadmin \
            --master-user-password $(openssl rand -base64 32) \
            --allocated-storage 20 \
            --vpc-security-group-ids $SECURITY_GROUP_ID \
            --db-subnet-group-name $DB_SUBNET_GROUP_NAME \
            --backup-retention-period 7 \
            --storage-encrypted \
            --region $AWS_REGION
        
        log_info "RDS 인스턴스 생성 시작: $DB_INSTANCE_ID"
        log_warn "RDS 인스턴스 생성 완료까지 약 10-15분 소요됩니다."
    fi
}

# ElastiCache Redis 클러스터 생성
create_redis_cluster() {
    log_step "ElastiCache Redis 클러스터 생성 중..."
    
    REDIS_CLUSTER_ID="${PROJECT_NAME}-redis"
    
    # Redis 클러스터 존재 확인
    if aws elasticache describe-cache-clusters --cache-cluster-id $REDIS_CLUSTER_ID --region $AWS_REGION &> /dev/null; then
        log_info "Redis 클러스터 이미 존재: $REDIS_CLUSTER_ID"
    else
        # 캐시 서브넷 그룹 생성
        CACHE_SUBNET_GROUP_NAME="${PROJECT_NAME}-cache-subnet-group"
        
        if ! aws elasticache describe-cache-subnet-groups --cache-subnet-group-name $CACHE_SUBNET_GROUP_NAME --region $AWS_REGION &> /dev/null; then
            aws elasticache create-cache-subnet-group \
                --cache-subnet-group-name $CACHE_SUBNET_GROUP_NAME \
                --cache-subnet-group-description "Cache subnet group for AICC common services" \
                --subnet-ids $SUBNET_IDS \
                --region $AWS_REGION
        fi
        
        # Redis 클러스터 생성
        aws elasticache create-cache-cluster \
            --cache-cluster-id $REDIS_CLUSTER_ID \
            --cache-node-type cache.t3.micro \
            --engine redis \
            --num-cache-nodes 1 \
            --cache-subnet-group-name $CACHE_SUBNET_GROUP_NAME \
            --security-group-ids $SECURITY_GROUP_ID \
            --region $AWS_REGION
        
        log_info "Redis 클러스터 생성 시작: $REDIS_CLUSTER_ID"
    fi
}

# ECS 클러스터 생성
create_ecs_cluster() {
    log_step "ECS 클러스터 생성 중..."
    
    # ECS 클러스터 존재 확인
    if aws ecs describe-clusters --clusters $ECS_CLUSTER_NAME --region $AWS_REGION --query 'clusters[0].status' --output text | grep -q "ACTIVE"; then
        log_info "ECS 클러스터 이미 존재: $ECS_CLUSTER_NAME"
    else
        aws ecs create-cluster --cluster-name $ECS_CLUSTER_NAME --region $AWS_REGION
        log_info "ECS 클러스터 생성 완료: $ECS_CLUSTER_NAME"
    fi
}

# IAM 역할 생성
create_iam_roles() {
    log_step "IAM 역할 생성 중..."
    
    # ECS 태스크 실행 역할
    TASK_EXECUTION_ROLE_NAME="${PROJECT_NAME}-task-execution-role"
    
    if ! aws iam get-role --role-name $TASK_EXECUTION_ROLE_NAME &> /dev/null; then
        # 신뢰 정책 생성
        cat > task-execution-trust-policy.json << EOF
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
            --role-name $TASK_EXECUTION_ROLE_NAME \
            --assume-role-policy-document file://task-execution-trust-policy.json
        
        # 정책 연결
        aws iam attach-role-policy \
            --role-name $TASK_EXECUTION_ROLE_NAME \
            --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
        
        rm task-execution-trust-policy.json
        log_info "ECS 태스크 실행 역할 생성 완료"
    fi
    
    # ECS 태스크 역할
    TASK_ROLE_NAME="${PROJECT_NAME}-task-role"
    
    if ! aws iam get-role --role-name $TASK_ROLE_NAME &> /dev/null; then
        # 태스크 역할 생성
        aws iam create-role \
            --role-name $TASK_ROLE_NAME \
            --assume-role-policy-document file://task-execution-trust-policy.json
        
        # 커스텀 정책 생성
        cat > task-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::aicc-*",
        "arn:aws:s3:::aicc-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish",
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData",
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
EOF
        
        aws iam put-role-policy \
            --role-name $TASK_ROLE_NAME \
            --policy-name "${PROJECT_NAME}-task-policy" \
            --policy-document file://task-policy.json
        
        rm task-policy.json
        log_info "ECS 태스크 역할 생성 완료"
    fi
    
    # 역할 ARN 조회
    TASK_EXECUTION_ROLE_ARN=$(aws iam get-role --role-name $TASK_EXECUTION_ROLE_NAME --query 'Role.Arn' --output text)
    TASK_ROLE_ARN=$(aws iam get-role --role-name $TASK_ROLE_NAME --query 'Role.Arn' --output text)
    
    export TASK_EXECUTION_ROLE_ARN TASK_ROLE_ARN
}

# ECS 태스크 정의 생성
create_task_definitions() {
    log_step "ECS 태스크 정의 생성 중..."
    
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    ECR_BASE_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    
    for service in "${SERVICES[@]}"; do
        log_info "태스크 정의 생성 중: $service"
        
        TASK_DEFINITION_NAME="${PROJECT_NAME}-${service}"
        IMAGE_URI="$ECR_BASE_URI/${ECR_REPOSITORY_PREFIX}-${service}:latest"
        
        # 포트 매핑 설정
        case $service in
            "monitoring")
                CONTAINER_PORT=8000
                ;;
            "recording")
                CONTAINER_PORT=8001
                ;;
            "integration")
                CONTAINER_PORT=8002
                ;;
            "auth")
                CONTAINER_PORT=8003
                ;;
        esac
        
        # 태스크 정의 JSON 생성
        cat > task-definition-${service}.json << EOF
{
  "family": "$TASK_DEFINITION_NAME",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "$TASK_EXECUTION_ROLE_ARN",
  "taskRoleArn": "$TASK_ROLE_ARN",
  "containerDefinitions": [
    {
      "name": "$service",
      "image": "$IMAGE_URI",
      "portMappings": [
        {
          "containerPort": $CONTAINER_PORT,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AWS_DEFAULT_REGION",
          "value": "$AWS_REGION"
        },
        {
          "name": "SERVICE_NAME",
          "value": "$service"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/$TASK_DEFINITION_NAME",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "essential": true
    }
  ]
}
EOF
        
        # CloudWatch 로그 그룹 생성
        aws logs create-log-group --log-group-name "/ecs/$TASK_DEFINITION_NAME" --region $AWS_REGION 2>/dev/null || true
        
        # 태스크 정의 등록
        aws ecs register-task-definition \
            --cli-input-json file://task-definition-${service}.json \
            --region $AWS_REGION
        
        rm task-definition-${service}.json
        log_info "$service 태스크 정의 생성 완료"
    done
}

# ECS 서비스 생성
create_ecs_services() {
    log_step "ECS 서비스 생성 중..."
    
    for service in "${SERVICES[@]}"; do
        log_info "ECS 서비스 생성 중: $service"
        
        SERVICE_NAME="${PROJECT_NAME}-${service}"
        TASK_DEFINITION_NAME="${PROJECT_NAME}-${service}"
        
        # 서비스 존재 확인
        if aws ecs describe-services --cluster $ECS_CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION --query 'services[0].status' --output text | grep -q "ACTIVE"; then
            log_info "ECS 서비스 이미 존재: $SERVICE_NAME"
            continue
        fi
        
        # 서비스 생성
        aws ecs create-service \
            --cluster $ECS_CLUSTER_NAME \
            --service-name $SERVICE_NAME \
            --task-definition $TASK_DEFINITION_NAME \
            --desired-count 1 \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
            --region $AWS_REGION
        
        log_info "$service ECS 서비스 생성 완료"
    done
}

# S3 버킷 생성
create_s3_buckets() {
    log_step "S3 버킷 생성 중..."
    
    BUCKETS=("aicc-recordings" "aicc-backups" "aicc-logs")
    
    for bucket in "${BUCKETS[@]}"; do
        if aws s3api head-bucket --bucket $bucket --region $AWS_REGION 2>/dev/null; then
            log_info "S3 버킷 이미 존재: $bucket"
        else
            aws s3api create-bucket \
                --bucket $bucket \
                --region $AWS_REGION \
                --create-bucket-configuration LocationConstraint=$AWS_REGION
            
            # 버킷 암호화 설정
            aws s3api put-bucket-encryption \
                --bucket $bucket \
                --server-side-encryption-configuration '{
                    "Rules": [
                        {
                            "ApplyServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "AES256"
                            }
                        }
                    ]
                }'
            
            log_info "S3 버킷 생성 완료: $bucket"
        fi
    done
}

# SNS 토픽 생성
create_sns_topics() {
    log_step "SNS 토픽 생성 중..."
    
    TOPICS=("aicc-alerts" "aicc-notifications")
    
    for topic in "${TOPICS[@]}"; do
        if aws sns get-topic-attributes --topic-arn "arn:aws:sns:$AWS_REGION:$(aws sts get-caller-identity --query Account --output text):$topic" --region $AWS_REGION &> /dev/null; then
            log_info "SNS 토픽 이미 존재: $topic"
        else
            aws sns create-topic --name $topic --region $AWS_REGION
            log_info "SNS 토픽 생성 완료: $topic"
        fi
    done
}

# 배포 상태 확인
check_deployment_status() {
    log_step "배포 상태 확인 중..."
    
    for service in "${SERVICES[@]}"; do
        SERVICE_NAME="${PROJECT_NAME}-${service}"
        
        log_info "$service 서비스 상태 확인 중..."
        
        # 서비스 상태 확인
        RUNNING_COUNT=$(aws ecs describe-services \
            --cluster $ECS_CLUSTER_NAME \
            --services $SERVICE_NAME \
            --region $AWS_REGION \
            --query 'services[0].runningCount' \
            --output text)
        
        DESIRED_COUNT=$(aws ecs describe-services \
            --cluster $ECS_CLUSTER_NAME \
            --services $SERVICE_NAME \
            --region $AWS_REGION \
            --query 'services[0].desiredCount' \
            --output text)
        
        if [ "$RUNNING_COUNT" = "$DESIRED_COUNT" ] && [ "$RUNNING_COUNT" != "0" ]; then
            log_info "$service 서비스 정상 실행 중 ($RUNNING_COUNT/$DESIRED_COUNT)"
        else
            log_warn "$service 서비스 상태 확인 필요 ($RUNNING_COUNT/$DESIRED_COUNT)"
        fi
    done
}

# 정리 함수
cleanup() {
    log_step "임시 파일 정리 중..."
    rm -f task-definition-*.json
    rm -f task-execution-trust-policy.json
    rm -f task-policy.json
}

# 메인 실행 함수
main() {
    log_info "AICC 공통/통합 기능 배포 시작"
    
    check_prerequisites
    create_ecr_repositories
    build_and_push_images
    setup_networking
    create_security_groups
    create_rds_instance
    create_redis_cluster
    create_s3_buckets
    create_sns_topics
    create_ecs_cluster
    create_iam_roles
    create_task_definitions
    create_ecs_services
    
    log_info "배포 완료! 서비스 시작까지 몇 분 소요될 수 있습니다."
    
    sleep 30
    check_deployment_status
    
    cleanup
    
    log_info "AICC 공통/통합 기능 배포 완료"
    
    # 접속 정보 출력
    echo ""
    echo "=== 배포 정보 ==="
    echo "ECS 클러스터: $ECS_CLUSTER_NAME"
    echo "VPC ID: $VPC_ID"
    echo "보안 그룹 ID: $SECURITY_GROUP_ID"
    echo ""
    echo "서비스 엔드포인트:"
    for service in "${SERVICES[@]}"; do
        case $service in
            "monitoring")
                echo "- 모니터링 서비스: http://[ECS-IP]:8000"
                ;;
            "recording")
                echo "- 녹취/저장 서비스: http://[ECS-IP]:8001"
                ;;
            "integration")
                echo "- 외부 연동 서비스: http://[ECS-IP]:8002"
                ;;
            "auth")
                echo "- 인증/권한 서비스: http://[ECS-IP]:8003"
                ;;
        esac
    done
    echo ""
    echo "AWS 콘솔에서 ECS 서비스의 실제 IP 주소를 확인하세요."
}

# 스크립트 실행
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 