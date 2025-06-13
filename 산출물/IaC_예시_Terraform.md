# Terraform IaC 예시 템플릿

## 1. 개요
- 본 템플릿은 Terraform을 활용하여 AICC 인프라의 주요 리소스(VPC, 서브넷, 보안그룹, EC2, S3, IAM 등)를 코드로 자동 배포하는 예시입니다.

## 2. Terraform 예시 코드
```hcl
provider "aws" {
  region = "ap-northeast-2"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  enable_dns_support = true
  enable_dns_hostnames = true
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
  map_public_ip_on_launch = true
}

resource "aws_security_group" "web_sg" {
  name        = "aicc-web-sg"
  description = "AICC 웹 서비스용 SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web_sg.id]
}

resource "aws_s3_bucket" "aicc_bucket" {
  bucket = "aicc-sample-bucket"
}

resource "aws_iam_role" "ec2_role" {
  name = "aicc-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}
```

## 3. 주요 파라미터/설정 설명
- **provider**: AWS 리전 지정
- **VPC/Subnet**: 네트워크 분리 및 IP 대역 설정
- **Security Group**: 인바운드/아웃바운드 트래픽 제어
- **EC2**: 챗봇/웹서버 등 서비스 배포용 인스턴스
- **S3**: 파일 저장(녹취, 로그 등)
- **IAM Role**: EC2 등 리소스의 권한 관리

## 4. 실무 팁
- 변수(variable), output, module을 활용해 재사용성/유지보수성 강화
- Terraform Cloud/Backend로 상태 관리 및 협업
- 실제 운영 환경에서는 리소스 태깅, 버전 관리, 정책 적용 필수 