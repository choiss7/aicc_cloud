"""
AWS Connect 콜센터용 시나리오 관리 모듈
"""
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import boto3

logger = logging.getLogger(__name__)

class ScenarioStatus(Enum):
    """시나리오 상태"""
    ACTIVE = "active"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"

@dataclass
class ScenarioStep:
    """시나리오 단계"""
    step_id: str
    step_name: str
    message: str
    input_type: str  # text, choice, number, date
    validation_rules: Dict[str, Any]
    next_steps: Dict[str, str]  # condition -> next_step_id
    escalation_triggers: List[str]

@dataclass
class ScenarioSession:
    """시나리오 세션 정보"""
    session_id: str
    scenario_id: str
    current_step: str
    status: ScenarioStatus
    collected_data: Dict[str, Any]
    retry_count: int
    created_at: str
    updated_at: str

class ChatbotScenario:
    """AWS Connect 챗봇 시나리오 관리자"""
    
    def __init__(self, dynamodb_table_name: str = "chatbot_scenarios"):
        self.dynamodb = boto3.resource('dynamodb')
        self.scenarios_table = self.dynamodb.Table(dynamodb_table_name)
        self.sessions_table = self.dynamodb.Table(f"{dynamodb_table_name}_sessions")
        
        # 내장 시나리오 정의
        self.built_in_scenarios = self._load_built_in_scenarios()
        
        # 재시도 제한
        self.max_retry_count = 3
    
    def start_scenario(self, session_id: str, scenario_id: str, 
                      initial_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        새로운 시나리오 시작
        
        Args:
            session_id: 세션 ID
            scenario_id: 시나리오 ID
            initial_data: 초기 데이터
            
        Returns:
            Dict: 시나리오 시작 결과
        """
        try:
            # 시나리오 정의 로드
            scenario_def = self._get_scenario_definition(scenario_id)
            if not scenario_def:
                return self._create_error_response(f"시나리오 '{scenario_id}'를 찾을 수 없습니다.")
            
            # 첫 번째 단계 가져오기
            first_step = self._get_first_step(scenario_def)
            
            # 세션 생성
            session = ScenarioSession(
                session_id=session_id,
                scenario_id=scenario_id,
                current_step=first_step['step_id'],
                status=ScenarioStatus.ACTIVE,
                collected_data=initial_data or {},
                retry_count=0,
                created_at=self._get_current_timestamp(),
                updated_at=self._get_current_timestamp()
            )
            
            # 세션 저장
            self._save_session(session)
            
            return {
                'success': True,
                'message': first_step['message'],
                'step_id': first_step['step_id'],
                'input_type': first_step['input_type'],
                'session_status': session.status.value
            }
            
        except Exception as e:
            logger.error(f"시나리오 시작 오류: {str(e)}")
            return self._create_error_response("시나리오를 시작할 수 없습니다.")
    
    def process_user_input(self, session_id: str, user_input: str) -> Dict[str, Any]:
        """
        사용자 입력 처리
        
        Args:
            session_id: 세션 ID
            user_input: 사용자 입력
            
        Returns:
            Dict: 처리 결과
        """
        try:
            # 세션 조회
            session = self._get_session(session_id)
            if not session:
                return self._create_error_response("세션을 찾을 수 없습니다.")
            
            # 시나리오 정의 로드
            scenario_def = self._get_scenario_definition(session.scenario_id)
            current_step = self._get_step_by_id(scenario_def, session.current_step)
            
            # 입력 검증
            validation_result = self._validate_input(current_step, user_input)
            if not validation_result['valid']:
                session.retry_count += 1
                self._save_session(session)
                
                if session.retry_count >= self.max_retry_count:
                    return self._escalate_scenario(session, "입력 검증 실패 반복")
                
                return {
                    'success': False,
                    'message': validation_result['error_message'],
                    'retry_count': session.retry_count,
                    'session_status': session.status.value
                }
            
            # 데이터 수집
            field_name = current_step.get('field_name', f"step_{current_step['step_id']}")
            session.collected_data[field_name] = validation_result['processed_value']
            session.retry_count = 0  # 성공 시 재시도 카운트 리셋
            
            # 다음 단계 결정
            next_step_result = self._determine_next_step(current_step, validation_result['processed_value'])
            
            if next_step_result['action'] == 'complete':
                session.status = ScenarioStatus.COMPLETED
                self._save_session(session)
                return self._complete_scenario(session)
            
            elif next_step_result['action'] == 'escalate':
                return self._escalate_scenario(session, next_step_result.get('reason', '조건 충족'))
            
            elif next_step_result['action'] == 'continue':
                next_step = self._get_step_by_id(scenario_def, next_step_result['next_step_id'])
                session.current_step = next_step['step_id']
                session.updated_at = self._get_current_timestamp()
                self._save_session(session)
                
                return {
                    'success': True,
                    'message': self._personalize_message(next_step['message'], session.collected_data),
                    'step_id': next_step['step_id'],
                    'input_type': next_step['input_type'],
                    'session_status': session.status.value,
                    'progress': self._calculate_progress(scenario_def, session.current_step)
                }
            
        except Exception as e:
            logger.error(f"사용자 입력 처리 오류: {str(e)}")
            return self._create_error_response("입력을 처리할 수 없습니다.")
    
    def get_scenario_status(self, session_id: str) -> Dict[str, Any]:
        """시나리오 상태 조회"""
        session = self._get_session(session_id)
        if not session:
            return {'success': False, 'message': '세션을 찾을 수 없습니다.'}
        
        return {
            'success': True,
            'session_id': session.session_id,
            'scenario_id': session.scenario_id,
            'current_step': session.current_step,
            'status': session.status.value,
            'collected_data': session.collected_data,
            'retry_count': session.retry_count
        }
    
    def cancel_scenario(self, session_id: str) -> Dict[str, Any]:
        """시나리오 취소"""
        session = self._get_session(session_id)
        if not session:
            return {'success': False, 'message': '세션을 찾을 수 없습니다.'}
        
        session.status = ScenarioStatus.CANCELLED
        session.updated_at = self._get_current_timestamp()
        self._save_session(session)
        
        return {
            'success': True,
            'message': '시나리오가 취소되었습니다.',
            'session_status': session.status.value
        }
    
    def _load_built_in_scenarios(self) -> Dict[str, Any]:
        """내장 시나리오 로드"""
        return {
            'product_inquiry': {
                'scenario_id': 'product_inquiry',
                'name': '상품 문의',
                'description': '상품에 대한 문의 처리',
                'steps': [
                    {
                        'step_id': 'ask_product_category',
                        'step_name': '상품 카테고리 확인',
                        'message': '어떤 종류의 상품에 대해 문의하시나요?\n1. 전자제품\n2. 의류\n3. 생활용품\n4. 기타',
                        'field_name': 'product_category',
                        'input_type': 'choice',
                        'validation_rules': {
                            'choices': ['1', '2', '3', '4', '전자제품', '의류', '생활용품', '기타']
                        },
                        'next_steps': {
                            'default': 'ask_specific_product'
                        }
                    },
                    {
                        'step_id': 'ask_specific_product',
                        'step_name': '구체적 상품명',
                        'message': '구체적으로 어떤 상품에 대해 문의하시나요?',
                        'field_name': 'product_name',
                        'input_type': 'text',
                        'validation_rules': {
                            'min_length': 2,
                            'max_length': 100
                        },
                        'next_steps': {
                            'default': 'ask_inquiry_type'
                        }
                    },
                    {
                        'step_id': 'ask_inquiry_type',
                        'step_name': '문의 유형',
                        'message': '어떤 내용을 문의하시나요?\n1. 가격 정보\n2. 재고 확인\n3. 상품 상세정보\n4. 기타',
                        'field_name': 'inquiry_type',
                        'input_type': 'choice',
                        'validation_rules': {
                            'choices': ['1', '2', '3', '4', '가격', '재고', '상세정보', '기타']
                        },
                        'next_steps': {
                            '1': 'complete',
                            '2': 'complete',
                            '3': 'complete',
                            '4': 'escalate'
                        }
                    }
                ]
            },
            'reservation': {
                'scenario_id': 'reservation',
                'name': '예약 접수',
                'description': '서비스 예약 처리',
                'steps': [
                    {
                        'step_id': 'ask_service_type',
                        'step_name': '서비스 유형',
                        'message': '어떤 서비스 예약을 원하시나요?\n1. 상담 예약\n2. 방문 서비스\n3. 전화 상담\n4. 기타',
                        'field_name': 'service_type',
                        'input_type': 'choice',
                        'validation_rules': {
                            'choices': ['1', '2', '3', '4']
                        },
                        'next_steps': {
                            'default': 'ask_preferred_date'
                        }
                    },
                    {
                        'step_id': 'ask_preferred_date',
                        'step_name': '희망 날짜',
                        'message': '희망하시는 날짜를 알려주세요. (예: 2024-01-15)',
                        'field_name': 'preferred_date',
                        'input_type': 'date',
                        'validation_rules': {
                            'date_format': 'YYYY-MM-DD',
                            'future_only': True
                        },
                        'next_steps': {
                            'default': 'ask_contact_info'
                        }
                    },
                    {
                        'step_id': 'ask_contact_info',
                        'step_name': '연락처',
                        'message': '연락 가능한 전화번호를 알려주세요.',
                        'field_name': 'contact_number',
                        'input_type': 'text',
                        'validation_rules': {
                            'pattern': r'^01[0-9]-[0-9]{4}-[0-9]{4}$',
                            'error_message': '올바른 전화번호 형식으로 입력해주세요. (예: 010-1234-5678)'
                        },
                        'next_steps': {
                            'default': 'complete'
                        }
                    }
                ]
            }
        }
    
    def _get_scenario_definition(self, scenario_id: str) -> Optional[Dict]:
        """시나리오 정의 조회"""
        # 우선 내장 시나리오 확인
        if scenario_id in self.built_in_scenarios:
            return self.built_in_scenarios[scenario_id]
        
        # DynamoDB에서 커스텀 시나리오 조회
        try:
            response = self.scenarios_table.get_item(Key={'scenario_id': scenario_id})
            return response.get('Item')
        except Exception as e:
            logger.error(f"시나리오 정의 조회 오류: {str(e)}")
            return None
    
    def _get_first_step(self, scenario_def: Dict) -> Dict:
        """첫 번째 단계 조회"""
        steps = scenario_def.get('steps', [])
        return steps[0] if steps else {}
    
    def _get_step_by_id(self, scenario_def: Dict, step_id: str) -> Optional[Dict]:
        """단계 ID로 단계 조회"""
        steps = scenario_def.get('steps', [])
        for step in steps:
            if step['step_id'] == step_id:
                return step
        return None
    
    def _validate_input(self, step: Dict, user_input: str) -> Dict[str, Any]:
        """입력 검증"""
        input_type = step.get('input_type', 'text')
        validation_rules = step.get('validation_rules', {})
        
        if input_type == 'choice':
            return self._validate_choice_input(user_input, validation_rules)
        elif input_type == 'date':
            return self._validate_date_input(user_input, validation_rules)
        elif input_type == 'number':
            return self._validate_number_input(user_input, validation_rules)
        else:
            return self._validate_text_input(user_input, validation_rules)
    
    def _validate_choice_input(self, user_input: str, rules: Dict) -> Dict[str, Any]:
        """선택형 입력 검증"""
        choices = rules.get('choices', [])
        if user_input.strip() in choices:
            return {'valid': True, 'processed_value': user_input.strip()}
        
        return {
            'valid': False,
            'error_message': f"올바른 선택지를 입력해주세요: {', '.join(choices)}"
        }
    
    def _validate_text_input(self, user_input: str, rules: Dict) -> Dict[str, Any]:
        """텍스트 입력 검증"""
        min_length = rules.get('min_length', 1)
        max_length = rules.get('max_length', 1000)
        pattern = rules.get('pattern')
        
        if len(user_input.strip()) < min_length:
            return {'valid': False, 'error_message': f'최소 {min_length}글자 이상 입력해주세요.'}
        
        if len(user_input.strip()) > max_length:
            return {'valid': False, 'error_message': f'최대 {max_length}글자까지 입력 가능합니다.'}
        
        if pattern:
            import re
            if not re.match(pattern, user_input.strip()):
                error_msg = rules.get('error_message', '올바른 형식으로 입력해주세요.')
                return {'valid': False, 'error_message': error_msg}
        
        return {'valid': True, 'processed_value': user_input.strip()}
    
    def _validate_date_input(self, user_input: str, rules: Dict) -> Dict[str, Any]:
        """날짜 입력 검증"""
        from datetime import datetime, date
        
        try:
            date_format = rules.get('date_format', '%Y-%m-%d')
            parsed_date = datetime.strptime(user_input.strip(), date_format).date()
            
            if rules.get('future_only', False) and parsed_date <= date.today():
                return {'valid': False, 'error_message': '오늘 이후의 날짜를 입력해주세요.'}
            
            return {'valid': True, 'processed_value': user_input.strip()}
            
        except ValueError:
            return {'valid': False, 'error_message': '올바른 날짜 형식으로 입력해주세요. (예: 2024-01-15)'}
    
    def _validate_number_input(self, user_input: str, rules: Dict) -> Dict[str, Any]:
        """숫자 입력 검증"""
        try:
            number = float(user_input.strip())
            
            min_value = rules.get('min_value')
            max_value = rules.get('max_value')
            
            if min_value is not None and number < min_value:
                return {'valid': False, 'error_message': f'{min_value} 이상의 값을 입력해주세요.'}
            
            if max_value is not None and number > max_value:
                return {'valid': False, 'error_message': f'{max_value} 이하의 값을 입력해주세요.'}
            
            return {'valid': True, 'processed_value': number}
            
        except ValueError:
            return {'valid': False, 'error_message': '올바른 숫자를 입력해주세요.'}
    
    def _determine_next_step(self, current_step: Dict, user_value: Any) -> Dict[str, Any]:
        """다음 단계 결정"""
        next_steps = current_step.get('next_steps', {})
        
        # 사용자 값에 따른 조건부 분기
        if str(user_value) in next_steps:
            next_action = next_steps[str(user_value)]
        else:
            next_action = next_steps.get('default', 'complete')
        
        if next_action == 'complete':
            return {'action': 'complete'}
        elif next_action == 'escalate':
            return {'action': 'escalate', 'reason': '사용자 요청'}
        else:
            return {'action': 'continue', 'next_step_id': next_action}
    
    def _personalize_message(self, message: str, collected_data: Dict) -> str:
        """메시지 개인화"""
        try:
            return message.format(**collected_data)
        except (KeyError, ValueError):
            return message
    
    def _calculate_progress(self, scenario_def: Dict, current_step_id: str) -> float:
        """진행률 계산"""
        steps = scenario_def.get('steps', [])
        if not steps:
            return 100.0
        
        current_index = -1
        for i, step in enumerate(steps):
            if step['step_id'] == current_step_id:
                current_index = i
                break
        
        if current_index == -1:
            return 0.0
        
        return (current_index + 1) / len(steps) * 100
    
    def _complete_scenario(self, session: ScenarioSession) -> Dict[str, Any]:
        """시나리오 완료 처리"""
        return {
            'success': True,
            'message': '요청이 완료되었습니다. 담당자가 검토 후 연락드리겠습니다.',
            'session_status': session.status.value,
            'collected_data': session.collected_data,
            'completion_time': self._get_current_timestamp()
        }
    
    def _escalate_scenario(self, session: ScenarioSession, reason: str) -> Dict[str, Any]:
        """시나리오 에스컬레이션"""
        session.status = ScenarioStatus.ESCALATED
        session.updated_at = self._get_current_timestamp()
        self._save_session(session)
        
        return {
            'success': True,
            'message': '상담원에게 연결해드리겠습니다. 잠시만 기다려주세요.',
            'session_status': session.status.value,
            'escalation_reason': reason,
            'collected_data': session.collected_data
        }
    
    def _save_session(self, session: ScenarioSession):
        """세션 저장"""
        try:
            self.sessions_table.put_item(Item={
                'session_id': session.session_id,
                'scenario_id': session.scenario_id,
                'current_step': session.current_step,
                'status': session.status.value,
                'collected_data': session.collected_data,
                'retry_count': session.retry_count,
                'created_at': session.created_at,
                'updated_at': session.updated_at
            })
        except Exception as e:
            logger.error(f"세션 저장 오류: {str(e)}")
            raise
    
    def _get_session(self, session_id: str) -> Optional[ScenarioSession]:
        """세션 조회"""
        try:
            response = self.sessions_table.get_item(Key={'session_id': session_id})
            item = response.get('Item')
            
            if not item:
                return None
            
            return ScenarioSession(
                session_id=item['session_id'],
                scenario_id=item['scenario_id'],
                current_step=item['current_step'],
                status=ScenarioStatus(item['status']),
                collected_data=item['collected_data'],
                retry_count=item['retry_count'],
                created_at=item['created_at'],
                updated_at=item['updated_at']
            )
            
        except Exception as e:
            logger.error(f"세션 조회 오류: {str(e)}")
            return None
    
    def _get_current_timestamp(self) -> str:
        """현재 타임스탬프 반환"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def _create_error_response(self, message: str) -> Dict[str, Any]:
        """오류 응답 생성"""
        return {
            'success': False,
            'message': message,
            'session_status': 'error'
        } 