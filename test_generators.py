"""
小说生成器测试脚本
测试所有15种小说类型生成器
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "backend" / "novel-service" / "app"))

from generators.novel_generator import (
    NovelType, NovelGeneratorFactory, 
    SciFiNovelGenerator, MysteryNovelGenerator, RomanceNovelGenerator,
    FantasyNovelGenerator, UrbanNovelGenerator, HistoryNovelGenerator,
    MartialArtsNovelGenerator, XianxiaNovelGenerator, HorrorNovelGenerator,
    MilitaryNovelGenerator, GameNovelGenerator, SportsNovelGenerator,
    TimeTravelNovelGenerator, SystemFlowNovelGenerator, ApocalypseNovelGenerator
)

async def test_generator(generator_class, type_name):
    """测试单个生成器"""
    print(f"\n{'='*60}")
    print(f"测试 {type_name} 生成器...")
    print('='*60)
    
    try:
        # 创建生成器实例
        generator = generator_class()
        
        # 测试1: 检查元数据
        print(f"[OK] 元数据: {generator.metadata}")
        
        # 测试2: 生成大纲（使用默认）
        outline = generator._create_default_outline("测试标题", "测试简介", 3)
        print(f"[OK] 大纲生成成功，章节数: {len(outline.get('chapters', []))}")
        
        # 测试3: 生成章节（使用默认）
        chapter = generator._create_default_chapter(0, "测试章节大纲")
        print(f"[OK] 章节生成成功，长度: {len(chapter)} 字")
        
        # 测试4: 生成人物（使用默认）
        character = generator._create_default_character("测试角色", "主角", ["勇敢", "聪明"])
        print(f"[OK] 人物生成成功: {character.get('basic_info', {}).get('occupation', '未知')}")
        
        # 测试5: 风格分析（使用默认）
        style = generator._create_default_style_analysis()
        print(f"[OK] 风格分析成功: {style.get('language_style', '未知')}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("="*60)
    print("AI小说生成器测试")
    print("="*60)
    
    # 定义所有生成器类型
    generators = [
        (SciFiNovelGenerator, "科幻"),
        (MysteryNovelGenerator, "悬疑推理"),
        (RomanceNovelGenerator, "言情"),
        (FantasyNovelGenerator, "奇幻"),
        (UrbanNovelGenerator, "都市"),
        (HistoryNovelGenerator, "历史"),
        (MartialArtsNovelGenerator, "武侠"),
        (XianxiaNovelGenerator, "仙侠"),
        (HorrorNovelGenerator, "恐怖"),
        (MilitaryNovelGenerator, "军事"),
        (GameNovelGenerator, "游戏"),
        (SportsNovelGenerator, "体育"),
        (TimeTravelNovelGenerator, "穿越"),
        (SystemFlowNovelGenerator, "系统流"),
        (ApocalypseNovelGenerator, "末日"),
    ]
    
    # 测试工厂
    print("\n测试工厂类...")
    supported_types = NovelGeneratorFactory.get_supported_types()
    print(f"[OK] 工厂支持 {len(supported_types)} 种类型")
    
    # 逐个测试生成器
    results = []
    for gen_class, name in generators:
        result = await test_generator(gen_class, name)
        results.append((name, result))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    
    for name, result in results:
        status = "[OK] 通过" if result else "[FAIL] 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\nPASS 所有测试通过！")
    else:
        print(f"\nWARNING 有 {failed} 个测试失败，请检查！")

if __name__ == "__main__":
    asyncio.run(main())
