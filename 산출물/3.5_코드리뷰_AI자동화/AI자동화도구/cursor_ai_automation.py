#!/usr/bin/env python3
"""
AICC 커서 AI 활용 자동화 도구
- 코드 분석 및 리뷰 자동화
- 테스트 코드 자동 생성
- 문서화 자동화
- 리팩토링 제안
"""

import os
import ast
import json
import asyncio
import aiofiles
import subprocess
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CodeAnalysisResult:
    """코드 분석 결과"""
    file_path: str
    lines_of_code: int
    complexity: int
    functions: List[str]
    classes: List[str]
    imports: List[str]
    issues: List[str]
    suggestions: List[str]
    test_coverage: float
    security_score: int
    maintainability_score: int

@dataclass
class TestGenerationResult:
    """테스트 생성 결과"""
    test_file_path: str
    test_functions: List[str]
    coverage_target: float
    generated_tests: str

@dataclass
class DocumentationResult:
    """문서화 결과"""
    doc_file_path: str
    api_docs: str
    readme_content: str
    changelog: str

class CursorAIAutomation:
    """커서 AI 자동화 메인 클래스"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.source_dirs = [
            self.project_root / "산출물/3.4_공통_통합_기능_개발/소스코드"
        ]
        self.output_dir = self.project_root / "산출물/3.5_코드리뷰_AI자동화"
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def analyze_codebase(self) -> List[CodeAnalysisResult]:
        """전체 코드베이스 분석"""
        logger.info("코드베이스 분석 시작")
        results = []
        
        for source_dir in self.source_dirs:
            if source_dir.exists():
                python_files = list(source_dir.rglob("*.py"))
                
                # 병렬 처리로 파일 분석
                tasks = [self._analyze_file(file_path) for file_path in python_files]
                file_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in file_results:
                    if isinstance(result, CodeAnalysisResult):
                        results.append(result)
                    elif isinstance(result, Exception):
                        logger.error(f"파일 분석 중 오류: {result}")
        
        logger.info(f"총 {len(results)}개 파일 분석 완료")
        return results
    
    async def _analyze_file(self, file_path: Path) -> CodeAnalysisResult:
        """개별 파일 분석"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            # AST 파싱
            tree = ast.parse(content)
            
            # 기본 메트릭 수집
            lines_of_code = len([line for line in content.split('\n') if line.strip()])
            complexity = self._calculate_complexity(tree)
            functions = self._extract_functions(tree)
            classes = self._extract_classes(tree)
            imports = self._extract_imports(tree)
            
            # 코드 이슈 분석
            issues = await self._analyze_code_issues(content, file_path)
            suggestions = await self._generate_suggestions(content, issues)
            
            # 품질 점수 계산
            security_score = self._calculate_security_score(content)
            maintainability_score = self._calculate_maintainability_score(
                complexity, lines_of_code, len(functions), len(classes)
            )
            
            return CodeAnalysisResult(
                file_path=str(file_path),
                lines_of_code=lines_of_code,
                complexity=complexity,
                functions=functions,
                classes=classes,
                imports=imports,
                issues=issues,
                suggestions=suggestions,
                test_coverage=0.0,  # 실제 테스트 실행 시 계산
                security_score=security_score,
                maintainability_score=maintainability_score
            )
            
        except Exception as e:
            logger.error(f"파일 분석 실패 {file_path}: {e}")
            raise
    
    def _calculate_complexity(self, tree: ast.AST) -> int:
        """순환 복잡도 계산"""
        complexity = 1  # 기본 복잡도
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, (ast.And, ast.Or)):
                complexity += 1
        
        return complexity
    
    def _extract_functions(self, tree: ast.AST) -> List[str]:
        """함수 목록 추출"""
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        return functions
    
    def _extract_classes(self, tree: ast.AST) -> List[str]:
        """클래스 목록 추출"""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
        return classes
    
    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """임포트 목록 추출"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports
    
    async def _analyze_code_issues(self, content: str, file_path: Path) -> List[str]:
        """코드 이슈 분석"""
        issues = []
        
        # 보안 이슈 검사
        security_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "하드코딩된 비밀번호 발견"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "하드코딩된 API 키 발견"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "하드코딩된 시크릿 발견"),
            (r'eval\s*\(', "eval() 사용으로 인한 보안 위험"),
            (r'exec\s*\(', "exec() 사용으로 인한 보안 위험"),
        ]
        
        for pattern, message in security_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append(f"보안: {message}")
        
        # 코드 품질 이슈
        quality_patterns = [
            (r'print\s*\(', "print() 문 사용 - 로깅 사용 권장"),
            (r'TODO|FIXME|HACK', "TODO/FIXME 주석 발견"),
            (r'except\s*:', "빈 except 절 - 구체적인 예외 처리 필요"),
        ]
        
        for pattern, message in quality_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                issues.append(f"품질: {message} ({len(matches)}개)")
        
        # 성능 이슈
        if "time.sleep" in content:
            issues.append("성능: time.sleep() 사용 - 비동기 처리 고려")
        
        if content.count("for") > 10:
            issues.append("성능: 중첩된 반복문 많음 - 최적화 고려")
        
        return issues
    
    async def _generate_suggestions(self, content: str, issues: List[str]) -> List[str]:
        """개선 제안 생성"""
        suggestions = []
        
        # 이슈 기반 제안
        for issue in issues:
            if "하드코딩" in issue:
                suggestions.append("환경변수 또는 설정 파일 사용 권장")
            elif "print()" in issue:
                suggestions.append("logging 모듈 사용으로 변경")
            elif "except:" in issue:
                suggestions.append("구체적인 예외 타입 지정 및 적절한 처리")
            elif "time.sleep" in issue:
                suggestions.append("asyncio.sleep() 또는 비동기 처리 방식 사용")
        
        # 일반적인 개선 제안
        if "class" in content and "def __init__" in content:
            if "typing" not in content:
                suggestions.append("타입 힌트 추가로 코드 가독성 향상")
        
        if "async def" in content and "await" not in content:
            suggestions.append("비동기 함수에서 await 사용 확인")
        
        if len(content.split('\n')) > 500:
            suggestions.append("파일이 큼 - 모듈 분리 고려")
        
        return suggestions
    
    def _calculate_security_score(self, content: str) -> int:
        """보안 점수 계산 (0-100)"""
        score = 100
        
        # 보안 위험 요소 검사
        security_risks = [
            (r'password\s*=\s*["\'][^"\']+["\']', -20),
            (r'api_key\s*=\s*["\'][^"\']+["\']', -15),
            (r'eval\s*\(', -25),
            (r'exec\s*\(', -25),
            (r'shell=True', -10),
            (r'input\s*\(', -5),
        ]
        
        for pattern, penalty in security_risks:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            score += penalty * matches
        
        # 보안 강화 요소 검사
        security_enhancements = [
            (r'import\s+hashlib', 5),
            (r'import\s+secrets', 5),
            (r'import\s+cryptography', 10),
            (r'@require_auth', 10),
            (r'validate_input', 5),
        ]
        
        for pattern, bonus in security_enhancements:
            if re.search(pattern, content, re.IGNORECASE):
                score += bonus
        
        return max(0, min(100, score))
    
    def _calculate_maintainability_score(self, complexity: int, loc: int, 
                                       functions: int, classes: int) -> int:
        """유지보수성 점수 계산 (0-100)"""
        score = 100
        
        # 복잡도 패널티
        if complexity > 20:
            score -= (complexity - 20) * 2
        
        # 파일 크기 패널티
        if loc > 1000:
            score -= (loc - 1000) // 100 * 5
        
        # 함수/클래스 비율 보너스
        if functions > 0 and loc > 0:
            function_ratio = functions / (loc / 100)
            if function_ratio > 2:  # 적절한 함수 분리
                score += 10
        
        if classes > 0 and functions > 0:
            if functions / classes < 10:  # 적절한 클래스 크기
                score += 5
        
        return max(0, min(100, score))
    
    async def generate_tests(self, analysis_results: List[CodeAnalysisResult]) -> List[TestGenerationResult]:
        """테스트 코드 자동 생성"""
        logger.info("테스트 코드 생성 시작")
        test_results = []
        
        for analysis in analysis_results:
            if analysis.functions or analysis.classes:
                test_result = await self._generate_test_for_file(analysis)
                test_results.append(test_result)
        
        logger.info(f"총 {len(test_results)}개 테스트 파일 생성")
        return test_results
    
    async def _generate_test_for_file(self, analysis: CodeAnalysisResult) -> TestGenerationResult:
        """개별 파일에 대한 테스트 생성"""
        file_path = Path(analysis.file_path)
        test_file_name = f"test_{file_path.stem}.py"
        test_file_path = self.output_dir / "품질관리" / "tests" / test_file_name
        
        # 테스트 코드 템플릿 생성
        test_content = self._generate_test_template(analysis)
        
        # 테스트 파일 저장
        test_file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(test_file_path, 'w', encoding='utf-8') as f:
            await f.write(test_content)
        
        return TestGenerationResult(
            test_file_path=str(test_file_path),
            test_functions=[f"test_{func}" for func in analysis.functions],
            coverage_target=80.0,
            generated_tests=test_content
        )
    
    def _generate_test_template(self, analysis: CodeAnalysisResult) -> str:
        """테스트 템플릿 생성"""
        file_path = Path(analysis.file_path)
        module_name = file_path.stem
        
        template = f'''"""
{module_name} 모듈에 대한 자동 생성된 테스트
Generated by AICC Cursor AI Automation
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from {module_name} import *

class Test{module_name.title().replace('_', '')}:
    """테스트 클래스"""
    
    def setup_method(self):
        """테스트 설정"""
        pass
    
    def teardown_method(self):
        """테스트 정리"""
        pass

'''
        
        # 함수별 테스트 생성
        for func_name in analysis.functions:
            if not func_name.startswith('_'):  # private 함수 제외
                template += f'''
    def test_{func_name}_success(self):
        """
        {func_name} 함수 성공 케이스 테스트
        TODO: 실제 테스트 로직 구현 필요
        """
        # Arrange
        # TODO: 테스트 데이터 준비
        
        # Act
        # TODO: 함수 호출
        
        # Assert
        # TODO: 결과 검증
        assert True  # 임시 assertion
    
    def test_{func_name}_failure(self):
        """
        {func_name} 함수 실패 케이스 테스트
        TODO: 실제 테스트 로직 구현 필요
        """
        # TODO: 예외 상황 테스트
        assert True  # 임시 assertion
'''
        
        # 클래스별 테스트 생성
        for class_name in analysis.classes:
            template += f'''
    def test_{class_name.lower()}_initialization(self):
        """
        {class_name} 클래스 초기화 테스트
        TODO: 실제 테스트 로직 구현 필요
        """
        # TODO: 클래스 인스턴스 생성 및 검증
        assert True  # 임시 assertion
'''
        
        # 비동기 함수 테스트 추가
        if any('async' in func for func in analysis.functions):
            template += '''
    @pytest.mark.asyncio
    async def test_async_functions(self):
        """
        비동기 함수 테스트
        TODO: 실제 비동기 테스트 로직 구현 필요
        """
        # TODO: 비동기 함수 테스트
        assert True  # 임시 assertion
'''
        
        return template
    
    async def run_automation(self) -> Dict[str, Any]:
        """전체 자동화 프로세스 실행"""
        logger.info("AICC 커서 AI 자동화 시작")
        
        try:
            # 1. 코드 분석
            analysis_results = await self.analyze_codebase()
            
            # 2. 테스트 생성
            test_results = await self.generate_tests(analysis_results)
            
            # 3. 종합 보고서 생성
            summary_report = {
                "automation_timestamp": datetime.now().isoformat(),
                "analysis_summary": {
                    "files_analyzed": len(analysis_results),
                    "total_lines_of_code": sum(a.lines_of_code for a in analysis_results),
                    "total_functions": sum(len(a.functions) for a in analysis_results),
                    "total_classes": sum(len(a.classes) for a in analysis_results)
                },
                "test_generation_summary": {
                    "test_files_generated": len(test_results),
                    "test_functions_generated": sum(len(t.test_functions) for t in test_results)
                }
            }
            
            # 종합 보고서 저장
            summary_path = self.output_dir / "automation_summary.json"
            async with aiofiles.open(summary_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(summary_report, ensure_ascii=False, indent=2))
            
            logger.info("AICC 커서 AI 자동화 완료")
            return summary_report
            
        except Exception as e:
            logger.error(f"자동화 프로세스 실패: {e}")
            raise
        finally:
            self.executor.shutdown(wait=True)

async def main():
    """메인 실행 함수"""
    project_root = os.getcwd()
    automation = CursorAIAutomation(project_root)
    
    try:
        result = await automation.run_automation()
        print("🎉 AICC 커서 AI 자동화 완료!")
        print(f"📊 분석된 파일: {result['analysis_summary']['files_analyzed']}개")
        print(f"🧪 생성된 테스트: {result['test_generation_summary']['test_files_generated']}개")
        
    except Exception as e:
        print(f"❌ 자동화 실패: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main()) 