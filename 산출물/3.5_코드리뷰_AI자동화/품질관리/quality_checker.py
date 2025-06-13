#!/usr/bin/env python3
"""
AICC 코드 품질 검사 도구
- 정적 코드 분석
- 보안 취약점 검사
- 성능 분석
- 코딩 스타일 검사
"""

import os
import ast
import json
import subprocess
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import re
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class QualityIssue:
    """품질 이슈"""
    file_path: str
    line_number: int
    issue_type: str  # security, performance, style, bug
    severity: str    # critical, high, medium, low
    message: str
    suggestion: str

@dataclass
class QualityReport:
    """품질 보고서"""
    timestamp: str
    total_files: int
    total_lines: int
    issues: List[QualityIssue]
    scores: Dict[str, float]
    grade: str
    recommendations: List[str]

class CodeQualityChecker:
    """코드 품질 검사기"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.source_dirs = [
            self.project_root / "산출물/3.4_공통_통합_기능_개발/소스코드"
        ]
        
    async def run_quality_check(self) -> QualityReport:
        """품질 검사 실행"""
        logger.info("코드 품질 검사 시작")
        
        all_issues = []
        total_files = 0
        total_lines = 0
        
        for source_dir in self.source_dirs:
            if source_dir.exists():
                python_files = list(source_dir.rglob("*.py"))
                total_files += len(python_files)
                
                for file_path in python_files:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        total_lines += len(content.split('\n'))
                        
                        # 각종 검사 실행
                        security_issues = await self._check_security(file_path, content)
                        performance_issues = await self._check_performance(file_path, content)
                        style_issues = await self._check_style(file_path, content)
                        bug_issues = await self._check_bugs(file_path, content)
                        
                        all_issues.extend(security_issues)
                        all_issues.extend(performance_issues)
                        all_issues.extend(style_issues)
                        all_issues.extend(bug_issues)
                        
                    except Exception as e:
                        logger.error(f"파일 검사 실패 {file_path}: {e}")
        
        # 점수 계산
        scores = self._calculate_scores(all_issues, total_files, total_lines)
        grade = self._calculate_grade(scores)
        recommendations = self._generate_recommendations(all_issues)
        
        report = QualityReport(
            timestamp=datetime.now().isoformat(),
            total_files=total_files,
            total_lines=total_lines,
            issues=all_issues,
            scores=scores,
            grade=grade,
            recommendations=recommendations
        )
        
        # 보고서 저장
        await self._save_report(report)
        
        logger.info(f"품질 검사 완료 - 등급: {grade}")
        return report
    
    async def _check_security(self, file_path: Path, content: str) -> List[QualityIssue]:
        """보안 검사"""
        issues = []
        lines = content.split('\n')
        
        security_patterns = [
            {
                'pattern': r'password\s*=\s*["\'][^"\']+["\']',
                'severity': 'critical',
                'message': '하드코딩된 비밀번호 발견',
                'suggestion': '환경변수나 보안 저장소 사용'
            },
            {
                'pattern': r'api_key\s*=\s*["\'][^"\']+["\']',
                'severity': 'critical',
                'message': '하드코딩된 API 키 발견',
                'suggestion': '환경변수나 AWS Secrets Manager 사용'
            },
            {
                'pattern': r'secret\s*=\s*["\'][^"\']+["\']',
                'severity': 'critical',
                'message': '하드코딩된 시크릿 발견',
                'suggestion': '보안 저장소 사용'
            },
            {
                'pattern': r'eval\s*\(',
                'severity': 'high',
                'message': 'eval() 사용으로 인한 코드 인젝션 위험',
                'suggestion': '안전한 대안 함수 사용'
            },
            {
                'pattern': r'exec\s*\(',
                'severity': 'high',
                'message': 'exec() 사용으로 인한 코드 인젝션 위험',
                'suggestion': '안전한 대안 함수 사용'
            },
            {
                'pattern': r'shell=True',
                'severity': 'medium',
                'message': 'shell=True 사용으로 인한 명령어 인젝션 위험',
                'suggestion': 'shell=False 사용 또는 입력 검증'
            },
            {
                'pattern': r'pickle\.loads?\(',
                'severity': 'medium',
                'message': 'pickle 사용으로 인한 역직렬화 공격 위험',
                'suggestion': 'json 또는 안전한 직렬화 방식 사용'
            }
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern_info in security_patterns:
                if re.search(pattern_info['pattern'], line, re.IGNORECASE):
                    issues.append(QualityIssue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type='security',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        suggestion=pattern_info['suggestion']
                    ))
        
        return issues
    
    async def _check_performance(self, file_path: Path, content: str) -> List[QualityIssue]:
        """성능 검사"""
        issues = []
        lines = content.split('\n')
        
        performance_patterns = [
            {
                'pattern': r'time\.sleep\(',
                'severity': 'medium',
                'message': 'time.sleep() 사용으로 인한 블로킹',
                'suggestion': 'asyncio.sleep() 사용'
            },
            {
                'pattern': r'\.append\(.*\)\s*$',
                'severity': 'low',
                'message': '반복문에서 append() 사용',
                'suggestion': '리스트 컴프리헨션 고려'
            },
            {
                'pattern': r'for.*in.*\.keys\(\):',
                'severity': 'low',
                'message': '불필요한 .keys() 사용',
                'suggestion': '직접 딕셔너리 순회'
            }
        ]
        
        # 중첩 반복문 검사
        nested_loops = 0
        for i, line in enumerate(lines, 1):
            if re.search(r'^\s*for\s+', line):
                # 다음 줄들에서 또 다른 for문 찾기
                indent_level = len(line) - len(line.lstrip())
                for j in range(i, min(i + 20, len(lines))):
                    next_line = lines[j]
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent > indent_level and re.search(r'^\s*for\s+', next_line):
                        nested_loops += 1
                        issues.append(QualityIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type='performance',
                            severity='medium',
                            message='중첩된 반복문 발견',
                            suggestion='알고리즘 최적화 고려'
                        ))
                        break
        
        for i, line in enumerate(lines, 1):
            for pattern_info in performance_patterns:
                if re.search(pattern_info['pattern'], line):
                    issues.append(QualityIssue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type='performance',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        suggestion=pattern_info['suggestion']
                    ))
        
        return issues
    
    async def _check_style(self, file_path: Path, content: str) -> List[QualityIssue]:
        """스타일 검사"""
        issues = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # 긴 줄 검사
            if len(line) > 120:
                issues.append(QualityIssue(
                    file_path=str(file_path),
                    line_number=i,
                    issue_type='style',
                    severity='low',
                    message=f'긴 줄 ({len(line)}자)',
                    suggestion='120자 이내로 줄 나누기'
                ))
            
            # 탭 사용 검사
            if '\t' in line:
                issues.append(QualityIssue(
                    file_path=str(file_path),
                    line_number=i,
                    issue_type='style',
                    severity='low',
                    message='탭 문자 사용',
                    suggestion='스페이스 4개 사용'
                ))
            
            # 후행 공백 검사
            if line.endswith(' ') or line.endswith('\t'):
                issues.append(QualityIssue(
                    file_path=str(file_path),
                    line_number=i,
                    issue_type='style',
                    severity='low',
                    message='후행 공백 발견',
                    suggestion='후행 공백 제거'
                ))
        
        # 함수/클래스 명명 규칙 검사
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not re.match(r'^[a-z_][a-z0-9_]*$', node.name):
                        issues.append(QualityIssue(
                            file_path=str(file_path),
                            line_number=node.lineno,
                            issue_type='style',
                            severity='low',
                            message=f'함수명 규칙 위반: {node.name}',
                            suggestion='snake_case 사용'
                        ))
                
                elif isinstance(node, ast.ClassDef):
                    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                        issues.append(QualityIssue(
                            file_path=str(file_path),
                            line_number=node.lineno,
                            issue_type='style',
                            severity='low',
                            message=f'클래스명 규칙 위반: {node.name}',
                            suggestion='PascalCase 사용'
                        ))
        except SyntaxError:
            pass
        
        return issues
    
    async def _check_bugs(self, file_path: Path, content: str) -> List[QualityIssue]:
        """버그 검사"""
        issues = []
        lines = content.split('\n')
        
        bug_patterns = [
            {
                'pattern': r'except\s*:',
                'severity': 'medium',
                'message': '빈 except 절',
                'suggestion': '구체적인 예외 타입 지정'
            },
            {
                'pattern': r'print\s*\(',
                'severity': 'low',
                'message': 'print() 문 사용',
                'suggestion': 'logging 모듈 사용'
            },
            {
                'pattern': r'TODO|FIXME|HACK',
                'severity': 'low',
                'message': 'TODO/FIXME 주석',
                'suggestion': '해당 작업 완료'
            }
        ]
        
        for i, line in enumerate(lines, 1):
            for pattern_info in bug_patterns:
                if re.search(pattern_info['pattern'], line, re.IGNORECASE):
                    issues.append(QualityIssue(
                        file_path=str(file_path),
                        line_number=i,
                        issue_type='bug',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        suggestion=pattern_info['suggestion']
                    ))
        
        # 미사용 import 검사 (간단한 버전)
        try:
            tree = ast.parse(content)
            imports = []
            used_names = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append((alias.name, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imports.append((alias.name, node.lineno))
                elif isinstance(node, ast.Name):
                    used_names.add(node.id)
            
            for import_name, line_no in imports:
                base_name = import_name.split('.')[0]
                if base_name not in used_names and base_name not in ['os', 'sys', 'logging']:
                    issues.append(QualityIssue(
                        file_path=str(file_path),
                        line_number=line_no,
                        issue_type='bug',
                        severity='low',
                        message=f'미사용 import: {import_name}',
                        suggestion='불필요한 import 제거'
                    ))
        except SyntaxError:
            pass
        
        return issues
    
    def _calculate_scores(self, issues: List[QualityIssue], total_files: int, total_lines: int) -> Dict[str, float]:
        """점수 계산"""
        # 이슈 타입별 개수
        security_issues = [i for i in issues if i.issue_type == 'security']
        performance_issues = [i for i in issues if i.issue_type == 'performance']
        style_issues = [i for i in issues if i.issue_type == 'style']
        bug_issues = [i for i in issues if i.issue_type == 'bug']
        
        # 심각도별 가중치
        severity_weights = {'critical': 10, 'high': 5, 'medium': 2, 'low': 1}
        
        def calculate_category_score(category_issues):
            if not category_issues:
                return 100.0
            
            penalty = sum(severity_weights.get(issue.severity, 1) for issue in category_issues)
            # 파일당 페널티 정규화
            normalized_penalty = (penalty / total_files) * 10
            return max(0, 100 - normalized_penalty)
        
        scores = {
            'security': calculate_category_score(security_issues),
            'performance': calculate_category_score(performance_issues),
            'style': calculate_category_score(style_issues),
            'bugs': calculate_category_score(bug_issues),
            'overall': 0
        }
        
        # 전체 점수 (가중 평균)
        scores['overall'] = (
            scores['security'] * 0.4 +
            scores['performance'] * 0.3 +
            scores['bugs'] * 0.2 +
            scores['style'] * 0.1
        )
        
        return scores
    
    def _calculate_grade(self, scores: Dict[str, float]) -> str:
        """등급 계산"""
        overall_score = scores['overall']
        
        if overall_score >= 95:
            return 'A+'
        elif overall_score >= 90:
            return 'A'
        elif overall_score >= 85:
            return 'B+'
        elif overall_score >= 80:
            return 'B'
        elif overall_score >= 75:
            return 'C+'
        elif overall_score >= 70:
            return 'C'
        elif overall_score >= 65:
            return 'D+'
        elif overall_score >= 60:
            return 'D'
        else:
            return 'F'
    
    def _generate_recommendations(self, issues: List[QualityIssue]) -> List[str]:
        """권장사항 생성"""
        recommendations = []
        
        # 심각도별 이슈 분류
        critical_issues = [i for i in issues if i.severity == 'critical']
        high_issues = [i for i in issues if i.severity == 'high']
        
        if critical_issues:
            recommendations.append(f"🔴 긴급: {len(critical_issues)}개의 심각한 보안 이슈를 즉시 수정하세요")
        
        if high_issues:
            recommendations.append(f"🟡 중요: {len(high_issues)}개의 높은 우선순위 이슈를 수정하세요")
        
        # 타입별 권장사항
        security_issues = [i for i in issues if i.issue_type == 'security']
        if security_issues:
            recommendations.append("보안 강화: 하드코딩된 자격 증명을 환경변수로 분리하세요")
            recommendations.append("보안 검토: 정기적인 보안 감사를 실시하세요")
        
        performance_issues = [i for i in issues if i.issue_type == 'performance']
        if performance_issues:
            recommendations.append("성능 최적화: 비동기 처리 및 알고리즘 개선을 고려하세요")
        
        style_issues = [i for i in issues if i.issue_type == 'style']
        if len(style_issues) > 10:
            recommendations.append("코드 스타일: 자동 포매터(black, autopep8) 사용을 권장합니다")
        
        # 일반적인 권장사항
        recommendations.extend([
            "테스트 커버리지: 단위 테스트 작성으로 코드 품질을 향상시키세요",
            "코드 리뷰: 정기적인 코드 리뷰를 통해 품질을 관리하세요",
            "문서화: API 문서와 코드 주석을 보완하세요"
        ])
        
        return recommendations
    
    async def _save_report(self, report: QualityReport):
        """보고서 저장"""
        output_dir = self.project_root / "산출물/3.5_코드리뷰_AI자동화/품질관리"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON 보고서
        json_path = output_dir / "quality_report.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=str)
        
        # HTML 보고서
        html_content = self._generate_html_report(report)
        html_path = output_dir / "quality_report.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"품질 보고서 저장: {json_path}, {html_path}")
    
    def _generate_html_report(self, report: QualityReport) -> str:
        """HTML 보고서 생성"""
        # 이슈를 심각도별로 분류
        critical_issues = [i for i in report.issues if i.severity == 'critical']
        high_issues = [i for i in report.issues if i.severity == 'high']
        medium_issues = [i for i in report.issues if i.severity == 'medium']
        low_issues = [i for i in report.issues if i.severity == 'low']
        
        html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AICC 코드 품질 보고서</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f4f4f4; padding: 20px; border-radius: 5px; }}
        .grade {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .scores {{ display: flex; gap: 20px; margin: 20px 0; }}
        .score-card {{ background: #ecf0f1; padding: 15px; border-radius: 5px; flex: 1; }}
        .issue-section {{ margin: 20px 0; }}
        .issue {{ background: #fff; border-left: 4px solid #ccc; padding: 10px; margin: 5px 0; }}
        .critical {{ border-left-color: #e74c3c; }}
        .high {{ border-left-color: #f39c12; }}
        .medium {{ border-left-color: #f1c40f; }}
        .low {{ border-left-color: #95a5a6; }}
        .recommendations {{ background: #d5f4e6; padding: 15px; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AICC 코드 품질 보고서</h1>
        <p>생성일시: {report.timestamp}</p>
        <div class="grade">품질 등급: {report.grade}</div>
    </div>
    
    <div class="scores">
        <div class="score-card">
            <h3>보안</h3>
            <div>{report.scores['security']:.1f}/100</div>
        </div>
        <div class="score-card">
            <h3>성능</h3>
            <div>{report.scores['performance']:.1f}/100</div>
        </div>
        <div class="score-card">
            <h3>버그</h3>
            <div>{report.scores['bugs']:.1f}/100</div>
        </div>
        <div class="score-card">
            <h3>스타일</h3>
            <div>{report.scores['style']:.1f}/100</div>
        </div>
    </div>
    
    <h2>통계</h2>
    <table>
        <tr><th>항목</th><th>값</th></tr>
        <tr><td>총 파일 수</td><td>{report.total_files}</td></tr>
        <tr><td>총 라인 수</td><td>{report.total_lines:,}</td></tr>
        <tr><td>총 이슈 수</td><td>{len(report.issues)}</td></tr>
        <tr><td>심각한 이슈</td><td>{len(critical_issues)}</td></tr>
        <tr><td>높은 우선순위 이슈</td><td>{len(high_issues)}</td></tr>
    </table>
"""
        
        # 심각도별 이슈 표시
        if critical_issues:
            html += f"""
    <div class="issue-section">
        <h2>🔴 심각한 이슈 ({len(critical_issues)}개)</h2>
"""
            for issue in critical_issues[:10]:  # 상위 10개만
                html += f"""
        <div class="issue critical">
            <strong>{issue.message}</strong><br>
            파일: {issue.file_path}:{issue.line_number}<br>
            제안: {issue.suggestion}
        </div>
"""
            html += "</div>"
        
        if high_issues:
            html += f"""
    <div class="issue-section">
        <h2>🟡 높은 우선순위 이슈 ({len(high_issues)}개)</h2>
"""
            for issue in high_issues[:10]:  # 상위 10개만
                html += f"""
        <div class="issue high">
            <strong>{issue.message}</strong><br>
            파일: {issue.file_path}:{issue.line_number}<br>
            제안: {issue.suggestion}
        </div>
"""
            html += "</div>"
        
        # 권장사항
        html += f"""
    <div class="recommendations">
        <h2>권장사항</h2>
        <ul>
"""
        for rec in report.recommendations:
            html += f"<li>{rec}</li>"
        
        html += """
        </ul>
    </div>
</body>
</html>
"""
        
        return html

async def main():
    """메인 실행 함수"""
    project_root = os.getcwd()
    checker = CodeQualityChecker(project_root)
    
    try:
        report = await checker.run_quality_check()
        print(f"🎯 품질 검사 완료!")
        print(f"📊 등급: {report.grade}")
        print(f"📁 파일: {report.total_files}개")
        print(f"📝 라인: {report.total_lines:,}줄")
        print(f"⚠️  이슈: {len(report.issues)}개")
        print(f"🔴 심각: {len([i for i in report.issues if i.severity == 'critical'])}개")
        print(f"🟡 높음: {len([i for i in report.issues if i.severity == 'high'])}개")
        
    except Exception as e:
        print(f"❌ 품질 검사 실패: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    asyncio.run(main()) 