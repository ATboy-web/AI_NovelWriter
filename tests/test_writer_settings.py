"""全屏写作器的设置读写（`writer_settings.json`）。

## 为什么单独测这个

原来读写都用**不带 encoding 的文本模式 `open()`** ⇒ Windows 上默认是 **GBK**：

- 读：文件里只要有非 ASCII 就抛 `UnicodeDecodeError`（实测在测试运行时
  以"后台线程未处理异常"的形式冒出来）；
- 写：会用 GBK 落盘，与读取方（以及任何外部编辑器）不一致。

这与本仓踩过两次的"非 UTF-8 控制台"是同一族问题，所以一并钉住：**读写都用 UTF-8**，
且设置读不出来时**不得**阻断全屏写作器打开（与 `AppConfig` 的"损坏不阻断"同一原则）。
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.fullscreen_writer import FullscreenWriter  # noqa: E402

DEFAULTS = {
    "font_size": 18,
    "paper_width": 700,
    "paper_position": "center",
    "bg_opacity": 0.85,
    "typewriter_mode": True,
    "ai_assist_enabled": True,
}


@pytest.fixture(scope="module")
def workdir():
    """一个**共用的**临时目录（每个用例一个 `tmp_path` 会带来两倍的目录创建/清理）。

    为什么不用 `tmp_path`：本沙箱的安全删除守卫按「本轮对话」累计路径数（阈值 50），
    长会话里跑到后半程时 `tmp_path` 的清理会触发 `SystemExit`，表现为成批
    `ERROR at setup` —— 那是环境伪报，但会把真实信号淹掉。
    """
    path = Path(tempfile.mkdtemp(prefix="anw-writer-settings-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _fresh(workdir: Path, name: str) -> Path:
    """在共用目录里开一个子目录（每个用例互不干扰）。"""
    target = workdir / name
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        item.unlink()
    return target


def _writer(config_dir: Path) -> SimpleNamespace:
    """一个足够让两个设置方法跑起来的替身（它们只碰 `self.config` 与这几个属性）。"""
    return SimpleNamespace(config=SimpleNamespace(config_dir=config_dir), **DEFAULTS)


def _settings_file(config_dir: Path) -> Path:
    return config_dir / "writer_settings.json"


def test_load_does_nothing_when_no_config():
    """没有 config（无 GUI/无配置环境）时不得抛异常。"""
    FullscreenWriter._load_writer_settings(SimpleNamespace(config=None))


def test_missing_file_keeps_defaults(workdir):
    writer = _writer(_fresh(workdir, "missing"))
    FullscreenWriter._load_writer_settings(writer)
    assert writer.font_size == DEFAULTS["font_size"]


def test_load_reads_utf8_file_with_non_ascii_content(workdir):
    """**回归**：设置文件里有非 ASCII 时也必须能读出来。

    不显式指定编码的话，Windows 上这里会抛 `UnicodeDecodeError('gbk')`。
    """
    config_dir = _fresh(workdir, "utf8")
    _settings_file(config_dir).write_text(
        json.dumps({"font_size": 22, "备注": "深色主题下的字号"}, ensure_ascii=False),
        encoding="utf-8",
    )
    writer = _writer(config_dir)
    FullscreenWriter._load_writer_settings(writer)
    assert writer.font_size == 22


def test_corrupt_file_does_not_block_the_writer(workdir):
    """损坏的设置文件不该让全屏写作器打不开 —— 用默认值继续。"""
    config_dir = _fresh(workdir, "corrupt")
    _settings_file(config_dir).write_text("{ 这不是 JSON", encoding="utf-8")
    writer = _writer(config_dir)
    FullscreenWriter._load_writer_settings(writer)
    assert writer.font_size == DEFAULTS["font_size"]


def test_save_writes_utf8_and_round_trips(workdir):
    config_dir = _fresh(workdir, "roundtrip")
    writer = _writer(config_dir)
    writer.font_size = 20
    writer.typewriter_mode = False
    FullscreenWriter._save_writer_settings(writer)

    raw = _settings_file(config_dir).read_bytes()
    assert b"\xef\xbb\xbf" not in raw, "不该写 BOM"
    data = json.loads(raw.decode("utf-8"))
    assert data["font_size"] == 20
    assert data["typewriter_mode"] is False

    reloaded = _writer(config_dir)
    FullscreenWriter._load_writer_settings(reloaded)
    assert reloaded.font_size == 20
    assert reloaded.typewriter_mode is False


def test_save_failure_is_not_fatal(workdir):
    """保存失败（目录不存在等）只记日志，不抛异常。"""
    missing_dir = workdir / "definitely-missing" / "nested"
    assert not missing_dir.exists()
    FullscreenWriter._save_writer_settings(_writer(missing_dir))  # 不应抛异常


@pytest.mark.parametrize("value", [12, 30])
def test_load_respects_stored_font_size(workdir, value):
    config_dir = _fresh(workdir, f"font-{value}")
    _settings_file(config_dir).write_text(json.dumps({"font_size": value}), encoding="utf-8")
    writer = _writer(config_dir)
    FullscreenWriter._load_writer_settings(writer)
    assert writer.font_size == value
