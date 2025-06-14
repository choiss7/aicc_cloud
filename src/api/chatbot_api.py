"""
AWS Connect 콜센터용 챗봇 API
"""
from flask import Flask, request, jsonify, session
from flask_cors import CORS
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

# 서비스 초기화
conversation_service = ConversationService()
nlu_service = NLUService(Config.get('LEX_BOT_NAME'))
escalation_service = EscalationService(Config.get('CONNECT_INSTANCE_ID'))
scenario_manager = ChatbotScenario()
faq_manager = ChatbotFAQ()

@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/api/v1/conversation/start', methods=['POST'])
def start_conversation():
    """대화 시작"""
    try:
        data = request.get_json()
        
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
        
        return jsonify({
            'success': True,
            'conversation_id': conversation.conversation_id,
            'session_id': session_id,
            'message': '안녕하세요! 무엇을 도와드릴까요?',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"대화 시작 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '대화를 시작할 수 없습니다.',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/v1/conversation/message', methods=['POST'])
def send_message():
    """메시지 전송 및 처리"""
    try:
        data = request.get_json()
        
        conversation_id = session.get('conversation_id')
        if not conversation_id:
            return jsonify({
                'success': False,
                'error': '활성 대화가 없습니다.'
            }), 400
        
        user_message = data.get('message', '').strip()
        if not user_message:
            return jsonify({
                'success': False,
                'error': '메시지가 비어있습니다.'
            }), 400
        
        # 사용자 메시지 저장
        conversation_service.send_user_message(conversation_id, user_message)
        
        # 대화 조회
        conversation = conversation_service.get_conversation(conversation_id)
        if not conversation:
            return jsonify({
                'success': False,
                'error': '대화를 찾을 수 없습니다.'
            }), 404
        
        # NLU 처리
        session_attributes = conversation.context
        nlu_result = nlu_service.process_user_input(
            user_message, 
            session.get('session_id'),
            session_attributes
        )
        
        # 응답 처리
        response_data = await _process_nlu_result(conversation, nlu_result)
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"메시지 처리 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '메시지를 처리할 수 없습니다.',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/v1/conversation/faq', methods=['POST'])
def search_faq():
    """FAQ 검색"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        category = data.get('category')
        
        if not query:
            return jsonify({
                'success': False,
                'error': '검색어가 필요합니다.'
            }), 400
        
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
        
        return jsonify({
            'success': True,
            'query': query,
            'total_count': search_result.total_count,
            'confidence': search_result.confidence_score,
            'faqs': faq_items,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"FAQ 검색 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'FAQ 검색 중 오류가 발생했습니다.'
        }), 500

@app.route('/api/v1/conversation/escalate', methods=['POST'])
def escalate_conversation():
    """대화 에스컬레이션"""
    try:
        data = request.get_json()
        
        conversation_id = session.get('conversation_id')
        if not conversation_id:
            return jsonify({
                'success': False,
                'error': '활성 대화가 없습니다.'
            }), 400
        
        reason = data.get('reason', 'customer_request')
        description = data.get('description', '고객 요청에 의한 상담원 연결')
        
        # 대화 정보 조회
        conversation = conversation_service.get_conversation(conversation_id)
        if not conversation:
            return jsonify({
                'success': False,
                'error': '대화를 찾을 수 없습니다.'
            }), 404
        
        # 대화 이력 준비
        conversation_history = [msg.to_dict() for msg in conversation.messages]
        customer_data = conversation.context.get('customer_data', {})
        
        # 에스컬레이션 요청
        escalation_result = escalation_service.process_manual_escalation(
            session_id=session.get('session_id'),
            reason=reason,
            description=description,
            conversation_history=conversation_history,
            customer_data=customer_data
        )
        
        if escalation_result['success']:
            # 대화 상태 업데이트
            conversation_service.escalate_conversation(
                conversation_id, 
                escalation_result['escalation_id'],
                reason
            )
        
        return jsonify({
            'success': escalation_result['success'],
            'message': escalation_result.get('message'),
            'escalation_id': escalation_result.get('escalation_id'),
            'reference_number': escalation_result.get('reference_number'),
            'estimated_wait_time': escalation_result.get('estimated_wait_time'),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"에스컬레이션 요청 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '상담원 연결 요청을 처리할 수 없습니다.'
        }), 500

@app.route('/api/v1/conversation/scenario/start', methods=['POST'])
def start_scenario():
    """시나리오 시작"""
    try:
        data = request.get_json()
        
        scenario_id = data.get('scenario_id')
        if not scenario_id:
            return jsonify({
                'success': False,
                'error': '시나리오 ID가 필요합니다.'
            }), 400
        
        session_id = session.get('session_id')
        initial_data = data.get('initial_data', {})
        
        # 시나리오 시작
        result = scenario_manager.start_scenario(session_id, scenario_id, initial_data)
        
        # 세션에 시나리오 정보 저장
        if result['success']:
            session['active_scenario'] = scenario_id
            session['scenario_step'] = result['step_id']
        
        return jsonify({
            'success': result['success'],
            'message': result.get('message'),
            'step_id': result.get('step_id'),
            'input_type': result.get('input_type'),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"시나리오 시작 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '시나리오를 시작할 수 없습니다.'
        }), 500

@app.route('/api/v1/conversation/scenario/input', methods=['POST'])
def process_scenario_input():
    """시나리오 입력 처리"""
    try:
        data = request.get_json()
        
        user_input = data.get('input', '').strip()
        if not user_input:
            return jsonify({
                'success': False,
                'error': '입력이 필요합니다.'
            }), 400
        
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '세션이 없습니다.'
            }), 400
        
        # 시나리오 입력 처리
        result = scenario_manager.process_user_input(session_id, user_input)
        
        # 세션 상태 업데이트
        if result['success']:
            session['scenario_step'] = result.get('step_id')
        
        return jsonify({
            'success': result['success'],
            'message': result.get('message'),
            'step_id': result.get('step_id'),
            'input_type': result.get('input_type'),
            'progress': result.get('progress'),
            'retry_count': result.get('retry_count'),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"시나리오 입력 처리 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '입력을 처리할 수 없습니다.'
        }), 500

@app.route('/api/v1/conversation/end', methods=['POST'])
def end_conversation():
    """대화 종료"""
    try:
        data = request.get_json()
        
        conversation_id = session.get('conversation_id')
        if not conversation_id:
            return jsonify({
                'success': False,
                'error': '활성 대화가 없습니다.'
            }), 400
        
        summary = data.get('summary', '')
        
        # 대화 완료 처리
        result = conversation_service.complete_conversation(conversation_id, summary)
        
        if result:
            # 세션 정리
            session.pop('conversation_id', None)
            session.pop('active_scenario', None)
            session.pop('scenario_step', None)
        
        return jsonify({
            'success': result,
            'message': '대화가 완료되었습니다.' if result else '대화 종료 중 오류가 발생했습니다.',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"대화 종료 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '대화를 종료할 수 없습니다.'
        }), 500

@app.route('/api/v1/conversation/status', methods=['GET'])
def get_conversation_status():
    """대화 상태 조회"""
    try:
        conversation_id = session.get('conversation_id')
        if not conversation_id:
            return jsonify({
                'success': False,
                'error': '활성 대화가 없습니다.'
            }), 400
        
        conversation = conversation_service.get_conversation(conversation_id)
        if not conversation:
            return jsonify({
                'success': False,
                'error': '대화를 찾을 수 없습니다.'
            }), 404
        
        return jsonify({
            'success': True,
            'conversation_id': conversation.conversation_id,
            'status': conversation.status.value,
            'message_count': len(conversation.messages),
            'duration': conversation.get_conversation_duration(),
            'assigned_agent': conversation.assigned_agent_id,
            'active_scenario': session.get('active_scenario'),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"대화 상태 조회 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': '상태를 조회할 수 없습니다.'
        }), 500

async def _process_nlu_result(conversation, nlu_result):
    """NLU 결과 처리"""
    try:
        if not nlu_result['success']:
            return {
                'success': False,
                'error': nlu_result.get('error'),
                'response': '죄송합니다. 요청을 처리할 수 없습니다.'
            }
        
        intent = nlu_result['intent']
        confidence = nlu_result['confidence']
        entities = nlu_result['entities']
        next_action = nlu_result['next_action']
        
        # 봇 응답 결정
        bot_response = None
        additional_data = {}
        
        if next_action == 'faq_search':
            # FAQ 검색 수행
            faq_query = entities.get('query', conversation.messages[-1].content)
            faq_result = faq_manager.search_faq(faq_query)
            
            if faq_result.faq_items and faq_result.confidence_score > 0.7:
                bot_response = faq_result.faq_items[0].answer
                additional_data['faq_match'] = True
            else:
                bot_response = "관련 정보를 찾지 못했습니다. 다른 질문이 있으시면 말씀해 주세요."
        
        elif next_action == 'scenario_flow':
            # 시나리오 플로우 실행
            scenario_id = _map_intent_to_scenario(intent)
            if scenario_id:
                scenario_result = scenario_manager.start_scenario(
                    session.get('session_id'), scenario_id, entities
                )
                bot_response = scenario_result.get('message')
                additional_data['scenario_started'] = scenario_id
        
        elif next_action == 'escalate':
            # 자동 에스컬레이션 체크
            conversation_history = [msg.to_dict() for msg in conversation.messages]
            customer_data = conversation.context.get('customer_data', {})
            
            auto_escalation = escalation_service.handle_auto_escalation(
                conversation_history, customer_data, session.get('session_id')
            )
            
            if auto_escalation and auto_escalation['success']:
                bot_response = auto_escalation['message']
                additional_data['escalated'] = True
                additional_data['escalation_id'] = auto_escalation['escalation_id']
            else:
                bot_response = nlu_result['response_text']
        
        else:
            # 기본 응답
            bot_response = nlu_result['response_text']
        
        # 봇 응답 저장
        if bot_response:
            conversation_service.send_bot_message(
                conversation.conversation_id, 
                bot_response,
                {'intent': intent, 'confidence': confidence, 'entities': entities}
            )
        
        # 컨텍스트 업데이트
        for key, value in nlu_result.get('session_attributes', {}).items():
            conversation.update_context(key, value)
        
        return {
            'success': True,
            'response': bot_response,
            'intent': intent,
            'confidence': confidence,
            'entities': entities,
            'next_action': next_action,
            'sentiment': nlu_result.get('sentiment'),
            'timestamp': datetime.now().isoformat(),
            **additional_data
        }
        
    except Exception as e:
        logger.error(f"NLU 결과 처리 오류: {str(e)}")
        return {
            'success': False,
            'error': 'NLU 결과를 처리할 수 없습니다.',
            'response': '죄송합니다. 일시적인 오류가 발생했습니다.'
        }

def _map_intent_to_scenario(intent):
    """의도를 시나리오에 매핑"""
    mapping = {
        'product_inquiry': 'product_inquiry',
        'reservation': 'reservation',
        'cancel_request': 'cancellation',
        'technical_support': 'tech_support'
    }
    return mapping.get(intent)

@app.errorhandler(404)
def not_found(error):
    """404 에러 핸들러"""
    return jsonify({
        'success': False,
        'error': 'API 엔드포인트를 찾을 수 없습니다.',
        'timestamp': datetime.now().isoformat()
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """500 에러 핸들러"""
    logger.error(f"내부 서버 오류: {str(error)}")
    return jsonify({
        'success': False,
        'error': '내부 서버 오류가 발생했습니다.',
        'timestamp': datetime.now().isoformat()
    }), 500

if __name__ == '__main__':
    app.run(
        host=Config.get('API_HOST', '0.0.0.0'),
        port=Config.get('API_PORT', 8000),
        debug=Config.get('DEBUG', False)
    ) 