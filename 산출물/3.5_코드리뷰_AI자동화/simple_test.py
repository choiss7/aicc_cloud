#!/usr/bin/env python3
"""
간단한 자동화 도구 테스트 스크립트
기본 Python 라이브러리만 사용
"""

import os
import sys
import ast
import json
from pathlib import Path
from datetime import datetime

def analyze_python_file(file_path):
    """Python 파일을 분석하여 기본 정보를 추출합니다."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # AST 파싱
        tree = ast.parse(content)
        
        # 기본 통계
        stats = {
            'file_path': str(file_path),
            'lines': len(content.splitlines()),
            'functions': len([node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]),
            'classes': len([node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]),
            'imports': len([node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]),
        }
        
        return stats
    except Exception as e:
        return {'file_path': str(file_path), 'error': str(e)}

def find_python_files(directory):
    """디렉토리에서 Python 파일들을 찾습니다."""
    python_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                python_files.append(Path(root) / file)
    return python_files

def main():
    """메인 실행 함수"""
    print("🚀 AICC 자동화 도구 테스트 시작")
    print("=" * 50)
    
    # 분석 대상 디렉토리
    target_dir = Path("../3.4_공통_통합_기능_개발/소스코드")
    
    if not target_dir.exists():
        print(f"❌ 대상 디렉토리가 존재하지 않습니다: {target_dir}")
        return
    
    print(f"📁 분석 대상: {target_dir.absolute()}")
    
    # Python 파일 찾기
    python_files = find_python_files(target_dir)
    print(f"🔍 발견된 Python 파일: {len(python_files)}개")
    
    if not python_files:
        print("⚠️  Python 파일이 발견되지 않았습니다.")
        return
    
    # 파일별 분석
    results = []
    total_lines = 0
    total_functions = 0
    total_classes = 0
    
    for file_path in python_files:
        print(f"📄 분석 중: {file_path.name}")
        stats = analyze_python_file(file_path)
        results.append(stats)
        
        if 'error' not in stats:
            total_lines += stats['lines']
            total_functions += stats['functions']
            total_classes += stats['classes']
    
    # 결과 출력
    print("\n📊 분석 결과")
    print("=" * 50)
    print(f"총 파일 수: {len(python_files)}")
    print(f"총 라인 수: {total_lines}")
    print(f"총 함수 수: {total_functions}")
    print(f"총 클래스 수: {total_classes}")
    
    # 파일별 상세 결과
    print("\n📋 파일별 상세 정보")
    print("-" * 50)
    for result in results:
        if 'error' in result:
            print(f"❌ {Path(result['file_path']).name}: {result['error']}")
        else:
            print(f"✅ {Path(result['file_path']).name}: "
                  f"{result['lines']}줄, "
                  f"{result['functions']}함수, "
                  f"{result['classes']}클래스")
    
    # JSON 결과 저장
    output_file = "analysis_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_files': len(python_files),
                'total_lines': total_lines,
                'total_functions': total_functions,
                'total_classes': total_classes
            },
            'files': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 결과가 {output_file}에 저장되었습니다.")
    print("✨ 테스트 완료!")

if __name__ == "__main__":
    main() 