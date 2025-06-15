# AWS Connect Lambda 함수

이 디렉토리에는 AWS Connect 콜센터와 연동되는 Lambda 함수들이 포함되어 있습니다.

## 주요 함수

### chatbot_handler.py
- AWS Connect Contact Flow와 연동되는 메인 Lambda 함수
- 고객 문의를 처리하고 적절한 응답을 생성
- 다양한 요청 타입 처리: 채팅, 음성, 에스컬레이션, 영업시간 확인, 대기열 상태 확인

## 배포 방법

### 1. Lambda 함수 생성
```bash
aws lambda create-function \
  --function-name aicc-chatbot-handler \
  --runtime python3.9 \
  --handler chatbot_handler.lambda_handler \
  --role arn:aws:iam::123456789012:role/lambda-connect-role \
  --zip-file fileb://chatbot_handler.zip
```

### 2. 환경 변수 설정
```bash
aws lambda update-function-configuration \
  --function-name aicc-chatbot-handler \
  --environment "Variables={CONVERSATIONS_TABLE=aicc-conversations,CHATBOT_RESPONSES_BUCKET=aicc-chatbot-responses}"
```

### 3. Connect 인스턴스에 Lambda 함수 연결
```bash
aws connect associate-lambda-function \
  --instance-id your-instance-id \
  --function-arn arn:aws:lambda:ap-northeast-2:123456789012:function:aicc-chatbot-handler
```

## 테스트 방법

### 로컬 테스트
```bash
python -c "import chatbot_handler; import json; event = json.loads(open('test_event.json').read()); print(chatbot_handler.lambda_handler(event, None))"
```

### AWS Lambda 콘솔에서 테스트
테스트 이벤트 예시:
```json
{
  "Details": {
    "ContactData": {
      "ContactId": "12345678-1234-1234-1234-123456789012",
      "CustomerEndpoint": {
        "Address": "+821012345678",
        "Type": "TELEPHONE_NUMBER"
      }
    },
    "Parameters": {
      "requestType": "chat",
      "userInput": "안녕하세요",
      "intentName": "Greeting",
      "sessionAttributes": {}
    }
  }
}
``` 