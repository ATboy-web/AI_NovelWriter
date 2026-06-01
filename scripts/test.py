#!/usr/bin/env python3
"""
AI自动写小说系统 - 测试脚本
用于验证系统功能
"""

import requests
import json
import sys
from typing import Dict, Any, List

# 服务地址
AI_SERVICE_URL = "http://localhost:8001"
NOVEL_SERVICE_URL = "http://localhost:8002"

class TestResult:
    """测试结果类"""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.name}" + (f" - {self.message}" if self.message else "")

def test_service_health() -> TestResult:
    """测试服务健康状态"""
    try:
        # 测试AI服务
        ai_response = requests.get(f"{AI_SERVICE_URL}/health", timeout=5)
        if ai_response.status_code != 200:
            return TestResult("服务健康检查", False, f"AI服务状态码: {ai_response.status_code}")
        
        # 测试小说服务
        novel_response = requests.get(f"{NOVEL_SERVICE_URL}/health", timeout=5)
        if novel_response.status_code != 200:
            return TestResult("服务健康检查", False, f"小说服务状态码: {novel_response.status_code}")
        
        return TestResult("服务健康检查", True)
        
    except Exception as e:
        return TestResult("服务健康检查", False, str(e))

def test_get_models() -> TestResult:
    """测试获取模型"""
    try:
        response = requests.get(f"{AI_SERVICE_URL}/api/v1/models", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return TestResult("获取模型", True, f"找到 {len(data.get('models', []))} 个模型")
            else:
                return TestResult("获取模型", False, "响应格式错误")
        else:
            return TestResult("获取模型", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("获取模型", False, str(e))

def test_get_novel_types() -> TestResult:
    """测试获取小说类型"""
    try:
        response = requests.get(f"{NOVEL_SERVICE_URL}/api/v1/novel-types", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                novel_types = data.get("novel_types", [])
                return TestResult("获取小说类型", True, f"找到 {len(novel_types)} 种类型")
            else:
                return TestResult("获取小说类型", False, "响应格式错误")
        else:
            return TestResult("获取小说类型", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("获取小说类型", False, str(e))

def test_generate_chapter() -> TestResult:
    """测试生成章节"""
    try:
        data = {
            "novel_type": "scifi",
            "chapter_title": "测试章节",
            "chapter_outline": "这是一个测试章节，用于验证生成功能是否正常工作。",
            "model_type": "local",
            "max_tokens": 100,
            "temperature": 0.7
        }
        
        response = requests.post(
            f"{AI_SERVICE_URL}/api/v1/generate/chapter",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                content = result.get("content", "")
                word_count = result.get("word_count", 0)
                return TestResult("生成章节", True, f"生成 {word_count} 字")
            else:
                return TestResult("生成章节", False, "生成失败")
        else:
            return TestResult("生成章节", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("生成章节", False, str(e))

def test_generate_character() -> TestResult:
    """测试生成人物"""
    try:
        data = {
            "novel_type": "scifi",
            "character_name": "测试角色",
            "character_role": "主角",
            "character_traits": ["聪明", "勇敢"],
            "model_type": "local"
        }
        
        response = requests.post(
            f"{AI_SERVICE_URL}/api/v1/generate/character",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                character = result.get("character_profile", {})
                return TestResult("生成人物", True, f"生成人物: {result.get('character_name', '未知')}")
            else:
                return TestResult("生成人物", False, "生成失败")
        else:
            return TestResult("生成人物", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("生成人物", False, str(e))

def test_generate_outline() -> TestResult:
    """测试生成大纲"""
    try:
        data = {
            "novel_type": "scifi",
            "title": "测试小说",
            "synopsis": "这是一个测试小说，用于验证大纲生成功能。",
            "chapter_count": 2,
            "model_type": "local"
        }
        
        response = requests.post(
            f"{NOVEL_SERVICE_URL}/api/v1/generate/outline",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                chapters = result.get("chapters", [])
                return TestResult("生成大纲", True, f"生成 {len(chapters)} 章大纲")
            else:
                return TestResult("生成大纲", False, "生成失败")
        else:
            return TestResult("生成大纲", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("生成大纲", False, str(e))

def test_analyze_style() -> TestResult:
    """测试风格分析"""
    try:
        data = {
            "content": "这是一个测试文本，用于验证风格分析功能。",
            "novel_type": "scifi",
            "model_type": "local"
        }
        
        response = requests.post(
            f"{NOVEL_SERVICE_URL}/api/v1/analyze/style",
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                analysis = result.get("analysis_results", {})
                return TestResult("风格分析", True, "分析完成")
            else:
                return TestResult("风格分析", False, "分析失败")
        else:
            return TestResult("风格分析", False, f"状态码: {response.status_code}")
            
    except Exception as e:
        return TestResult("风格分析", False, str(e))

def run_all_tests() -> List[TestResult]:
    """运行所有测试"""
    tests = [
        test_service_health,
        test_get_models,
        test_get_novel_types,
        test_generate_chapter,
        test_generate_character,
        test_generate_outline,
        test_analyze_style
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            results.append(TestResult(test_func.__name__, False, str(e)))
    
    return results

def print_test_results(results: List[TestResult]):
    """打印测试结果"""
    print("=" * 60)
    print("AI自动写小说系统 - 测试报告")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    
    for result in results:
        print(result)
        if result.passed:
            passed += 1
        else:
            failed += 1
    
    print()
    print("-" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {len(results)} 项")
    print("-" * 60)
    
    if failed == 0:
        print("\n✓ 所有测试通过！系统运行正常。")
    else:
        print(f"\n✗ 有 {failed} 项测试失败，请检查系统状态。")
    
    return failed == 0

def main():
    """主函数"""
    print("开始运行系统测试...")
    print()
    
    # 运行所有测试
    results = run_all_tests()
    
    # 打印测试结果
    success = print_test_results(results)
    
    # 返回退出码
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()