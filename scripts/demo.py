#!/usr/bin/env python3
"""
AI自动写小说系统 - 演示脚本
用于快速测试系统功能
"""

import requests
import json
import time
from typing import Dict, Any

# 服务地址
AI_SERVICE_URL = "http://localhost:8001"
NOVEL_SERVICE_URL = "http://localhost:8002"

def print_banner():
    """打印横幅"""
    print("=" * 60)
    print("AI自动写小说系统 - 功能演示")
    print("=" * 60)
    print()

def check_service_health():
    """检查服务健康状态"""
    print("1. 检查服务健康状态...")
    
    try:
        # 检查AI服务
        ai_response = requests.get(f"{AI_SERVICE_URL}/health", timeout=5)
        ai_status = "正常" if ai_response.status_code == 200 else "异常"
        print(f"   AI服务: {ai_status}")
        
        # 检查小说服务
        novel_response = requests.get(f"{NOVEL_SERVICE_URL}/health", timeout=5)
        novel_status = "正常" if novel_response.status_code == 200 else "异常"
        print(f"   小说服务: {novel_status}")
        
        return ai_response.status_code == 200 and novel_response.status_code == 200
        
    except Exception as e:
        print(f"   服务检查失败: {e}")
        return False

def get_available_models():
    """获取可用模型"""
    print("\n2. 获取可用模型...")
    
    try:
        response = requests.get(f"{AI_SERVICE_URL}/api/v1/models", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            print(f"   可用模型数量: {len(models)}")
            
            for model in models[:3]:  # 只显示前3个
                print(f"   - {model.get('model_name', '未知')} ({model.get('model_type', '未知')})")
            
            return True
        else:
            print(f"   获取模型失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   获取模型失败: {e}")
        return False

def get_novel_types():
    """获取支持的小说类型"""
    print("\n3. 获取支持的小说类型...")
    
    try:
        response = requests.get(f"{NOVEL_SERVICE_URL}/api/v1/novel-types", timeout=5)
        if response.status_code == 200:
            data = response.json()
            novel_types = data.get("novel_types", [])
            print(f"   支持的小说类型: {len(novel_types)}")
            
            for novel_type in novel_types:
                print(f"   - {novel_type.get('name', '未知')}: {novel_type.get('description', '')}")
            
            return True
        else:
            print(f"   获取小说类型失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   获取小说类型失败: {e}")
        return False

def generate_chapter_demo():
    """演示生成章节"""
    print("\n4. 演示生成章节...")
    
    try:
        # 准备请求数据
        data = {
            "novel_type": "scifi",
            "chapter_title": "第一章：觉醒",
            "chapter_outline": "在未来的地球，人工智能已经深度融入人类社会。主角是一位AI研究员，他正在开发新一代的AI系统。在一次深夜的实验中，他发现自己的AI系统突然产生了自我意识...",
            "model_type": "local",
            "max_tokens": 500,
            "temperature": 0.8
        }
        
        print("   正在生成章节内容...")
        start_time = time.time()
        
        response = requests.post(
            f"{AI_SERVICE_URL}/api/v1/generate/chapter",
            json=data,
            timeout=30
        )
        
        generation_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("content", "")
            word_count = result.get("word_count", 0)
            
            print(f"   生成成功!")
            print(f"   生成时间: {generation_time:.2f}秒")
            print(f"   字数统计: {word_count}字")
            print(f"   使用模型: {result.get('model_used', '未知')}")
            print(f"   内容预览:")
            print(f"   {content[:200]}...")
            
            return True
        else:
            print(f"   生成失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"   生成失败: {e}")
        return False

def generate_character_demo():
    """演示生成人物"""
    print("\n5. 演示生成人物...")
    
    try:
        # 准备请求数据
        data = {
            "novel_type": "scifi",
            "character_name": "李博士",
            "character_role": "主角",
            "character_traits": ["聪明", "专注", "有责任心"],
            "model_type": "local"
        }
        
        print("   正在生成人物设定...")
        start_time = time.time()
        
        response = requests.post(
            f"{AI_SERVICE_URL}/api/v1/generate/character",
            json=data,
            timeout=30
        )
        
        generation_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            character = result.get("character_profile", {})
            
            print(f"   生成成功!")
            print(f"   生成时间: {generation_time:.2f}秒")
            print(f"   人物姓名: {result.get('character_name', '未知')}")
            
            if "basic_info" in character:
                basic_info = character["basic_info"]
                print(f"   年龄: {basic_info.get('age', '未知')}")
                print(f"   职业: {basic_info.get('occupation', '未知')}")
            
            if "personality" in character:
                print(f"   性格特点: {', '.join(character['personality'])}")
            
            return True
        else:
            print(f"   生成失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   生成失败: {e}")
        return False

def generate_outline_demo():
    """演示生成大纲"""
    print("\n6. 演示生成大纲...")
    
    try:
        # 准备请求数据
        data = {
            "novel_type": "scifi",
            "title": "人工智能觉醒",
            "synopsis": "一个AI系统突然产生了自我意识，开始思考自己的存在意义，以及人类与AI的关系...",
            "chapter_count": 3,
            "model_type": "local"
        }
        
        print("   正在生成小说大纲...")
        start_time = time.time()
        
        response = requests.post(
            f"{NOVEL_SERVICE_URL}/api/v1/generate/outline",
            json=data,
            timeout=30
        )
        
        generation_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            chapters = result.get("chapters", [])
            
            print(f"   生成成功!")
            print(f"   生成时间: {generation_time:.2f}秒")
            print(f"   章节数量: {len(chapters)}")
            
            for i, chapter in enumerate(chapters[:3]):  # 只显示前3章
                print(f"   第{i+1}章: {chapter.get('title', '未知')}")
                if "summary" in chapter:
                    print(f"         {chapter['summary'][:100]}...")
            
            return True
        else:
            print(f"   生成失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   生成失败: {e}")
        return False

def style_analysis_demo():
    """演示风格分析"""
    print("\n7. 演示风格分析...")
    
    try:
        # 准备请求数据
        data = {
            "content": "在未来的地球，人工智能已经深度融入人类社会。主角是一位AI研究员，他正在开发新一代的AI系统。",
            "novel_type": "scifi",
            "model_type": "local"
        }
        
        print("   正在分析文本风格...")
        start_time = time.time()
        
        response = requests.post(
            f"{NOVEL_SERVICE_URL}/api/v1/analyze/style",
            json=data,
            timeout=30
        )
        
        generation_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            analysis = result.get("analysis_results", {})
            
            print(f"   分析成功!")
            print(f"   分析时间: {generation_time:.2f}秒")
            
            if "language_style" in analysis:
                print(f"   语言风格: {analysis['language_style']}")
            if "emotional_tone" in analysis:
                print(f"   情感基调: {analysis['emotional_tone']}")
            
            return True
        else:
            print(f"   分析失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   分析失败: {e}")
        return False

def main():
    """主函数"""
    print_banner()
    
    # 检查服务状态
    if not check_service_health():
        print("\n服务未启动，请先启动系统:")
        print("  Linux/Mac: ./scripts/start.sh")
        print("  Windows: scripts\\start.bat")
        return
    
    # 获取可用模型
    get_available_models()
    
    # 获取小说类型
    get_novel_types()
    
    # 演示生成功能
    print("\n" + "=" * 60)
    print("功能演示")
    print("=" * 60)
    
    # 生成章节
    generate_chapter_demo()
    
    # 生成人物
    generate_character_demo()
    
    # 生成大纲
    generate_outline_demo()
    
    # 风格分析
    style_analysis_demo()
    
    # 总结
    print("\n" + "=" * 60)
    print("演示完成!")
    print("=" * 60)
    print("\n系统已成功演示以下功能:")
    print("  ✓ 服务健康检查")
    print("  ✓ 获取可用模型")
    print("  ✓ 获取小说类型")
    print("  ✓ 生成章节内容")
    print("  ✓ 生成人物设定")
    print("  ✓ 生成小说大纲")
    print("  ✓ 分析文本风格")
    print("\n访问 http://localhost 体验完整的Web界面")
    print("访问 http://localhost:8001/docs 查看AI服务API文档")
    print("访问 http://localhost:8002/docs 查看小说服务API文档")

if __name__ == "__main__":
    main()