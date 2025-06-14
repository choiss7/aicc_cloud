"""
AWS Connect 콜센터용 에스컬레이션 서비스
"""
import json
import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

from ..chatbot_escalation import ChatbotEscalation, EscalationReason, EscalationPriority, EscalationStatus

logger = logging.getLogger(__name__)

class EscalationService:
    """에스컬레이션 관리 서비스"""
    
    def __init__(self, connect_instance_id: str, dynamodb_table_name: str = "escalation_service"):
        self.escalation_manager = ChatbotEscalation(connect_instance_id, dynamodb_table_name)
        
        # Additional services
        self.sns_client = boto3.client('sns')
        self.ses_client = boto3.client('ses')
        self.lambda_client = boto3.client('lambda')
        
        # Configuration
        self.notification_topic_arn = "arn:aws:sns:region:account:escalation-notifications"
        self.supervisor_email = "supervisor@company.com"
        
        # Escalation rules
        self.auto_escalation_rules = self._load_escalation_rules()
    
    def handle_auto_escalation(self, conversation_history: List[Dict],
                             customer_data: Dict, session_id: str) -> Optional[Dict]:
        """
        자동 에스컬레이션 처리
        
        Args:
            conversation_history: 대화 이력
            customer_data: 고객 데이터
            session_id: 세션 ID
            
        Returns:
            Optional[Dict]: 에스컬레이션 결과
        """
        try:
            # 자동 에스컬레이션 조건 확인
            escalation_trigger = self._check_auto_escalation_conditions(
                conversation_history, customer_data
            )
            
            if not escalation_trigger:
                return None
            
            reason = escalation_trigger['reason']
            description = escalation_trigger['description']
            
            # 에스컬레이션 요청
            result = self.escalation_manager.request_escalation(
                session_id=session_id,
                reason=reason,
                description=description,
                conversation_history=conversation_history,
                customer_data=customer_data
            )
            
            if result['success']:
                # 자동 에스컬레이션 알림
                self._send_auto_escalation_notification(result, escalation_trigger)
                
                logger.info(f"자동 에스컬레이션 처리 완료: {result['escalation_id']}")
            
            return result
            
        except Exception as e:
            logger.error(f"자동 에스컬레이션 처리 오류: {str(e)}")
            return None
    
    def process_manual_escalation(self, session_id: str, reason: str,
                                description: str, conversation_history: List[Dict],
                                customer_data: Dict, agent_id: Optional[str] = None) -> Dict:
        """
        수동 에스컬레이션 처리
        
        Args:
            session_id: 세션 ID
            reason: 에스컬레이션 사유
            description: 상세 설명
            conversation_history: 대화 이력
            customer_data: 고객 데이터
            agent_id: 요청한 상담원 ID (있는 경우)
            
        Returns:
            Dict: 에스컬레이션 결과
        """
        try:
            # 사유를 열거형으로 변환
            escalation_reason = self._map_reason_to_enum(reason)
            
            # 에스컬레이션 요청
            result = self.escalation_manager.request_escalation(
                session_id=session_id,
                reason=escalation_reason,
                description=description,
                conversation_history=conversation_history,
                customer_data=customer_data
            )
            
            if result['success']:
                # 수동 에스컬레이션 로깅
                self._log_manual_escalation(result, agent_id, reason)
                
                # 알림 전송
                self._send_manual_escalation_notification(result, agent_id)
            
            return result
            
        except Exception as e:
            logger.error(f"수동 에스컬레이션 처리 오류: {str(e)}")
            return {
                'success': False,
                'message': '에스컬레이션 요청을 처리할 수 없습니다.'
            }
    
    def assign_best_agent(self, escalation_id: str, skill_requirements: Optional[List[str]] = None) -> Dict:
        """
        최적 상담원 자동 배정
        
        Args:
            escalation_id: 에스컬레이션 ID
            skill_requirements: 필요 스킬 목록
            
        Returns:
            Dict: 배정 결과
        """
        try:
            # 에스컬레이션 정보 조회
            escalation = self.escalation_manager._get_escalation_request(escalation_id)
            if not escalation:
                return {'success': False, 'message': '에스컬레이션을 찾을 수 없습니다.'}
            
            # 가용한 상담원 조회
            available_agents = self.escalation_manager.get_available_agents(skill_requirements)
            
            if not available_agents:
                return {
                    'success': False,
                    'message': '현재 가용한 상담원이 없습니다.',
                    'action': 'queue_for_callback'
                }
            
            # 최적 상담원 선택
            best_agent = self._select_best_agent(available_agents, escalation, skill_requirements)
            
            # 상담원 배정
            assignment_result = self.escalation_manager.assign_agent(escalation_id, best_agent.agent_id)
            
            if assignment_result['success']:
                # 배정 후 처리
                self._post_assignment_processing(escalation, best_agent)
            
            return assignment_result
            
        except Exception as e:
            logger.error(f"상담원 자동 배정 오류: {str(e)}")
            return {'success': False, 'message': '상담원 배정을 처리할 수 없습니다.'}
    
    def handle_escalation_timeout(self, escalation_id: str) -> Dict:
        """
        에스컬레이션 타임아웃 처리
        
        Args:
            escalation_id: 에스컬레이션 ID
            
        Returns:
            Dict: 처리 결과
        """
        try:
            escalation = self.escalation_manager._get_escalation_request(escalation_id)
            if not escalation:
                return {'success': False, 'message': '에스컬레이션을 찾을 수 없습니다.'}
            
            # 타임아웃 처리 로직
            if escalation.priority == EscalationPriority.CRITICAL:
                # 긴급 건은 슈퍼바이저에게 즉시 에스컬레이션
                return self._escalate_to_supervisor(escalation)
            else:
                # 일반 건은 콜백 큐로 이동
                return self._move_to_callback_queue(escalation)
            
        except Exception as e:
            logger.error(f"에스컬레이션 타임아웃 처리 오류: {str(e)}")
            return {'success': False, 'message': '타임아웃 처리 중 오류가 발생했습니다.'}
    
    def generate_escalation_report(self, start_date: str, end_date: str) -> Dict:
        """
        에스컬레이션 리포트 생성
        
        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
            
        Returns:
            Dict: 리포트 데이터
        """
        try:
            # 기본 분석 데이터 가져오기
            analytics = self.escalation_manager.get_escalation_analytics(start_date, end_date)
            
            # 추가 분석 수행
            detailed_analysis = self._perform_detailed_analysis(start_date, end_date)
            
            # 리포트 생성
            report = {
                'period': {'start': start_date, 'end': end_date},
                'summary': analytics,
                'detailed_analysis': detailed_analysis,
                'recommendations': self._generate_recommendations(analytics),
                'generated_at': datetime.now().isoformat()
            }
            
            # 리포트 저장 (S3 등)
            self._save_report(report)
            
            return report
            
        except Exception as e:
            logger.error(f"에스컬레이션 리포트 생성 오류: {str(e)}")
            return {}
    
    def _check_auto_escalation_conditions(self, conversation_history: List[Dict],
                                        customer_data: Dict) -> Optional[Dict]:
        """자동 에스컬레이션 조건 확인"""
        
        # 조건 1: 대화 턴 수 초과
        user_messages = [msg for msg in conversation_history if msg.get('source') == 'user']
        if len(user_messages) >= self.auto_escalation_rules['max_conversation_turns']:
            return {
                'reason': EscalationReason.BOT_LIMITATION,
                'description': f'대화 턴 수 초과 ({len(user_messages)}회)'
            }
        
        # 조건 2: 부정적 키워드 감지
        negative_keywords = self.auto_escalation_rules['negative_keywords']
        recent_messages = user_messages[-3:]  # 최근 3개 메시지 확인
        
        for message in recent_messages:
            content = message.get('content', '').lower()
            for keyword in negative_keywords:
                if keyword in content:
                    return {
                        'reason': EscalationReason.COMPLAINT,
                        'description': f'부정적 키워드 감지: {keyword}'
                    }
        
        # 조건 3: VIP 고객의 복잡한 문의
        if customer_data.get('vip_status') and len(user_messages) >= 3:
            return {
                'reason': EscalationReason.COMPLEX_INQUIRY,
                'description': 'VIP 고객의 복잡한 문의'
            }
        
        # 조건 4: 반복적인 동일 의도
        recent_intents = [msg.get('intent') for msg in recent_messages if msg.get('intent')]
        if len(set(recent_intents)) == 1 and len(recent_intents) >= 3:
            return {
                'reason': EscalationReason.BOT_LIMITATION,
                'description': f'반복적인 동일 의도: {recent_intents[0]}'
            }
        
        # 조건 5: 긴급 키워드 감지
        urgent_keywords = self.auto_escalation_rules['urgent_keywords']
        for message in recent_messages:
            content = message.get('content', '').lower()
            for keyword in urgent_keywords:
                if keyword in content:
                    return {
                        'reason': EscalationReason.URGENT_MATTER,
                        'description': f'긴급 키워드 감지: {keyword}'
                    }
        
        return None
    
    def _map_reason_to_enum(self, reason: str) -> EscalationReason:
        """사유 문자열을 열거형으로 매핑"""
        mapping = {
            'complaint': EscalationReason.COMPLAINT,
            'complex_inquiry': EscalationReason.COMPLEX_INQUIRY,
            'technical_support': EscalationReason.TECHNICAL_SUPPORT,
            'payment_issue': EscalationReason.PAYMENT_ISSUE,
            'urgent_matter': EscalationReason.URGENT_MATTER,
            'bot_limitation': EscalationReason.BOT_LIMITATION,
            'customer_request': EscalationReason.CUSTOMER_REQUEST,
            'system_error': EscalationReason.SYSTEM_ERROR
        }
        
        return mapping.get(reason.lower(), EscalationReason.CUSTOMER_REQUEST)
    
    def _select_best_agent(self, available_agents, escalation, skill_requirements):
        """최적 상담원 선택 알고리즘"""
        scored_agents = []
        
        for agent in available_agents:
            score = 0
            
            # 스킬 매칭 점수 (40점)
            if skill_requirements:
                skill_match_count = sum(1 for skill in skill_requirements if agent.has_skill(skill))
                skill_score = (skill_match_count / len(skill_requirements)) * 40
                score += skill_score
            else:
                score += 20  # 기본 점수
            
            # 워크로드 점수 (30점) - 낮을수록 좋음
            workload_score = max(0, 30 - (agent.current_workload * 10))
            score += workload_score
            
            # 성과 점수 (20점)
            performance_score = agent.calculate_productivity_score() * 0.2
            score += performance_score
            
            # 고객 타입 매칭 (10점)
            if escalation.customer_data.get('vip_status') and 'vip' in agent.tags:
                score += 10
            elif escalation.reason == EscalationReason.TECHNICAL_SUPPORT and agent.has_skill('technical_support'):
                score += 10
            
            scored_agents.append((agent, score))
        
        # 점수 기준으로 정렬하여 최고점 상담원 선택
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        return scored_agents[0][0]
    
    def _escalate_to_supervisor(self, escalation):
        """슈퍼바이저에게 에스컬레이션"""
        try:
            # 슈퍼바이저 찾기 로직
            supervisor_id = "supervisor_001"  # 실제로는 동적으로 찾아야 함
            
            result = self.escalation_manager.assign_agent(escalation.escalation_id, supervisor_id)
            
            if result['success']:
                # 긴급 알림 전송
                self._send_urgent_notification(escalation, supervisor_id)
            
            return result
            
        except Exception as e:
            logger.error(f"슈퍼바이저 에스컬레이션 오류: {str(e)}")
            return {'success': False, 'message': '슈퍼바이저 에스컬레이션 실패'}
    
    def _move_to_callback_queue(self, escalation):
        """콜백 큐로 이동"""
        try:
            # 콜백 스케줄링 로직
            callback_time = datetime.now() + timedelta(hours=1)
            
            # Lambda 함수를 통한 콜백 스케줄링
            self.lambda_client.invoke(
                FunctionName='schedule-callback',
                InvocationType='Event',
                Payload=json.dumps({
                    'escalation_id': escalation.escalation_id,
                    'callback_time': callback_time.isoformat(),
                    'customer_data': escalation.customer_data
                })
            )
            
            return {
                'success': True,
                'message': '콜백으로 전환되었습니다.',
                'callback_time': callback_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"콜백 큐 이동 오류: {str(e)}")
            return {'success': False, 'message': '콜백 처리 중 오류 발생'}
    
    def _send_auto_escalation_notification(self, result, trigger):
        """자동 에스컬레이션 알림 전송"""
        try:
            message = {
                'type': 'auto_escalation',
                'escalation_id': result['escalation_id'],
                'trigger': trigger,
                'timestamp': datetime.now().isoformat()
            }
            
            self.sns_client.publish(
                TopicArn=self.notification_topic_arn,
                Message=json.dumps(message),
                Subject='자동 에스컬레이션 발생'
            )
            
        except Exception as e:
            logger.error(f"자동 에스컬레이션 알림 전송 오류: {str(e)}")
    
    def _send_manual_escalation_notification(self, result, agent_id):
        """수동 에스컬레이션 알림 전송"""
        try:
            message = {
                'type': 'manual_escalation',
                'escalation_id': result['escalation_id'],
                'requested_by': agent_id,
                'timestamp': datetime.now().isoformat()
            }
            
            self.sns_client.publish(
                TopicArn=self.notification_topic_arn,
                Message=json.dumps(message),
                Subject='수동 에스컬레이션 요청'
            )
            
        except Exception as e:
            logger.error(f"수동 에스컬레이션 알림 전송 오류: {str(e)}")
    
    def _send_urgent_notification(self, escalation, supervisor_id):
        """긴급 알림 전송"""
        try:
            # SNS 알림
            self.sns_client.publish(
                TopicArn=self.notification_topic_arn,
                Message=f"긴급 에스컬레이션: {escalation.escalation_id}",
                Subject='긴급 에스컬레이션 발생'
            )
            
            # 이메일 알림
            self.ses_client.send_email(
                Source='system@company.com',
                Destination={'ToAddresses': [self.supervisor_email]},
                Message={
                    'Subject': {'Data': '긴급 에스컬레이션 발생'},
                    'Body': {
                        'Text': {
                            'Data': f'긴급 에스컬레이션이 발생했습니다.\n\n'
                                   f'에스컬레이션 ID: {escalation.escalation_id}\n'
                                   f'사유: {escalation.reason.value}\n'
                                   f'설명: {escalation.description}'
                        }
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"긴급 알림 전송 오류: {str(e)}")
    
    def _log_manual_escalation(self, result, agent_id, reason):
        """수동 에스컬레이션 로깅"""
        logger.info(f"수동 에스컬레이션 - ID: {result['escalation_id']}, "
                   f"상담원: {agent_id}, 사유: {reason}")
    
    def _post_assignment_processing(self, escalation, agent):
        """배정 후 처리"""
        try:
            # 상담원에게 컨텍스트 정보 전송
            context_info = {
                'customer_data': escalation.customer_data,
                'conversation_summary': escalation.conversation_history[-5:],  # 최근 5개 메시지
                'escalation_reason': escalation.reason.value,
                'priority': escalation.priority.value
            }
            
            # 실제로는 상담원 인터페이스로 전송
            logger.info(f"상담원 {agent.agent_id}에게 컨텍스트 정보 전송")
            
        except Exception as e:
            logger.error(f"배정 후 처리 오류: {str(e)}")
    
    def _perform_detailed_analysis(self, start_date: str, end_date: str) -> Dict:
        """상세 분석 수행"""
        # 실제 구현에서는 더 복잡한 분석 로직
        return {
            'peak_hours': ['10:00-11:00', '14:00-15:00'],
            'common_escalation_paths': ['bot -> agent', 'agent -> supervisor'],
            'resolution_time_analysis': {
                'average': 15.5,
                'median': 12.0,
                'percentile_95': 35.0
            }
        }
    
    def _generate_recommendations(self, analytics: Dict) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []
        
        if analytics.get('total_escalations', 0) > 100:
            recommendations.append("에스컬레이션 건수가 많습니다. 봇 응답 품질 개선을 고려하세요.")
        
        escalation_rate = analytics.get('by_reason', {}).get('bot_limitation', 0)
        if escalation_rate > 30:
            recommendations.append("봇 한계로 인한 에스컬레이션이 많습니다. FAQ 확장을 고려하세요.")
        
        avg_wait_time = analytics.get('average_wait_time', 0)
        if avg_wait_time > 20:
            recommendations.append("평균 대기시간이 깁니다. 상담원 증원을 고려하세요.")
        
        return recommendations
    
    def _save_report(self, report: Dict):
        """리포트 저장"""
        try:
            # S3에 리포트 저장
            s3_client = boto3.client('s3')
            report_key = f"reports/escalation/{datetime.now().strftime('%Y/%m')}/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            s3_client.put_object(
                Bucket='aicc-reports',
                Key=report_key,
                Body=json.dumps(report, ensure_ascii=False),
                ContentType='application/json'
            )
            
            logger.info(f"에스컬레이션 리포트 저장: {report_key}")
            
        except Exception as e:
            logger.error(f"리포트 저장 오류: {str(e)}")
    
    def _load_escalation_rules(self) -> Dict:
        """에스컬레이션 규칙 로드"""
        return {
            'max_conversation_turns': 8,
            'negative_keywords': ['화나', '짜증', '최악', '불만', '화가', '열받'],
            'urgent_keywords': ['긴급', '당장', '즉시', '빨리', '응급'],
            'vip_auto_escalation_turns': 5,
            'timeout_minutes': {
                'critical': 5,
                'high': 10,
                'medium': 20,
                'low': 30
            }
        } 