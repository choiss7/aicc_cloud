"""
AI 챗봇 시나리오 관리 모듈
대화 흐름 제어 및 시나리오 기반 응답 처리
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import uuid

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationState(Enum):
    """대화 상태 열거형"""
    INITIAL = "initial"
    GREETING = "greeting"
    INQUIRY = "inquiry"
    PROCESSING = "processing"
    WAITING_INPUT = "waiting_input"
    ESCALATION = "escalation"
    CLOSING = "closing"
    ENDED = "ended"

class ScenarioType(Enum):
    """시나리오 타입 열거형"""
    BANKING = "banking"
    INSURANCE = "insurance"
    TELECOM = "telecom"
    GENERAL = "general"
    EMERGENCY = "emergency"

class ChatbotScenario:
    """
    챗봇 시나리오 관리 클래스
    """
    
    def __init__(self):
        """시나리오 관리자 초기화"""
        self.scenarios = self._load_scenarios()
        self.active_sessions = {}
        
    def _load_scenarios(self) -> Dict:
        """
        시나리오 데이터 로드
        
        Returns:
            시나리오 딕셔너리
        """
        return {
            ScenarioType.BANKING.value: {
                "name": "은행 업무 시나리오",
                "flows": {
                    "account_inquiry": {
                        "name": "계좌 조회",
                        "steps": [
                            {
                                "id": "auth_request",
                                "message": "계좌 조회를 위해 본인 인증이 필요합니다. 주민등록번호 뒷자리를 입력해 주세요.",
                                "input_type": "secure_text",
                                "validation": "resident_number",
                                "next_step": "account_select"
                            },
                            {
                                "id": "account_select",
                                "message": "조회하실 계좌를 선택해 주세요.",
                                "input_type": "selection",
                                "options": ["예금계좌", "적금계좌", "대출계좌", "전체계좌"],
                                "next_step": "show_balance"
                            },
                            {
                                "id": "show_balance",
                                "message": "계좌 잔액을 조회했습니다.",
                                "input_type": "display",
                                "next_step": "additional_service"
                            }
                        ]
                    },
                    "transfer": {
                        "name": "계좌 이체",
                        "steps": [
                            {
                                "id": "auth_request",
                                "message": "계좌 이체를 위해 본인 인증이 필요합니다.",
                                "input_type": "secure_text",
                                "validation": "resident_number",
                                "next_step": "transfer_info"
                            },
                            {
                                "id": "transfer_info",
                                "message": "이체 정보를 입력해 주세요.",
                                "input_type": "form",
                                "fields": ["받는계좌", "이체금액", "받는분성함"],
                                "next_step": "transfer_confirm"
                            },
                            {
                                "id": "transfer_confirm",
                                "message": "이체 정보를 확인해 주세요.",
                                "input_type": "confirmation",
                                "next_step": "transfer_complete"
                            }
                        ]
                    }
                }
            },
            ScenarioType.INSURANCE.value: {
                "name": "보험 업무 시나리오",
                "flows": {
                    "claim_report": {
                        "name": "보험금 청구",
                        "steps": [
                            {
                                "id": "incident_type",
                                "message": "어떤 종류의 사고인지 선택해 주세요.",
                                "input_type": "selection",
                                "options": ["교통사고", "화재", "도난", "질병", "기타"],
                                "next_step": "incident_details"
                            },
                            {
                                "id": "incident_details",
                                "message": "사고 상세 내용을 입력해 주세요.",
                                "input_type": "text",
                                "next_step": "document_upload"
                            },
                            {
                                "id": "document_upload",
                                "message": "관련 서류를 업로드해 주세요.",
                                "input_type": "file_upload",
                                "next_step": "claim_submit"
                            }
                        ]
                    }
                }
            },
            ScenarioType.GENERAL.value: {
                "name": "일반 상담 시나리오",
                "flows": {
                    "faq": {
                        "name": "자주 묻는 질문",
                        "steps": [
                            {
                                "id": "category_select",
                                "message": "어떤 분야에 대해 궁금하신가요?",
                                "input_type": "selection",
                                "options": ["서비스 이용", "요금 안내", "기술 지원", "기타"],
                                "next_step": "show_faq"
                            },
                            {
                                "id": "show_faq",
                                "message": "관련 FAQ를 보여드리겠습니다.",
                                "input_type": "display",
                                "next_step": "satisfaction_check"
                            }
                        ]
                    }
                }
            }
        }
    
    def create_session(self, user_id: str, scenario_type: str = None) -> str:
        """
        새로운 대화 세션 생성
        
        Args:
            user_id: 사용자 ID
            scenario_type: 시나리오 타입
            
        Returns:
            세션 ID
        """
        session_id = str(uuid.uuid4())
        
        self.active_sessions[session_id] = {
            'user_id': user_id,
            'session_id': session_id,
            'scenario_type': scenario_type or ScenarioType.GENERAL.value,
            'current_flow': None,
            'current_step': None,
            'state': ConversationState.INITIAL,
            'context': {},
            'history': [],
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        logger.info(f"새 세션 생성: {session_id} (사용자: {user_id})")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        세션 정보 조회
        
        Args:
            session_id: 세션 ID
            
        Returns:
            세션 정보
        """
        return self.active_sessions.get(session_id)
    
    def update_session(self, session_id: str, updates: Dict) -> bool:
        """
        세션 정보 업데이트
        
        Args:
            session_id: 세션 ID
            updates: 업데이트할 정보
            
        Returns:
            업데이트 성공 여부
        """
        if session_id not in self.active_sessions:
            return False
        
        self.active_sessions[session_id].update(updates)
        self.active_sessions[session_id]['updated_at'] = datetime.now().isoformat()
        return True
    
    def start_flow(self, session_id: str, flow_name: str) -> Dict:
        """
        특정 플로우 시작
        
        Args:
            session_id: 세션 ID
            flow_name: 플로우 이름
            
        Returns:
            첫 번째 단계 정보
        """
        session = self.get_session(session_id)
        if not session:
            return {"error": "세션을 찾을 수 없습니다."}
        
        scenario_type = session['scenario_type']
        scenario = self.scenarios.get(scenario_type)
        
        if not scenario or flow_name not in scenario['flows']:
            return {"error": "플로우를 찾을 수 없습니다."}
        
        flow = scenario['flows'][flow_name]
        first_step = flow['steps'][0]
        
        # 세션 업데이트
        self.update_session(session_id, {
            'current_flow': flow_name,
            'current_step': first_step['id'],
            'state': ConversationState.PROCESSING
        })
        
        return {
            'step_id': first_step['id'],
            'message': first_step['message'],
            'input_type': first_step['input_type'],
            'options': first_step.get('options', []),
            'fields': first_step.get('fields', [])
        }
    
    def process_step(self, session_id: str, user_input: Any) -> Dict:
        """
        현재 단계 처리 및 다음 단계로 진행
        
        Args:
            session_id: 세션 ID
            user_input: 사용자 입력
            
        Returns:
            다음 단계 정보 또는 완료 메시지
        """
        session = self.get_session(session_id)
        if not session:
            return {"error": "세션을 찾을 수 없습니다."}
        
        current_flow = session['current_flow']
        current_step_id = session['current_step']
        
        if not current_flow or not current_step_id:
            return {"error": "진행 중인 플로우가 없습니다."}
        
        # 현재 단계 정보 가져오기
        scenario = self.scenarios[session['scenario_type']]
        flow = scenario['flows'][current_flow]
        current_step = None
        
        for step in flow['steps']:
            if step['id'] == current_step_id:
                current_step = step
                break
        
        if not current_step:
            return {"error": "현재 단계를 찾을 수 없습니다."}
        
        # 입력 검증
        validation_result = self._validate_input(current_step, user_input)
        if not validation_result['valid']:
            return {
                'error': validation_result['message'],
                'retry': True
            }
        
        # 컨텍스트에 입력 저장
        session['context'][current_step_id] = user_input
        
        # 히스토리에 추가
        session['history'].append({
            'step_id': current_step_id,
            'user_input': user_input,
            'timestamp': datetime.now().isoformat()
        })
        
        # 다음 단계 찾기
        next_step_id = current_step.get('next_step')
        if not next_step_id:
            # 플로우 완료
            self.update_session(session_id, {
                'current_flow': None,
                'current_step': None,
                'state': ConversationState.CLOSING
            })
            return {
                'completed': True,
                'message': "요청이 완료되었습니다. 추가로 도움이 필요하시면 말씀해 주세요."
            }
        
        # 다음 단계 찾기
        next_step = None
        for step in flow['steps']:
            if step['id'] == next_step_id:
                next_step = step
                break
        
        if not next_step:
            return {"error": "다음 단계를 찾을 수 없습니다."}
        
        # 세션 업데이트
        self.update_session(session_id, {
            'current_step': next_step['id']
        })
        
        return {
            'step_id': next_step['id'],
            'message': next_step['message'],
            'input_type': next_step['input_type'],
            'options': next_step.get('options', []),
            'fields': next_step.get('fields', [])
        }
    
    def _validate_input(self, step: Dict, user_input: Any) -> Dict:
        """
        사용자 입력 검증
        
        Args:
            step: 현재 단계 정보
            user_input: 사용자 입력
            
        Returns:
            검증 결과
        """
        input_type = step['input_type']
        
        if input_type == 'selection':
            options = step.get('options', [])
            if user_input not in options:
                return {
                    'valid': False,
                    'message': f"다음 중에서 선택해 주세요: {', '.join(options)}"
                }
        
        elif input_type == 'secure_text':
            validation = step.get('validation')
            if validation == 'resident_number':
                if not user_input or len(user_input) != 7:
                    return {
                        'valid': False,
                        'message': "주민등록번호 뒷자리 7자리를 정확히 입력해 주세요."
                    }
        
        elif input_type == 'text':
            if not user_input or len(user_input.strip()) == 0:
                return {
                    'valid': False,
                    'message': "내용을 입력해 주세요."
                }
        
        return {'valid': True}
    
    def get_available_flows(self, scenario_type: str) -> List[Dict]:
        """
        사용 가능한 플로우 목록 조회
        
        Args:
            scenario_type: 시나리오 타입
            
        Returns:
            플로우 목록
        """
        scenario = self.scenarios.get(scenario_type)
        if not scenario:
            return []
        
        flows = []
        for flow_id, flow_data in scenario['flows'].items():
            flows.append({
                'id': flow_id,
                'name': flow_data['name'],
                'description': flow_data.get('description', '')
            })
        
        return flows
    
    def should_escalate(self, session_id: str) -> bool:
        """
        상담원 전환 필요 여부 판단
        
        Args:
            session_id: 세션 ID
            
        Returns:
            전환 필요 여부
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        # 에스컬레이션 조건 확인
        history_count = len(session['history'])
        
        # 10번 이상 대화했는데 해결되지 않은 경우
        if history_count >= 10 and session['state'] != ConversationState.CLOSING:
            return True
        
        # 특정 키워드가 포함된 경우
        escalation_keywords = ['상담원', '사람', '직원', '담당자', '불만', '화나']
        for history_item in session['history'][-3:]:  # 최근 3개 입력 확인
            user_input = str(history_item.get('user_input', '')).lower()
            if any(keyword in user_input for keyword in escalation_keywords):
                return True
        
        return False
    
    def end_session(self, session_id: str) -> bool:
        """
        세션 종료
        
        Args:
            session_id: 세션 ID
            
        Returns:
            종료 성공 여부
        """
        if session_id in self.active_sessions:
            self.active_sessions[session_id]['state'] = ConversationState.ENDED
            self.active_sessions[session_id]['ended_at'] = datetime.now().isoformat()
            logger.info(f"세션 종료: {session_id}")
            return True
        return False

# 사용 예시
if __name__ == "__main__":
    scenario_manager = ChatbotScenario()
    
    # 세션 생성
    session_id = scenario_manager.create_session("user123", ScenarioType.BANKING.value)
    print(f"세션 생성: {session_id}")
    
    # 계좌 조회 플로우 시작
    result = scenario_manager.start_flow(session_id, "account_inquiry")
    print(f"첫 번째 단계: {result}")
    
    # 사용자 입력 처리
    result = scenario_manager.process_step(session_id, "1234567")
    print(f"두 번째 단계: {result}")
    
    # 계좌 선택
    result = scenario_manager.process_step(session_id, "예금계좌")
    print(f"세 번째 단계: {result}")
    
    # 세션 정보 확인
    session_info = scenario_manager.get_session(session_id)
    print(f"세션 정보: {session_info}") 