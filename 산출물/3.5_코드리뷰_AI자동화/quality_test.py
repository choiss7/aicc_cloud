#!/usr/bin/env python3
"""
코드 품질 검사 테스트 스크립트
"""

import os
import ast
import re
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

class CodeQualityChecker:
    def __init__(self):
        self.issues = defaultdict(list)
        self.scores = {}
    
    def check_security_issues(self, content, file_path):
        """보안 이슈 검사"""
        security_issues = []
        
        # 하드코딩된 비밀번호/키 검사
        patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                security_issues.append({
                    'type': 'hardcoded_secret',
                    'line': line_num,
                    'message': f'하드코딩된 비밀정보 발견: {match.group()[:20]}...',
                    'severity': 'high'
                })
        
        # eval/exec 사용 검사
        if 'eval(' in content or 'exec(' in content:
            security_issues.append({
                'type': 'dangerous_function',
                'message': 'eval() 또는 exec() 사용 발견',
                'severity': 'high'
            })
        
        return security_issues
    
    def check_performance_issues(self, content, file_path):
        """성능 이슈 검사"""
        performance_issues = []
        
        # time.sleep 사용 검사
        if 'time.sleep' in content:
            performance_issues.append({
                'type': 'blocking_sleep',
                'message': 'time.sleep() 사용으로 인한 블로킹 발견',
                'severity': 'medium'
            })
        
        # 중첩 반복문 검사 (간단한 패턴 매칭)
        nested_loops = re.findall(r'for.*:\s*\n.*for.*:', content, re.MULTILINE)
        if nested_loops:
            performance_issues.append({
                'type': 'nested_loops',
                'message': f'중첩 반복문 {len(nested_loops)}개 발견',
                'severity': 'medium'
            })
        
        return performance_issues
    
    def check_code_style(self, content, file_path):
        """코드 스타일 검사"""
        style_issues = []
        
        lines = content.split('\n')
        
        # 긴 라인 검사
        long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 120]
        if long_lines:
            style_issues.append({
                'type': 'long_lines',
                'lines': long_lines[:5],  # 처음 5개만
                'message': f'{len(long_lines)}개 라인이 120자를 초과',
                'severity': 'low'
            })
        
        # TODO/FIXME 주석 검사
        todo_count = content.count('TODO') + content.count('FIXME')
        if todo_count > 0:
            style_issues.append({
                'type': 'todo_comments',
                'count': todo_count,
                'message': f'{todo_count}개의 TODO/FIXME 주석 발견',
                'severity': 'low'
            })
        
        return style_issues
    
    def analyze_complexity(self, content):
        """코드 복잡도 분석"""
        try:
            tree = ast.parse(content)
            
            # 함수별 복잡도 계산 (간단한 버전)
            complexity_data = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 간단한 복잡도 계산 (if, for, while, try 문의 개수)
                    complexity = 1  # 기본 복잡도
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)):
                            complexity += 1
                    
                    complexity_data.append({
                        'function': node.name,
                        'complexity': complexity,
                        'line': node.lineno
                    })
            
            return complexity_data
        except:
            return []
    
    def analyze_file(self, file_path):
        """파일 분석"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            result = {
                'file_path': str(file_path),
                'security_issues': self.check_security_issues(content, file_path),
                'performance_issues': self.check_performance_issues(content, file_path),
                'style_issues': self.check_code_style(content, file_path),
                'complexity': self.analyze_complexity(content),
                'lines': len(content.split('\n')),
                'size_kb': len(content.encode('utf-8')) / 1024
            }
            
            # 점수 계산
            total_issues = (len(result['security_issues']) * 3 + 
                          len(result['performance_issues']) * 2 + 
                          len(result['style_issues']))
            
            # 복잡도 점수
            high_complexity = len([c for c in result['complexity'] if c['complexity'] > 10])
            complexity_penalty = high_complexity * 2
            
            # 기본 점수에서 이슈에 따라 차감
            base_score = 100
            final_score = max(0, base_score - total_issues - complexity_penalty)
            
            result['quality_score'] = final_score
            result['grade'] = self.get_grade(final_score)
            
            return result
            
        except Exception as e:
            return {
                'file_path': str(file_path),
                'error': str(e),
                'quality_score': 0,
                'grade': 'F'
            }
    
    def get_grade(self, score):
        """점수에 따른 등급 반환"""
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

def main():
    """메인 실행 함수"""
    print("🔍 AICC 코드 품질 검사 시작")
    print("=" * 60)
    
    # 분석 대상 디렉토리
    target_dir = Path("../3.4_공통_통합_기능_개발/소스코드")
    
    if not target_dir.exists():
        print(f"❌ 대상 디렉토리가 존재하지 않습니다: {target_dir}")
        return
    
    # Python 파일 찾기
    python_files = []
    for root, dirs, files in os.walk(target_dir):
        for file in files:
            if file.endswith('.py'):
                python_files.append(Path(root) / file)
    
    print(f"📁 분석 대상: {len(python_files)}개 파일")
    
    # 품질 검사 실행
    checker = CodeQualityChecker()
    results = []
    
    total_security_issues = 0
    total_performance_issues = 0
    total_style_issues = 0
    total_score = 0
    
    for file_path in python_files:
        print(f"🔍 검사 중: {file_path.name}")
        result = checker.analyze_file(file_path)
        results.append(result)
        
        if 'error' not in result:
            total_security_issues += len(result['security_issues'])
            total_performance_issues += len(result['performance_issues'])
            total_style_issues += len(result['style_issues'])
            total_score += result['quality_score']
    
    # 전체 결과 출력
    print("\n📊 품질 검사 결과")
    print("=" * 60)
    print(f"총 보안 이슈: {total_security_issues}개")
    print(f"총 성능 이슈: {total_performance_issues}개")
    print(f"총 스타일 이슈: {total_style_issues}개")
    print(f"평균 품질 점수: {total_score/len(python_files):.1f}/100")
    
    # 파일별 상세 결과
    print("\n📋 파일별 품질 점수")
    print("-" * 60)
    for result in results:
        if 'error' in result:
            print(f"❌ {Path(result['file_path']).name}: 분석 실패")
        else:
            print(f"{result['grade']} {Path(result['file_path']).name}: "
                  f"{result['quality_score']:.0f}점 "
                  f"(보안:{len(result['security_issues'])}, "
                  f"성능:{len(result['performance_issues'])}, "
                  f"스타일:{len(result['style_issues'])})")
    
    # 상위 이슈들 출력
    print("\n⚠️  주요 이슈")
    print("-" * 60)
    for result in results:
        if 'error' not in result:
            file_name = Path(result['file_path']).name
            
            # 보안 이슈
            for issue in result['security_issues']:
                print(f"🔴 {file_name}: {issue['message']}")
            
            # 성능 이슈
            for issue in result['performance_issues']:
                print(f"🟡 {file_name}: {issue['message']}")
            
            # 높은 복잡도 함수
            high_complexity = [c for c in result['complexity'] if c['complexity'] > 10]
            for func in high_complexity:
                print(f"🟠 {file_name}: 함수 '{func['function']}'의 복잡도가 높음 ({func['complexity']})")
    
    # 결과 저장
    output_file = "quality_report.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_files': len(python_files),
                'total_security_issues': total_security_issues,
                'total_performance_issues': total_performance_issues,
                'total_style_issues': total_style_issues,
                'average_score': total_score / len(python_files) if python_files else 0
            },
            'files': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 상세 결과가 {output_file}에 저장되었습니다.")
    print("✨ 품질 검사 완료!")

if __name__ == "__main__":
    main() 