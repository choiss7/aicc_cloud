# AWS CloudFormation IaC 예시 템플릿

## 1. 개요
- 본 템플릿은 AWS CloudFormation을 활용하여 AICC 인프라의 주요 리소스(VPC, 서브넷, 보안그룹, EC2, S3, IAM 등)를 코드로 자동 배포하는 예시입니다.

## 2. CloudFormation 템플릿 예시 (YAML)
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: AICC 기본 인프라 예시
Resources:
  MyVPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: 10.0.0.0/16
      EnableDnsSupport: true
      EnableDnsHostnames: true
  MySubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref MyVPC
      CidrBlock: 10.0.1.0/24
      MapPublicIpOnLaunch: true
  MySecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: AICC SG
      VpcId: !Ref MyVPC
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0
  MyEC2:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-0abcdef1234567890
      InstanceType: t3.micro
      SubnetId: !Ref MySubnet
      SecurityGroupIds:
        - !Ref MySecurityGroup
  MyS3:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: aicc-sample-bucket
  MyIAMRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ec2.amazonaws.com
            Action: sts:AssumeRole
      Path: /
```

## 3. 주요 파라미터/설정 설명
- **VPC/Subnet**: 네트워크 분리 및 IP 대역 설정
- **SecurityGroup**: 인바운드/아웃바운드 트래픽 제어
- **EC2**: 챗봇/웹서버 등 서비스 배포용 인스턴스
- **S3**: 파일 저장(녹취, 로그 등)
- **IAM Role**: EC2 등 리소스의 권한 관리

## 4. 실무 팁
- 실제 운영 환경에서는 파라미터(Parameter)와 Output을 활용해 재사용성/유연성 강화
- CloudFormation StackSet, ChangeSet 등으로 대규모 운영 자동화 가능
- Terraform 등 타 IaC 도구도 유사하게 활용 가능 