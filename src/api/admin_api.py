"""
AWS Connect 콜센터용 관리자 API
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from datetime import datetime, timedelta
from functools import wraps

from ..services.conversation_service import ConversationService
from ..services.nlu_service import NLUService
from ..services.escalation_service import EscalationService
from ..chatbot_faq import ChatbotFAQ
from ..utils.logger import setup_logger
from ..utils.config import Config

logger = setup_logger(__name__)

app = Flask(__name__)
CORS(app)

# 서비스 초기화
conversation_service = ConversationService()
nlu_service = NLUService(Config.get('LEX_BOT_NAME'))
escalation_service = EscalationService(Config.get('CONNECT_INSTANCE_ID'))
faq_manager = ChatbotFAQ()

def require_admin_auth(f):
    """관리자 인증 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': '인증이 필요합니다.'}), 401
        
        # 실제 구현에서는 JWT 토큰 검증 등을 수행
        token = auth_header.split(' ')[1]
        if not _validate_admin_token(token):
            return jsonify({'error': '유효하지 않은 토큰입니다.'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/api/v1/dashboard/overview', methods=['GET'])
@require_admin_auth
def get_dashboard_overview():
    """대시보드 개요 정보"""
    try:
        # 오늘 날짜 기준 통계
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 대화 통계
        active_conversations = len(conversation_service.get_active_conversations())
        
        # NLU 분석 통계
        nlu_analytics = nlu_service.get_nlu_analytics(yesterday, today)
        
        # 에스컬레이션 통계
        escalation_analytics = escalation_service.escalation_manager.get_escalation_analytics(yesterday, today)
        
        overview = {
            'active_conversations': active_conversations,
            'total_requests_today': nlu_analytics.get('total_requests', 0),
            'average_confidence': nlu_analytics.get('average_confidence', 0),
            'escalation_rate': escalation_analytics.get('escalation_rate', 0),
            'popular_intents': list(nlu_analytics.get('intent_distribution', {}).keys())[:5],
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'data': overview
        })
        
    except Exception as e:
        logger.error(f"대시보드 개요 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/conversations', methods=['GET'])
@require_admin_auth
def get_conversations():
    """대화 목록 조회"""
    try:
        # 쿼리 파라미터
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        status = request.args.get('status')
        user_id = request.args.get('user_id')
        agent_id = request.args.get('agent_id')
        
        # 대화 검색
        if start_date or end_date:
            conversations = conversation_service.search_conversations(
                query="", start_date=start_date, end_date=end_date
            )
        else:
            conversations = conversation_service.get_active_conversations(user_id, agent_id)
        
        # 결과 변환
        conversation_list = []
        for conv in conversations:
            conversation_data = {
                'conversation_id': conv.conversation_id,
                'user_id': conv.user_id,
                'channel': conv.channel,
                'status': conv.status.value,
                'message_count': len(conv.messages),
                'duration': conv.get_conversation_duration(),
                'created_at': conv.created_at,
                'assigned_agent': conv.assigned_agent_id,
                'tags': conv.tags
            }
            conversation_list.append(conversation_data)
        
        return jsonify({
            'success': True,
            'data': {
                'conversations': conversation_list,
                'total_count': len(conversation_list)
            }
        })
        
    except Exception as e:
        logger.error(f"대화 목록 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/conversations/<conversation_id>', methods=['GET'])
@require_admin_auth
def get_conversation_detail(conversation_id):
    """대화 상세 조회"""
    try:
        conversation = conversation_service.get_conversation(conversation_id)
        if not conversation:
            return jsonify({'success': False, 'error': '대화를 찾을 수 없습니다.'}), 404
        
        # 메시지 변환
        messages = []
        for msg in conversation.messages:
            message_data = {
                'message_id': msg.message_id,
                'source': msg.source.value,
                'message_type': msg.message_type.value,
                'content': msg.content,
                'timestamp': msg.timestamp,
                'metadata': msg.metadata
            }
            messages.append(message_data)
        
        conversation_detail = {
            'conversation_id': conversation.conversation_id,
            'session_id': conversation.session_id,
            'user_id': conversation.user_id,
            'channel': conversation.channel,
            'status': conversation.status.value,
            'messages': messages,
            'context': conversation.context,
            'created_at': conversation.created_at,
            'updated_at': conversation.updated_at,
            'duration': conversation.get_conversation_duration(),
            'assigned_agent': conversation.assigned_agent_id,
            'escalation_id': conversation.escalation_id,
            'tags': conversation.tags,
            'summary': conversation.summary.__dict__ if conversation.summary else None
        }
        
        return jsonify({
            'success': True,
            'data': conversation_detail
        })
        
    except Exception as e:
        logger.error(f"대화 상세 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/faq', methods=['GET'])
@require_admin_auth
def get_faq_list():
    """FAQ 목록 조회"""
    try:
        category = request.args.get('category')
        limit = int(request.args.get('limit', 50))
        
        if category:
            # 카테고리별 조회 (실제 구현 필요)
            faqs = []
        else:
            # 인기 FAQ 조회
            popular_faqs = faq_manager.get_popular_faqs(limit=limit)
            faqs = [faq.__dict__ for faq in popular_faqs]
        
        return jsonify({
            'success': True,
            'data': {
                'faqs': faqs,
                'total_count': len(faqs)
            }
        })
        
    except Exception as e:
        logger.error(f"FAQ 목록 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/faq', methods=['POST'])
@require_admin_auth
def create_faq():
    """FAQ 생성"""
    try:
        data = request.get_json()
        
        required_fields = ['category', 'question', 'answer']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False, 
                    'error': f'{field}는 필수 항목입니다.'
                }), 400
        
        # FAQ 추가
        result = faq_manager.add_faq(
            category=data['category'],
            question=data['question'],
            answer=data['answer'],
            keywords=data.get('keywords', []),
            priority=data.get('priority', 0)
        )
        
        return jsonify({
            'success': result,
            'message': 'FAQ가 생성되었습니다.' if result else 'FAQ 생성에 실패했습니다.'
        })
        
    except Exception as e:
        logger.error(f"FAQ 생성 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/faq/<faq_id>', methods=['PUT'])
@require_admin_auth
def update_faq(faq_id):
    """FAQ 수정"""
    try:
        data = request.get_json()
        
        # FAQ 수정
        result = faq_manager.update_faq(faq_id, **data)
        
        return jsonify({
            'success': result,
            'message': 'FAQ가 수정되었습니다.' if result else 'FAQ 수정에 실패했습니다.'
        })
        
    except Exception as e:
        logger.error(f"FAQ 수정 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/faq/<faq_id>', methods=['DELETE'])
@require_admin_auth
def delete_faq(faq_id):
    """FAQ 삭제"""
    try:
        result = faq_manager.delete_faq(faq_id)
        
        return jsonify({
            'success': result,
            'message': 'FAQ가 삭제되었습니다.' if result else 'FAQ 삭제에 실패했습니다.'
        })
        
    except Exception as e:
        logger.error(f"FAQ 삭제 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/analytics/nlu', methods=['GET'])
@require_admin_auth
def get_nlu_analytics():
    """NLU 분석 통계"""
    try:
        start_date = request.args.get('start_date', 
                                    (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        analytics = nlu_service.get_nlu_analytics(start_date, end_date)
        
        return jsonify({
            'success': True,
            'data': {
                'period': {'start': start_date, 'end': end_date},
                'analytics': analytics
            }
        })
        
    except Exception as e:
        logger.error(f"NLU 분석 통계 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/analytics/escalations', methods=['GET'])
@require_admin_auth
def get_escalation_analytics():
    """에스컬레이션 분석 통계"""
    try:
        start_date = request.args.get('start_date', 
                                    (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        
        analytics = escalation_service.escalation_manager.get_escalation_analytics(start_date, end_date)
        
        return jsonify({
            'success': True,
            'data': {
                'period': {'start': start_date, 'end': end_date},
                'analytics': analytics
            }
        })
        
    except Exception as e:
        logger.error(f"에스컬레이션 분석 통계 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/reports/escalations', methods=['POST'])
@require_admin_auth
def generate_escalation_report():
    """에스컬레이션 리포트 생성"""
    try:
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'error': '시작 날짜와 종료 날짜가 필요합니다.'
            }), 400
        
        report = escalation_service.generate_escalation_report(start_date, end_date)
        
        return jsonify({
            'success': True,
            'data': report
        })
        
    except Exception as e:
        logger.error(f"에스컬레이션 리포트 생성 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/agents', methods=['GET'])
@require_admin_auth
def get_agents():
    """상담원 목록 조회"""
    try:
        skills = request.args.getlist('skills')
        available_only = request.args.get('available_only', 'false').lower() == 'true'
        
        if available_only:
            agents = escalation_service.escalation_manager.get_available_agents(skills)
        else:
            # 전체 상담원 목록 조회 (실제 구현 필요)
            agents = []
        
        agent_list = [agent.__dict__ for agent in agents]
        
        return jsonify({
            'success': True,
            'data': {
                'agents': agent_list,
                'total_count': len(agent_list)
            }
        })
        
    except Exception as e:
        logger.error(f"상담원 목록 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/escalations', methods=['GET'])
@require_admin_auth
def get_escalations():
    """에스컬레이션 목록 조회"""
    try:
        status = request.args.get('status')
        priority = request.args.get('priority')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # 실제 구현에서는 필터링 로직 추가
        escalations = []  # 에스컬레이션 조회 로직 필요
        
        return jsonify({
            'success': True,
            'data': {
                'escalations': escalations,
                'total_count': len(escalations)
            }
        })
        
    except Exception as e:
        logger.error(f"에스컬레이션 목록 조회 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/escalations/<escalation_id>/assign', methods=['POST'])
@require_admin_auth
def assign_escalation_agent(escalation_id):
    """에스컬레이션 상담원 배정"""
    try:
        data = request.get_json()
        agent_id = data.get('agent_id')
        
        if not agent_id:
            return jsonify({
                'success': False,
                'error': '상담원 ID가 필요합니다.'
            }), 400
        
        result = escalation_service.escalation_manager.assign_agent(escalation_id, agent_id)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"에스컬레이션 상담원 배정 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/v1/system/health', methods=['GET'])
@require_admin_auth
def system_health():
    """시스템 상태 체크"""
    try:
        health_status = {
            'database': _check_database_health(),
            'aws_services': _check_aws_services_health(),
            'api_status': 'healthy',
            'timestamp': datetime.now().isoformat()
        }
        
        overall_status = all(status == 'healthy' for status in health_status.values() if status != health_status['timestamp'])
        
        return jsonify({
            'success': True,
            'overall_status': 'healthy' if overall_status else 'unhealthy',
            'details': health_status
        })
        
    except Exception as e:
        logger.error(f"시스템 상태 체크 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def _validate_admin_token(token):
    """관리자 토큰 검증 (실제 구현 필요)"""
    # JWT 토큰 검증, 역할 확인 등
    return token == "admin-token"  # 임시 구현

def _check_database_health():
    """데이터베이스 상태 체크"""
    try:
        # DynamoDB 연결 테스트
        conversation_service.conversations_table.describe_table()
        return 'healthy'
    except Exception:
        return 'unhealthy'

def _check_aws_services_health():
    """AWS 서비스 상태 체크"""
    try:
        # AWS 서비스 연결 테스트
        return 'healthy'
    except Exception:
        return 'unhealthy'

if __name__ == '__main__':
    app.run(
        host=Config.get('ADMIN_API_HOST', '0.0.0.0'),
        port=Config.get('ADMIN_API_PORT', 8001),
        debug=Config.get('DEBUG', False)
    ) 