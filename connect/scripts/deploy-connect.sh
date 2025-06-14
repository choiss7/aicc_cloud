#!/bin/bash

# AWS Connect 인스턴스 배포 스크립트
# 작성자: AICC Cloud Team
# 버전: 1.0

set -e

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
STACK_NAME="aicc-connect-instance"
TEMPLATE_FILE="cloudformation/connect-instance.yaml"
REGION="ap-northeast-2"
INSTANCE_ALIAS="aicc-prod"

# 환경 변수 확인
check_prerequisites() {
    log_info "사전 요구사항 확인 중..."
    
    # AWS CLI 설치 확인
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI가 설치되지 않았습니다."
        exit 1
    fi
    
    # AWS 자격 증명 확인
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS 자격 증명이 설정되지 않았습니다."
        exit 1
    fi
    
    # CloudFormation 템플릿 파일 확인
    if [ ! -f "$TEMPLATE_FILE" ]; then
        log_error "CloudFormation 템플릿 파일을 찾을 수 없습니다: $TEMPLATE_FILE"
        exit 1
    fi
    
    log_success "사전 요구사항 확인 완료"
}

# CloudFormation 스택 배포
deploy_stack() {
    log_info "CloudFormation 스택 배포 시작..."
    
    # 스택 존재 여부 확인
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null; then
        log_warning "스택이 이미 존재합니다. 업데이트를 진행합니다."
        
        aws cloudformation update-stack \
            --stack-name "$STACK_NAME" \
            --template-body file://"$TEMPLATE_FILE" \
            --parameters ParameterKey=InstanceAlias,ParameterValue="$INSTANCE_ALIAS" \
            --capabilities CAPABILITY_IAM \
            --region "$REGION"
            
        log_info "스택 업데이트 대기 중..."
        aws cloudformation wait stack-update-complete \
            --stack-name "$STACK_NAME" \
            --region "$REGION"
    else
        log_info "새 스택을 생성합니다."
        
        aws cloudformation create-stack \
            --stack-name "$STACK_NAME" \
            --template-body file://"$TEMPLATE_FILE" \
            --parameters ParameterKey=InstanceAlias,ParameterValue="$INSTANCE_ALIAS" \
            --capabilities CAPABILITY_IAM \
            --region "$REGION"
            
        log_info "스택 생성 대기 중..."
        aws cloudformation wait stack-create-complete \
            --stack-name "$STACK_NAME" \
            --region "$REGION"
    fi
    
    log_success "CloudFormation 스택 배포 완료"
}

# 스택 출력 값 표시
show_outputs() {
    log_info "스택 출력 값 조회 중..."
    
    outputs=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs' \
        --output table)
    
    echo "$outputs"
}

# Contact Flow 배포
deploy_contact_flows() {
    log_info "Contact Flow 배포 시작..."
    
    # Connect 인스턴스 ID 가져오기
    INSTANCE_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ConnectInstanceId`].OutputValue' \
        --output text)
    
    if [ -z "$INSTANCE_ID" ]; then
        log_error "Connect 인스턴스 ID를 가져올 수 없습니다."
        exit 1
    fi
    
    log_info "Connect 인스턴스 ID: $INSTANCE_ID"
    
    # Contact Flow 파일들 배포
    FLOWS_DIR="contact-flows"
    
    if [ -d "$FLOWS_DIR" ]; then
        for flow_file in "$FLOWS_DIR"/*.json; do
            if [ -f "$flow_file" ]; then
                flow_name=$(basename "$flow_file" .json)
                
                log_info "Contact Flow 배포 중: $flow_name"
                
                # Contact Flow 내용에서 인스턴스 ID 교체
                temp_file=$(mktemp)
                sed "s/12345678-1234-1234-1234-123456789012/$INSTANCE_ID/g" "$flow_file" > "$temp_file"
                
                aws connect create-contact-flow \
                    --instance-id "$INSTANCE_ID" \
                    --name "$flow_name" \
                    --type CONTACT_FLOW \
                    --content file://"$temp_file" \
                    --region "$REGION" || log_warning "Contact Flow 생성 실패: $flow_name"
                
                rm "$temp_file"
                log_success "Contact Flow 배포 완료: $flow_name"
            fi
        done
    else
        log_warning "Contact Flow 디렉토리를 찾을 수 없습니다: $FLOWS_DIR"
    fi
}

# 전화번호 할당
assign_phone_number() {
    log_info "전화번호 할당 시작..."
    
    # Connect 인스턴스 ID 가져오기
    INSTANCE_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ConnectInstanceId`].OutputValue' \
        --output text)
    
    # 사용 가능한 전화번호 검색
    available_numbers=$(aws connect search-available-phone-numbers \
        --target-arn "arn:aws:connect:$REGION:$(aws sts get-caller-identity --query Account --output text):instance/$INSTANCE_ID" \
        --phone-number-country-code KR \
        --phone-number-type TOLL_FREE \
        --region "$REGION" \
        --query 'AvailableNumbersList[0].PhoneNumber' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$available_numbers" ] && [ "$available_numbers" != "None" ]; then
        log_info "전화번호 할당 중: $available_numbers"
        
        aws connect claim-phone-number \
            --target-arn "arn:aws:connect:$REGION:$(aws sts get-caller-identity --query Account --output text):instance/$INSTANCE_ID" \
            --phone-number "$available_numbers" \
            --region "$REGION"
            
        log_success "전화번호 할당 완료: $available_numbers"
    else
        log_warning "사용 가능한 전화번호가 없습니다. 수동으로 할당해 주세요."
    fi
}

# 배포 상태 확인
check_deployment_status() {
    log_info "배포 상태 확인 중..."
    
    # Connect 인스턴스 상태 확인
    INSTANCE_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ConnectInstanceId`].OutputValue' \
        --output text)
    
    instance_status=$(aws connect describe-instance \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'Instance.InstanceStatus' \
        --output text)
    
    log_info "Connect 인스턴스 상태: $instance_status"
    
    if [ "$instance_status" = "ACTIVE" ]; then
        log_success "Connect 인스턴스가 활성 상태입니다."
        
        # 인스턴스 URL 표시
        instance_url="https://$INSTANCE_ALIAS.my.connect.aws/connect/home"
        log_info "Connect 관리 콘솔 URL: $instance_url"
    else
        log_warning "Connect 인스턴스가 아직 활성화되지 않았습니다."
    fi
}

# 정리 함수
cleanup() {
    log_info "정리 작업 수행 중..."
    # 임시 파일 정리 등
}

# 메인 함수
main() {
    log_info "=== AWS Connect 인스턴스 배포 시작 ==="
    
    # 트랩 설정 (스크립트 종료 시 정리 작업 수행)
    trap cleanup EXIT
    
    # 사전 요구사항 확인
    check_prerequisites
    
    # CloudFormation 스택 배포
    deploy_stack
    
    # 스택 출력 값 표시
    show_outputs
    
    # Contact Flow 배포
    deploy_contact_flows
    
    # 전화번호 할당 (선택사항)
    read -p "전화번호를 자동으로 할당하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        assign_phone_number
    fi
    
    # 배포 상태 확인
    check_deployment_status
    
    log_success "=== AWS Connect 인스턴스 배포 완료 ==="
    log_info "다음 단계:"
    log_info "1. Connect 관리 콘솔에 로그인하여 설정을 확인하세요."
    log_info "2. 상담원 계정을 생성하세요."
    log_info "3. Contact Flow를 테스트하세요."
    log_info "4. 전화번호를 Contact Flow에 연결하세요."
}

# 도움말 표시
show_help() {
    echo "사용법: $0 [옵션]"
    echo ""
    echo "옵션:"
    echo "  -h, --help          이 도움말을 표시합니다"
    echo "  -s, --stack-name    CloudFormation 스택 이름 (기본값: $STACK_NAME)"
    echo "  -r, --region        AWS 리전 (기본값: $REGION)"
    echo "  -a, --alias         Connect 인스턴스 별칭 (기본값: $INSTANCE_ALIAS)"
    echo ""
    echo "예시:"
    echo "  $0"
    echo "  $0 --stack-name my-connect-stack --region us-east-1"
}

# 명령행 인수 처리
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -a|--alias)
            INSTANCE_ALIAS="$2"
            shift 2
            ;;
        *)
            log_error "알 수 없는 옵션: $1"
            show_help
            exit 1
            ;;
    esac
done

# 메인 함수 실행
main 