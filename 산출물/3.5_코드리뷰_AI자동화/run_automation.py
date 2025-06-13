#!/usr/bin/env python3
"""
AICC 3.5 코드 리뷰 및 커서 AI 활용 자동화 메인 실행기
- 코드 분석 및 리뷰
- 테스트 자동화
- 품질 검사
- 문서화 생성
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
import logging

# 현재 디렉토리를 Python 경로에 추가
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 모듈 임포트
try:
    from AI자동화도구.cursor_ai_automation import CursorAIAutomation
    from 품질관리.test_automation import TestAutomation
    from 문서화.doc_generator import DocumentationGenerator
except ImportError as e:
    print(f"모듈 임포트 실패: {e}")
    print("필요한 파일들이 생성되지 않았을 수 있습니다.")
    sys.exit(1)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('automation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AIAutomationRunner:
    """AI 자동화 실행기"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.output_dir = self.project_root / "산출물/3.5_코드리뷰_AI자동화"
        
    async def run_full_automation(self) -> dict:
        """전체 자동화 프로세스 실행"""
        logger.info("🚀 AICC 3.5 코드 리뷰 및 AI 자동화 시작")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "stages": {}
        }
        
        try:
            # 1. 코드 분석 및 리뷰
            logger.info("📊 1단계: 코드 분석 및 리뷰")
            cursor_automation = CursorAIAutomation(str(self.project_root))
            analysis_result = await cursor_automation.run_automation()
            results["stages"]["code_analysis"] = {
                "status": "completed",
                "files_analyzed": analysis_result["analysis_summary"]["files_analyzed"],
                "tests_generated": analysis_result["test_generation_summary"]["test_files_generated"]
            }
            logger.info("✅ 코드 분석 완료")
            
            # 2. 테스트 자동화
            logger.info("🧪 2단계: 테스트 자동화")
            test_automation = TestAutomation(str(self.project_root))
            test_result = await test_automation.run_all_tests()
            results["stages"]["test_automation"] = {
                "status": "completed",
                "total_tests": test_result.total_tests,
                "passed_tests": test_result.passed_tests,
                "coverage": f"{test_result.overall_coverage:.1f}%"
            }
            logger.info("✅ 테스트 자동화 완료")
            
            # 3. 문서화 생성
            logger.info("📚 3단계: 문서화 생성")
            doc_generator = DocumentationGenerator(str(self.project_root))
            doc_result = await doc_generator.generate_documentation()
            results["stages"]["documentation"] = {
                "status": "completed",
                "services_documented": len(doc_result.services),
                "documents_generated": 4  # API, README, CHANGELOG, ARCHITECTURE
            }
            logger.info("✅ 문서화 생성 완료")
            
            # 4. 종합 보고서 생성
            logger.info("📋 4단계: 종합 보고서 생성")
            await self._generate_summary_report(results, analysis_result, test_result, doc_result)
            results["stages"]["summary_report"] = {
                "status": "completed",
                "report_path": str(self.output_dir / "automation_summary.html")
            }
            logger.info("✅ 종합 보고서 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 자동화 프로세스 실패: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
            raise
        
        logger.info("🎉 AICC 3.5 자동화 프로세스 완료!")
        return results
    
    async def run_code_analysis_only(self) -> dict:
        """코드 분석만 실행"""
        logger.info("📊 코드 분석 실행")
        cursor_automation = CursorAIAutomation(str(self.project_root))
        return await cursor_automation.run_automation()
    
    async def run_test_automation_only(self) -> dict:
        """테스트 자동화만 실행"""
        logger.info("🧪 테스트 자동화 실행")
        test_automation = TestAutomation(str(self.project_root))
        result = await test_automation.run_all_tests()
        return {
            "total_tests": result.total_tests,
            "passed_tests": result.passed_tests,
            "failed_tests": result.failed_tests,
            "coverage": result.overall_coverage
        }
    
    async def run_documentation_only(self) -> dict:
        """문서화만 실행"""
        logger.info("📚 문서화 생성 실행")
        doc_generator = DocumentationGenerator(str(self.project_root))
        result = await doc_generator.generate_documentation()
        return {
            "services_documented": len(result.services),
            "timestamp": result.timestamp
        }
    
    async def _generate_summary_report(self, results: dict, analysis_result: dict, 
                                     test_result, doc_result) -> None:
        """종합 보고서 생성"""
        
        # HTML 보고서 생성
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AICC 3.5 자동화 종합 보고서</title>
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .container {{ 
            max-width: 1200px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 15px; 
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{ 
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white; 
            padding: 40px; 
            text-align: center; 
        }}
        .header h1 {{ 
            margin: 0; 
            font-size: 2.5em; 
            font-weight: 300;
        }}
        .header p {{ 
            margin: 10px 0 0 0; 
            opacity: 0.8; 
            font-size: 1.1em;
        }}
        .content {{ 
            padding: 40px; 
        }}
        .stage-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); 
            gap: 30px; 
            margin: 30px 0; 
        }}
        .stage-card {{ 
            background: #f8f9fa; 
            border-radius: 10px; 
            padding: 25px; 
            border-left: 5px solid #28a745;
            transition: transform 0.3s ease;
        }}
        .stage-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }}
        .stage-card h3 {{ 
            margin: 0 0 15px 0; 
            color: #2c3e50; 
            font-size: 1.3em;
        }}
        .stage-card .emoji {{ 
            font-size: 2em; 
            margin-bottom: 10px; 
            display: block;
        }}
        .metrics {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 20px; 
            margin: 30px 0; 
        }}
        .metric {{ 
            text-align: center; 
            padding: 20px; 
            background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
            color: white; 
            border-radius: 10px;
        }}
        .metric-value {{ 
            font-size: 2.5em; 
            font-weight: bold; 
            margin-bottom: 5px;
        }}
        .metric-label {{ 
            font-size: 0.9em; 
            opacity: 0.9;
        }}
        .summary {{ 
            background: #e8f5e8; 
            border-radius: 10px; 
            padding: 25px; 
            margin: 30px 0;
            border-left: 5px solid #28a745;
        }}
        .footer {{ 
            text-align: center; 
            padding: 30px; 
            background: #f8f9fa; 
            color: #6c757d;
            border-top: 1px solid #dee2e6;
        }}
        .status-badge {{ 
            display: inline-block; 
            padding: 5px 15px; 
            border-radius: 20px; 
            font-size: 0.9em; 
            font-weight: bold;
        }}
        .status-success {{ 
            background: #d4edda; 
            color: #155724; 
        }}
        .progress-bar {{ 
            background: #e9ecef; 
            border-radius: 10px; 
            overflow: hidden; 
            height: 8px; 
            margin: 10px 0;
        }}
        .progress-fill {{ 
            background: linear-gradient(90deg, #28a745, #20c997); 
            height: 100%; 
            transition: width 0.3s ease;
        }}
        table {{ 
            width: 100%; 
            border-collapse: collapse; 
            margin: 20px 0; 
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        th, td {{ 
            padding: 15px; 
            text-align: left; 
            border-bottom: 1px solid #dee2e6;
        }}
        th {{ 
            background: #f8f9fa; 
            font-weight: 600;
            color: #495057;
        }}
        .highlight {{ 
            background: linear-gradient(120deg, #a8edea 0%, #fed6e3 100%);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 AICC 3.5 자동화 보고서</h1>
            <p>코드 리뷰 및 커서 AI 활용 자동화 결과</p>
            <span class="status-badge status-success">✅ 완료</span>
        </div>
        
        <div class="content">
            <div class="highlight">
                <h2>📊 전체 요약</h2>
                <p><strong>실행 시간:</strong> {results['timestamp']}</p>
                <p><strong>상태:</strong> {results['status'].upper()}</p>
                <p><strong>완료된 단계:</strong> {len([s for s in results['stages'].values() if s['status'] == 'completed'])}/4</p>
            </div>
            
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value">{analysis_result['analysis_summary']['files_analyzed']}</div>
                    <div class="metric-label">분석된 파일</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{test_result.total_tests}</div>
                    <div class="metric-label">실행된 테스트</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{test_result.overall_coverage:.1f}%</div>
                    <div class="metric-label">테스트 커버리지</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{len(doc_result.services)}</div>
                    <div class="metric-label">문서화된 서비스</div>
                </div>
            </div>
            
            <h2>🔄 실행 단계</h2>
            <div class="stage-grid">
                <div class="stage-card">
                    <span class="emoji">📊</span>
                    <h3>코드 분석 및 리뷰</h3>
                    <p><strong>상태:</strong> <span class="status-badge status-success">완료</span></p>
                    <p><strong>분석된 파일:</strong> {analysis_result['analysis_summary']['files_analyzed']}개</p>
                    <p><strong>생성된 테스트:</strong> {analysis_result['test_generation_summary']['test_files_generated']}개</p>
                    <p><strong>총 코드 라인:</strong> {analysis_result['analysis_summary']['total_lines_of_code']:,}줄</p>
                </div>
                
                <div class="stage-card">
                    <span class="emoji">🧪</span>
                    <h3>테스트 자동화</h3>
                    <p><strong>상태:</strong> <span class="status-badge status-success">완료</span></p>
                    <p><strong>총 테스트:</strong> {test_result.total_tests}개</p>
                    <p><strong>통과:</strong> {test_result.passed_tests}개</p>
                    <p><strong>실패:</strong> {test_result.failed_tests}개</p>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {(test_result.passed_tests/test_result.total_tests*100) if test_result.total_tests > 0 else 0}%"></div>
                    </div>
                </div>
                
                <div class="stage-card">
                    <span class="emoji">📚</span>
                    <h3>문서화 생성</h3>
                    <p><strong>상태:</strong> <span class="status-badge status-success">완료</span></p>
                    <p><strong>서비스:</strong> {len(doc_result.services)}개</p>
                    <p><strong>생성된 문서:</strong> 4개</p>
                    <p><strong>API 엔드포인트:</strong> {sum(len(service.endpoints) for service in doc_result.services)}개</p>
                </div>
                
                <div class="stage-card">
                    <span class="emoji">📋</span>
                    <h3>종합 보고서</h3>
                    <p><strong>상태:</strong> <span class="status-badge status-success">완료</span></p>
                    <p><strong>HTML 보고서:</strong> ✅</p>
                    <p><strong>JSON 데이터:</strong> ✅</p>
                    <p><strong>로그 파일:</strong> ✅</p>
                </div>
            </div>
            
            <h2>📈 상세 결과</h2>
            
            <h3>코드 분석 결과</h3>
            <table>
                <tr>
                    <th>항목</th>
                    <th>값</th>
                    <th>설명</th>
                </tr>
                <tr>
                    <td>분석된 파일</td>
                    <td>{analysis_result['analysis_summary']['files_analyzed']}개</td>
                    <td>Python 소스 파일</td>
                </tr>
                <tr>
                    <td>총 코드 라인</td>
                    <td>{analysis_result['analysis_summary']['total_lines_of_code']:,}줄</td>
                    <td>주석 및 빈 줄 포함</td>
                </tr>
                <tr>
                    <td>총 함수</td>
                    <td>{analysis_result['analysis_summary']['total_functions']}개</td>
                    <td>일반 함수 + 비동기 함수</td>
                </tr>
                <tr>
                    <td>총 클래스</td>
                    <td>{analysis_result['analysis_summary']['total_classes']}개</td>
                    <td>사용자 정의 클래스</td>
                </tr>
            </table>
            
            <h3>테스트 결과</h3>
            <table>
                <tr>
                    <th>항목</th>
                    <th>값</th>
                    <th>비율</th>
                </tr>
                <tr>
                    <td>총 테스트</td>
                    <td>{test_result.total_tests}개</td>
                    <td>100%</td>
                </tr>
                <tr>
                    <td>통과한 테스트</td>
                    <td>{test_result.passed_tests}개</td>
                    <td>{(test_result.passed_tests/test_result.total_tests*100) if test_result.total_tests > 0 else 0:.1f}%</td>
                </tr>
                <tr>
                    <td>실패한 테스트</td>
                    <td>{test_result.failed_tests}개</td>
                    <td>{(test_result.failed_tests/test_result.total_tests*100) if test_result.total_tests > 0 else 0:.1f}%</td>
                </tr>
                <tr>
                    <td>건너뛴 테스트</td>
                    <td>{test_result.skipped_tests}개</td>
                    <td>{(test_result.skipped_tests/test_result.total_tests*100) if test_result.total_tests > 0 else 0:.1f}%</td>
                </tr>
            </table>
            
            <div class="summary">
                <h3>🎯 주요 성과</h3>
                <ul>
                    <li><strong>코드 품질 향상:</strong> 자동화된 코드 분석으로 품질 이슈 조기 발견</li>
                    <li><strong>테스트 자동화:</strong> {test_result.total_tests}개의 테스트 케이스 자동 생성 및 실행</li>
                    <li><strong>문서화 완성:</strong> API 문서, README, 아키텍처 문서 자동 생성</li>
                    <li><strong>개발 효율성:</strong> 수동 작업 시간 대폭 단축</li>
                </ul>
            </div>
            
            <div class="summary">
                <h3>📋 다음 단계 권장사항</h3>
                <ul>
                    <li>실패한 테스트 케이스 검토 및 수정</li>
                    <li>코드 커버리지 {test_result.overall_coverage:.1f}% → 80% 이상 목표</li>
                    <li>정기적인 자동화 실행 스케줄 설정</li>
                    <li>CI/CD 파이프라인에 자동화 도구 통합</li>
                </ul>
            </div>
        </div>
        
        <div class="footer">
            <p>🤖 AICC 커서 AI 자동화 시스템 | 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>이 보고서는 자동으로 생성되었습니다.</p>
        </div>
    </div>
</body>
</html>
"""
        
        # HTML 보고서 저장
        html_path = self.output_dir / "automation_summary.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # JSON 보고서 저장
        import json
        json_path = self.output_dir / "automation_summary.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"종합 보고서 저장: {html_path}")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='AICC 3.5 자동화 실행기')
    parser.add_argument('--mode', choices=['full', 'analysis', 'test', 'docs'], 
                       default='full', help='실행 모드 선택')
    parser.add_argument('--project-root', default='.', help='프로젝트 루트 디렉토리')
    
    args = parser.parse_args()
    
    project_root = os.path.abspath(args.project_root)
    runner = AIAutomationRunner(project_root)
    
    async def run_automation():
        try:
            if args.mode == 'full':
                print("🚀 전체 자동화 프로세스 시작...")
                result = await runner.run_full_automation()
                
                print("\n🎉 자동화 완료!")
                print(f"📊 분석된 파일: {result['stages']['code_analysis']['files_analyzed']}개")
                print(f"🧪 실행된 테스트: {result['stages']['test_automation']['total_tests']}개")
                print(f"📚 문서화된 서비스: {result['stages']['documentation']['services_documented']}개")
                print(f"📋 보고서: {result['stages']['summary_report']['report_path']}")
                
            elif args.mode == 'analysis':
                print("📊 코드 분석 시작...")
                result = await runner.run_code_analysis_only()
                print(f"✅ 분석 완료: {result['analysis_summary']['files_analyzed']}개 파일")
                
            elif args.mode == 'test':
                print("🧪 테스트 자동화 시작...")
                result = await runner.run_test_automation_only()
                print(f"✅ 테스트 완료: {result['passed_tests']}/{result['total_tests']} 통과")
                
            elif args.mode == 'docs':
                print("📚 문서화 시작...")
                result = await runner.run_documentation_only()
                print(f"✅ 문서화 완료: {result['services_documented']}개 서비스")
                
        except Exception as e:
            print(f"❌ 실행 실패: {e}")
            logger.exception("자동화 실행 중 오류 발생")
            return 1
        
        return 0
    
    return asyncio.run(run_automation())

if __name__ == "__main__":
    sys.exit(main()) 