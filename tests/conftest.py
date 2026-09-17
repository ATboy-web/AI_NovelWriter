"""
Pytest配置文件 - 共享fixtures和测试工具
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))


# ── 诊断日志隔离 ──────────────────────────────────────
# 必须在**本文件被 import 时**立刻执行，不能放进 fixture 或 pytest_* 钩子：
# `app/ai_client.py:47`、`app/generation_ui.py:20`、`app/novel_agent.py:39` 都在
# **模块级**调用 `get_logger()` 建单例，而 `DiagnosticLogger` 的目录一旦确定就不再改变。
# 只要等收集阶段去 import 测试模块，`app.ai_client` 早已把单例钉在真实目录上了。
#
# 事故背景（2026-09-17 实测）：`~/.ai_novel_writer/diagnostic_logs/diagnostic-*.jsonl`
# 连续 3 天共 3126 条 `API_CALL` **全部是同一份测试指纹**（llama3:8b×14 / gpt-4o×10 /
# deepseek-v4-flash×8 …，44 行完全一致），而真实生成才产出的 `CHAPTER` 事件数为 **0**。
# 结论：真实使用数据被测试淹没且**不可还原** —— 想回答"单章生成到底慢在哪"
# 时，日志里找不到一份真实样本。
#
# 用环境变量而不是直接改单例，是因为 `app/` 下的生产代码本来就有 3 处各自硬编码
# 这个目录（`diagnostic_logger` / `shell_ui` / `toolkit_ui`）；环境变量是唯一
# 一处生效、三处同时被纠正的切点。
DIAGNOSTIC_LOG_DIR_ENV = "AI_NOVEL_DIAGNOSTIC_DIR"
_TEST_DIAGNOSTIC_DIR = Path(tempfile.mkdtemp(prefix="ai-novel-diag-test-"))
os.environ[DIAGNOSTIC_LOG_DIR_ENV] = str(_TEST_DIAGNOSTIC_DIR)


def pytest_collection_finish(session):
    """收集结束后、执行任何用例之前，恢复"仓库根 `app` 优先"的不变量。

    必须在**这里**而不是 fixture 里做：收集阶段会 import 各测试模块，
    而 `backend/tests/test_generators.py` 在模块级把 `backend/novel-service` 插到
    `sys.path[0]`（那里也有一个 `app` 包），于是 `import app` 会被它劫持。
    收集已完成、用例尚未执行，正是唯一能整体纠正的时刻。

    事故背景见 `tests/_app_authority.py` 的模块文档：本轮 v3.1.0 的 Release
    就是因为它被跳过而没能发布。
    """
    from _app_authority import describe_app_authority, restore_root_app_authority

    try:
        fixed = restore_root_app_authority()
    except RuntimeError as exc:  # pragma: no cover - 只会在真正无解时触发
        raise pytest.UsageError(f"测试进程的 `app` 解析异常：\n{exc}\n{describe_app_authority()}") from exc
    if fixed:
        # 大声说明修了什么：静默修正会让人以为环境本来就是干净的
        print(f"\n[tests/conftest] 已恢复 `app` 包归属（{('；'.join(fixed))}）")


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """创建临时目录，测试后自动清理"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_ai_client():
    """模拟AI客户端"""
    client = MagicMock()
    client.chat.return_value = "这是模拟的AI回复"
    client.is_configured.return_value = True
    return client


@pytest.fixture
def diagnostic_log_dir(tmp_path) -> Generator[Path, None, None]:
    """把诊断日志单例指向本用例的临时目录，并保证用例后还原。

    少数用例要看"日志文件里到底写了什么"（例如面板注册记录、性能报告落盘），
    它们需要逐用例的干净目录；默认的全局隔离目录是**整场会话共享**的，
    前一个用例写的行会串进后一个用例的断言。
    """
    from app import diagnostic_logger

    previous = os.environ.get(DIAGNOSTIC_LOG_DIR_ENV)
    target = tmp_path / "diagnostic_logs"
    os.environ[DIAGNOSTIC_LOG_DIR_ENV] = str(target)
    diagnostic_logger.reset_logger()
    try:
        yield target
    finally:
        if previous is None:
            os.environ.pop(DIAGNOSTIC_LOG_DIR_ENV, None)
        else:
            os.environ[DIAGNOSTIC_LOG_DIR_ENV] = previous
        diagnostic_logger.reset_logger()


@pytest.fixture
def sample_novel_data():
    """示例小说数据"""
    return {
        "title": "测试小说",
        "genre": "科幻",
        "concept": "一个关于AI的故事",
        "protagonist": "张三",
        "total_chapters": 10,
        "word_count_per_chapter": 3000,
    }


@pytest.fixture
def sample_chapter():
    """示例章节数据"""
    return {
        "chapter_num": 1,
        "title": "第一章：觉醒",
        "content": "张三睁开眼睛，发现自己躺在一个陌生的房间里。" * 10,
        "summary": "张三在一个陌生房间醒来",
    }


@pytest.fixture
def sample_characters():
    """示例角色数据"""
    return {
        "张三": {"name": "张三", "role": "主角", "age": 25, "personality": "勇敢、聪明", "background": "普通大学生"},
        "李四": {"name": "李四", "role": "配角", "age": 30, "personality": "稳重、可靠", "background": "资深研究员"},
    }


@pytest.fixture
def sample_world_settings():
    """示例世界观设定"""
    return """
    故事背景：2045年，人工智能已经深度融入人类社会。
    主要地点：新北京科技城
    技术水平：量子计算普及，AGI初步实现
    社会结构：人机共存社会
    """


# 测试标记
def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "slow: 标记为慢速测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "unit: 单元测试")


def pytest_sessionfinish(session, exitstatus):
    """会话结束前**验证隔离真的生效**，然后清掉临时目录。

    这一条不是仪式：隔离靠的是"环境变量在任何 `app.*` 被 import 之前就设好"，
    而这件事**没有任何类型系统能保证**。所以这里直接去问运行中的单例要答案 ——
    如果它落在真实目录，就大声报错，而不是安静地把污染当成正常。
    """
    from app import diagnostic_logger

    logger = diagnostic_logger.get_logger()
    actual = Path(logger.get_log_dir()).resolve()
    expected = _TEST_DIAGNOSTIC_DIR.resolve()
    if actual != expected:
        print(
            f"\n[tests/conftest] ⚠️ 诊断日志未隔离：单例目录为 {actual}，应为 {expected}。\n"
            "  真实使用数据可能已被本次测试污染，请检查 import 顺序是否早于本 conftest。"
        )

    shutil.rmtree(_TEST_DIAGNOSTIC_DIR, ignore_errors=True)


# 测试收集钩子
def pytest_collection_modifyitems(config, items):
    """根据标记自动跳过测试"""
    import platform

    # 在Windows上跳过某些Linux特定测试
    if platform.system() == "Windows":
        skip_windows = pytest.mark.skip(reason="Windows上不支持此测试")
        for item in items:
            if "linux_only" in item.keywords:
                item.add_marker(skip_windows)
