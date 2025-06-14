"""
AWS Connect 콜센터용 챗봇 API with Swagger Documentation
"""
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_restx import Api, Resource, fields, Namespace
import logging
import json
from typing import Dict, Any
import uuid
from datetime import datetime

from ..services.conversation_service import ConversationService
from ..services.nlu_service import NLUService
from ..services.escalation_service import EscalationService
from ..chatbot_scenario import ChatbotScenario
from ..chatbot_faq import ChatbotFAQ
from ..utils.logger import setup_logger
from ..utils.config import Config

# 로거 설정
logger = setup_logger(__name__)

# Flask 앱 생성
app = Flask(__name__)
app.secret_key = Config.get('SECRET_KEY', 'default-secret-key')
CORS(app)

# Flask-RESTX API 설정
api = Api(
    app,
    version='1.0',
    title='AICC 챗봇 API',
    description='AWS Connect 기반 AI 콜센터 챗봇 API 문서',
    doc='/docs/',
    prefix='/api/v1'
)

# 네임스페이스 정의
conversation_ns = Namespace('conversation', description='대화 관리 API')
faq_ns = Namespace('faq', description='FAQ 검색 API')
admin_ns = Namespace('admin', description='관리자 API')

api.add_namespace(conversation_ns)
api.add_namespace(faq_ns)
api.add_namespace(admin_ns)

# 서비스 초기화
conversation_service = ConversationService()
nlu_service = NLUService(Config.get('LEX_BOT_NAME'))
escalation_service = EscalationService(Config.get('CONNECT_INSTANCE_ID'))
scenario_manager = ChatbotScenario()
faq_manager = ChatbotFAQ()

# Swagger 모델 정의
conversation_start_model = api.model('ConversationStart', {
    'session_id': fields.String(description='세션 ID (선택사항)', example='session_123'),
    'user_id': fields.String(description='사용자 ID (선택사항)', example='user_456'),
    'channel': fields.String(description='채널', example='web_chat', default='web_chat')
})

conversation_start_response = api.model('ConversationStartResponse', {
    'success': fields.Boolean(description='성공 여부', example=True),
    'conversation_id': fields.String(description='대화 ID', example='conv_789'),
    'session_id': fields.String(description='세션 ID', example='session_123'),
    'message': fields.String(description='환영 메시지', example='안녕하세요! 무엇을 도와드릴까요?'),
    'timestamp': fields.String(description='타임스탬프', example='2024-01-01T12:00:00')
})

message_send_model = api.model('MessageSend', {
    'message': fields.String(required=True, description='사용자 메시지', example='안녕하세요')
})

message_response = api.model('MessageResponse', {
    'success': fields.Boolean(description='성공 여부', example=True),
    'intent': fields.String(description='감지된 의도', example='greeting'),
    'confidence': fields.Float(description='신뢰도', example=0.95),
    'response': fields.String(description='봇 응답', example='안녕하세요! 무엇을 도와드릴까요?'),
    'next_action': fields.String(description='다음 액션', example='continue'),
    'entities': fields.Raw(description='추출된 엔티티'),
    'timestamp': fields.String(description='타임스탬프')
})

faq_search_model = api.model('FAQSearch', {
    'query': fields.String(required=True, description='검색어', example='환불 방법'),
    'category': fields.String(description='카테고리 (선택사항)', example='payment')
})

faq_item = api.model('FAQItem', {
    'faq_id': fields.String(description='FAQ ID', example='faq_001'),
    'category': fields.String(description='카테고리', example='payment'),
    'question': fields.String(description='질문', example='환불은 어떻게 하나요?'),
    'answer': fields.String(description='답변', example='환불은 구매일로부터 7일 이내에 가능합니다.'),
    'keywords': fields.List(fields.String, description='키워드 목록')
})

faq_search_response = api.model('FAQSearchResponse', {
    'success': fields.Boolean(description='성공 여부', example=True),
    'query': fields.String(description='검색어', example='환불 방법'),
    'total_count': fields.Integer(description='총 결과 수', example=5),
    'confidence': fields.Float(description='검색 신뢰도', example=0.85),
    'faqs': fields.List(fields.Nested(faq_item), description='FAQ 목록'),
    'timestamp': fields.String(description='타임스탬프')
})

escalation_model = api.model('Escalation', {
    'reason': fields.String(description='에스컬레이션 사유', example='customer_request'),
    'description': fields.String(description='상세 설명', example='복잡한 문의로 상담원 연결 필요')
})

error_response = api.model('ErrorResponse', {
    'success': fields.Boolean(description='성공 여부', example=False),
    'error': fields.String(description='오류 메시지', example='잘못된 요청입니다.'),
    'timestamp': fields.String(description='타임스탬프')
})

# 헬스 체크 엔드포인트
@app.route('/health', methods=['GET'])
def health_check():
    """
    헬스 체크
    ---
    tags:
      - Health
    responses:
      200:
        description: 서비스 상태 정상
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            timestamp:
              type: string
              example: 2024-01-01T12:00:00
            version:
              type: string
              example: 1.0.0
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

# 대화 관리 API
@conversation_ns.route('/start')
class ConversationStart(Resource):
    @conversation_ns.expect(conversation_start_model)
    @conversation_ns.marshal_with(conversation_start_response)
    @conversation_ns.doc('start_conversation')
    def post(self):
        """새로운 대화 시작"""
        try:
            data = request.get_json() or {}
            
            # 세션 ID 생성 또는 사용
            session_id = data.get('session_id') or str(uuid.uuid4())
            user_id = data.get('user_id')
            channel = data.get('channel', 'web_chat')
            
            # 새 대화 생성
            conversation = conversation_service.create_conversation(
                session_id=session_id,
                user_id=user_id,
                channel=channel
            )
            
            # 세션에 대화 ID 저장
            session['conversation_id'] = conversation.conversation_id
            session['session_id'] = session_id
            
            return {
                'success': True,
                'conversation_id': conversation.conversation_id,
                'session_id': session_id,
                'message': '안녕하세요! 무엇을 도와드릴까요?',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"대화 시작 오류: {str(e)}")
            conversation_ns.abort(500, '대화를 시작할 수 없습니다.')

@conversation_ns.route('/message')
class MessageSend(Resource):
    @conversation_ns.expect(message_send_model)
    @conversation_ns.marshal_with(message_response)
    @conversation_ns.doc('send_message')
    def post(self):
        """메시지 전송 및 처리"""
        try:
            data = request.get_json()
            
            conversation_id = session.get('conversation_id')
            if not conversation_id:
                conversation_ns.abort(400, '활성 대화가 없습니다.')
            
            user_message = data.get('message', '').strip()
            if not user_message:
                conversation_ns.abort(400, '메시지가 비어있습니다.')
            
            # 사용자 메시지 저장
            conversation_service.send_user_message(conversation_id, user_message)
            
            # 대화 조회
            conversation = conversation_service.get_conversation(conversation_id)
            if not conversation:
                conversation_ns.abort(404, '대화를 찾을 수 없습니다.')
            
            # NLU 처리
            session_attributes = conversation.context
            nlu_result = nlu_service.process_user_input(
                user_message, 
                session.get('session_id'),
                session_attributes
            )
            
            # 응답 처리
            response_data = self._process_nlu_result(conversation, nlu_result)
            
            return response_data
            
        except Exception as e:
            logger.error(f"메시지 처리 오류: {str(e)}")
            conversation_ns.abort(500, '메시지를 처리할 수 없습니다.')
    
    def _process_nlu_result(self, conversation, nlu_result):
        """NLU 결과 처리"""
        # 봇 응답 저장
        conversation_service.send_bot_message(
            conversation.conversation_id,
            nlu_result.response_text,
            {
                'intent': nlu_result.intent_result.intent,
                'confidence': nlu_result.intent_result.confidence,
                'entities': nlu_result.intent_result.entities
            }
        )
        
        return {
            'success': True,
            'intent': nlu_result.intent_result.intent,
            'confidence': nlu_result.intent_result.confidence,
            'response': nlu_result.response_text,
            'next_action': nlu_result.next_action,
            'entities': nlu_result.intent_result.entities,
            'timestamp': datetime.now().isoformat()
        }

@conversation_ns.route('/escalate')
class ConversationEscalate(Resource):
    @conversation_ns.expect(escalation_model)
    @conversation_ns.doc('escalate_conversation')
    def post(self):
        """대화 에스컬레이션 (상담원 연결)"""
        try:
            data = request.get_json() or {}
            
            conversation_id = session.get('conversation_id')
            if not conversation_id:
                conversation_ns.abort(400, '활성 대화가 없습니다.')
            
            reason = data.get('reason', 'customer_request')
            description = data.get('description', '고객 요청에 의한 상담원 연결')
            
            # 대화 정보 조회
            conversation = conversation_service.get_conversation(conversation_id)
            if not conversation:
                conversation_ns.abort(404, '대화를 찾을 수 없습니다.')
            
            # 에스컬레이션 처리
            escalation_id = str(uuid.uuid4())
            escalation_result = escalation_service.create_escalation(
                conversation_id=conversation_id,
                escalation_id=escalation_id,
                reason=reason,
                description=description,
                user_id=conversation.user_id
            )
            
            if escalation_result.success:
                # 대화 상태 업데이트
                conversation_service.escalate_conversation(
                    conversation_id, escalation_id, reason
                )
                
                return {
                    'success': True,
                    'escalation_id': escalation_id,
                    'estimated_wait_time': escalation_result.estimated_wait_time,
                    'message': '상담원에게 연결해드리겠습니다. 잠시만 기다려 주세요.',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': escalation_result.error_message,
                    'timestamp': datetime.now().isoformat()
                }, 500
                
        except Exception as e:
            logger.error(f"에스컬레이션 오류: {str(e)}")
            conversation_ns.abort(500, '에스컬레이션 처리 중 오류가 발생했습니다.')

@conversation_ns.route('/end')
class ConversationEnd(Resource):
    @conversation_ns.doc('end_conversation')
    def post(self):
        """대화 종료"""
        try:
            conversation_id = session.get('conversation_id')
            if not conversation_id:
                conversation_ns.abort(400, '활성 대화가 없습니다.')
            
            # 대화 완료 처리
            conversation_service.complete_conversation(
                conversation_id,
                '사용자 요청에 의한 대화 종료'
            )
            
            # 세션 정리
            session.pop('conversation_id', None)
            session.pop('session_id', None)
            
            return {
                'success': True,
                'message': '대화가 종료되었습니다. 이용해 주셔서 감사합니다.',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"대화 종료 오류: {str(e)}")
            conversation_ns.abort(500, '대화 종료 중 오류가 발생했습니다.')

@conversation_ns.route('/status')
class ConversationStatus(Resource):
    @conversation_ns.doc('get_conversation_status')
    def get(self):
        """현재 대화 상태 조회"""
        try:
            conversation_id = session.get('conversation_id')
            if not conversation_id:
                return {
                    'success': False,
                    'error': '활성 대화가 없습니다.'
                }, 400
            
            conversation = conversation_service.get_conversation(conversation_id)
            if not conversation:
                return {
                    'success': False,
                    'error': '대화를 찾을 수 없습니다.'
                }, 404
            
            return {
                'success': True,
                'conversation_id': conversation.conversation_id,
                'status': conversation.status.value,
                'created_at': conversation.created_at.isoformat(),
                'message_count': len(conversation.messages),
                'last_activity': conversation.updated_at.isoformat() if conversation.updated_at else None,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"대화 상태 조회 오류: {str(e)}")
            conversation_ns.abort(500, '대화 상태 조회 중 오류가 발생했습니다.')

# FAQ 검색 API
@faq_ns.route('/search')
class FAQSearch(Resource):
    @faq_ns.expect(faq_search_model)
    @faq_ns.marshal_with(faq_search_response)
    @faq_ns.doc('search_faq')
    def post(self):
        """FAQ 검색"""
        try:
            data = request.get_json()
            query = data.get('query', '').strip()
            category = data.get('category')
            
            if not query:
                faq_ns.abort(400, '검색어가 필요합니다.')
            
            # FAQ 검색
            search_result = faq_manager.search_faq(query, category)
            
            # 결과 변환
            faq_items = []
            for faq in search_result.faq_items:
                faq_items.append({
                    'faq_id': faq.faq_id,
                    'category': faq.category,
                    'question': faq.question,
                    'answer': faq.answer,
                    'keywords': faq.keywords
                })
            
            return {
                'success': True,
                'query': query,
                'total_count': search_result.total_count,
                'confidence': search_result.confidence_score,
                'faqs': faq_items,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"FAQ 검색 오류: {str(e)}")
            faq_ns.abort(500, 'FAQ 검색 중 오류가 발생했습니다.')

@faq_ns.route('/categories')
class FAQCategories(Resource):
    @faq_ns.doc('get_faq_categories')
    def get(self):
        """FAQ 카테고리 목록 조회"""
        try:
            categories = faq_manager.get_categories()
            
            return {
                'success': True,
                'categories': categories,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"FAQ 카테고리 조회 오류: {str(e)}")
            faq_ns.abort(500, 'FAQ 카테고리 조회 중 오류가 발생했습니다.')

# 관리자 API
@admin_ns.route('/conversations')
class AdminConversations(Resource):
    @admin_ns.doc('get_conversations')
    def get(self):
        """대화 목록 조회 (관리자용)"""
        try:
            # 쿼리 파라미터
            page = request.args.get('page', 1, type=int)
            size = request.args.get('size', 20, type=int)
            status = request.args.get('status')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            
            # 대화 목록 조회 (실제 구현 필요)
            conversations = []  # conversation_service.get_conversations_admin(...)
            
            return {
                'success': True,
                'conversations': conversations,
                'page': page,
                'size': size,
                'total': len(conversations),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"관리자 대화 목록 조회 오류: {str(e)}")
            admin_ns.abort(500, '대화 목록 조회 중 오류가 발생했습니다.')

@admin_ns.route('/analytics')
class AdminAnalytics(Resource):
    @admin_ns.doc('get_analytics')
    def get(self):
        """분석 데이터 조회 (관리자용)"""
        try:
            # 분석 데이터 조회 (실제 구현 필요)
            analytics_data = {
                'total_conversations': 1000,
                'active_conversations': 50,
                'escalation_rate': 0.15,
                'average_resolution_time': 300,
                'top_intents': [
                    {'intent': 'product_inquiry', 'count': 300},
                    {'intent': 'complaint', 'count': 150},
                    {'intent': 'technical_support', 'count': 100}
                ]
            }
            
            return {
                'success': True,
                'analytics': analytics_data,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"분석 데이터 조회 오류: {str(e)}")
            admin_ns.abort(500, '분석 데이터 조회 중 오류가 발생했습니다.')

# 오류 핸들러
@api.errorhandler(404)
def not_found(error):
    return {'success': False, 'error': '요청한 리소스를 찾을 수 없습니다.'}, 404

@api.errorhandler(500)
def internal_error(error):
    return {'success': False, 'error': '서버 내부 오류가 발생했습니다.'}, 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 