"""第三轮代码复查修复的回归测试。

对应 `docs/CODE_REVIEW_ROUND3.md` 中逐条列出的缺陷。每条测试的 docstring 都写明了
它锁定的缺陷编号，便于后续回溯。

覆盖范围：
- V1/V4 降级读之后的「底座空、增量非空」盲写
- V3 章节生成自动建角色必须走锁内读-改-写
- L6 旧版角色单文件不得被删除
- L7 凭据配置损坏/无法解密时不得被空值覆盖
- L8 启动器不得留下永不排空的子进程管道
- L9 传记生成的字数输入与 AI 返回校验
- M6 关键词缓存的跨线程安全
- M8/M9/S7 AI 客户端的配置热更新与端点校验
- S3/M11 docker-compose 的端口与口令强化
- S4 生产环境配置校验必须真正阻止启动
"""

import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.memory_manager import (
    CharacterDataGuardError,
    MemoryManager,
)


def make_chars(n: int, prefix: str = "角色") -> dict:
    return {f"{prefix}{i:03d}": {"personality": f"性格{i}"} for i in range(n)}


@pytest.fixture
def mm(tmp_path):
    return MemoryManager(tmp_path)


# 源码扫描工具已收敛到 tests/_source_scan.py（此前在本文件与其它测试里各有一份）。
# 显式把 tests/ 目录放进 sys.path 再按顶层模块名导入：`pytest -q`（走 testpaths）
# 与 `pytest tests/xxx.py` 两种调用方式下，包限定名 `tests.x` 的可见性并不一致。
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import _source_scan as _scan  # noqa: E402

REPO_ROOT = _scan.REPO_ROOT
_read = _scan.read
_code_only = _scan.code_only
_strip_noise = _scan.strip_noise
_method_body = _scan.method_body

# ===================================================================== V1 / V4


class TestDegradedReadBlocksBlindWrite:
    """V1/V4：真正的危险方向是「入参非空、底座为空」。"""

    def test_degraded_read_then_nonempty_save_is_refused(self, mm):
        """读到空底座后写非空集合必须被拒绝，且磁盘内容原样保留。"""
        mm.characters_file.write_text("彻底不是 JSON", encoding="utf-8")
        before = mm.characters_file.read_bytes()

        assert mm.get_characters() == {}
        assert mm._characters_corrupt is True

        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({"新角色": {"personality": "x"}})

        assert mm.characters_file.read_bytes() == before, "被拒绝的写入不得触碰磁盘"

    def test_refusal_archives_the_corrupt_file(self, mm):
        """拒绝写入时必须先把损坏文件留档，避免灭失。"""
        mm.characters_file.write_text("彻底不是 JSON", encoding="utf-8")
        assert mm.get_characters() == {}

        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({"新角色": {}})

        archives = list(mm.characters_file.parent.glob("characters.corrupt-*.json"))
        assert len(archives) == 1
        assert "彻底不是 JSON" in archives[0].read_text(encoding="utf-8")

    def test_preserves_286_scale_library_under_corruption(self, mm):
        """线上规模：底座读取失败时，286 个角色一个都不能少/被清。"""
        mm.save_characters(make_chars(286))
        # 破坏主文件，同时破坏备份（模拟"无可用备份"）
        mm.characters_file.write_text("{截断", encoding="utf-8")
        (mm.characters_file.parent / (mm.characters_file.name + ".bak")).write_text("{也坏了", encoding="utf-8")

        assert mm.get_characters() == {}
        with pytest.raises(CharacterDataGuardError):
            mm.save_characters({"新增角色A": {}})

        # 损坏内容仍可人工恢复：主文件与留档都还在
        assert mm.characters_file.exists()
        archived = list(mm.characters_file.parent.glob("characters.corrupt-*.json"))
        assert archived and "{截断" in archived[0].read_text(encoding="utf-8")

    def test_guard_can_be_forced_explicitly(self, mm):
        """显式 force=True 时允许继续（仍先留档）。"""
        mm.characters_file.write_text("坏数据", encoding="utf-8")
        assert mm.get_characters() == {}

        mm.save_characters({"甲": {}}, force=True)

        assert set(mm.get_characters()) == {"甲"}
        assert list(mm.characters_file.parent.glob("characters.corrupt-*.json"))

    def test_mutate_characters_is_blocked_after_degraded_read(self, mm):
        """mutate 走的也是 save_characters，因此同样被闸门拦住。"""
        mm.characters_file.write_text("坏数据", encoding="utf-8")
        assert mm.get_characters() == {}

        with pytest.raises(CharacterDataGuardError):
            mm.mutate_characters(lambda chars: chars.__setitem__("新", {}))

    def test_healthy_read_allows_normal_save(self, mm):
        """正常读不置损坏标记，后续写入不受影响（不能误伤正常路径）。"""
        mm.save_characters(make_chars(3))
        assert len(mm.get_characters()) == 3
        assert mm._characters_corrupt is False

        mm.save_characters(make_chars(5))
        assert len(mm.get_characters()) == 5

    def test_backup_recovery_does_not_block_writes(self, mm):
        """主文件坏了但 `.bak` 可解析 → 属正常降级，不得阻断写入。"""
        mm.save_characters(make_chars(4, "旧"))
        mm.save_characters(make_chars(6, "新"))  # .bak = 4 个"旧"
        mm.characters_file.write_text("{截断", encoding="utf-8")

        assert len(mm.get_characters()) == 4
        assert mm._characters_corrupt is False

        mm.mutate_characters(lambda chars: chars.__setitem__("新增", {}))
        assert "新增" in mm.get_characters()

    def test_archive_names_do_not_collide_within_one_second(self, mm):
        """同一秒内多次留档必须各自独立成文件，不能互相覆盖。"""
        mm.characters_file.write_text("坏数据", encoding="utf-8")
        assert mm.get_characters() == {}

        for _ in range(3):
            with pytest.raises(CharacterDataGuardError):
                mm.save_characters({"甲": {}})

        archives = list(mm.characters_file.parent.glob("characters.corrupt-*.json"))
        assert len(archives) == 3

    def test_first_write_of_empty_set_still_allowed(self, mm):
        """不存在损坏标记时，空库写空集是合法的（不误伤）。"""
        mm.save_characters({})
        assert mm.get_characters() == {}


class TestAutoDetectUsesLockedMutation:
    """V3：章节生成自动建角色必须走锁内读-改-写。"""

    def test_auto_detect_uses_mutate_characters(self):
        body = _method_body("app/character_ui.py", "def _auto_detect_characters", "def _sync_characters_to_system")
        assert "mutate_characters" in body
        assert "self.memory.save_characters(" not in body, "自动建角色不得直接整体覆盖角色库（底座为空时会清库）"

    def test_auto_detect_surfaces_guard_trip_to_the_user(self):
        body = _method_body("app/character_ui.py", "def _auto_detect_characters", "def _sync_characters_to_system")
        assert "CharacterDataGuardError" in body
        assert "已阻止一次可能清空角色库的写入" in body


class TestNovelAgentRefusesOnCorruptBase:
    """V4：并集合并不得在损坏场景下退化为整体覆盖。"""

    @staticmethod
    def _agent(memory, payload: dict):
        from app.novel_agent import NovelAgent

        ai = MagicMock()
        ai.chat.return_value = json.dumps(payload, ensure_ascii=False)
        ai.is_configured.return_value = True
        return NovelAgent(ai, memory)

    def test_refuses_when_base_is_corrupt(self, mm):
        mm.characters_file.write_text("坏数据", encoding="utf-8")

        agent = self._agent(mm, {"新角色A": {"personality": "x"}})
        with pytest.raises(CharacterDataGuardError):
            agent.generate_characters("科幻", "测试书名", count=1)

    def test_normal_path_still_merges(self, mm):
        """反向断言：底座正常时并集合并照常工作。"""
        mm.save_characters(make_chars(5))
        agent = self._agent(mm, {"新角色A": {"personality": "x"}})
        agent.generate_characters("科幻", "测试书名", count=1)

        chars = mm.get_characters()
        assert len(chars) == 6
        assert "新角色A" in chars


# ======================================================================== L6


class TestLegacyCharacterFileIsArchivedNotDeleted:
    """L6：旧版单文件一律不删除，改为改名归档。"""

    def test_legacy_file_is_imported_then_archived(self, tmp_path):
        from app.character_system import CharacterSystem

        legacy = tmp_path / "character_profile.json"
        legacy.write_text(
            json.dumps({"name": "旧主角", "personality": "沉稳"}, ensure_ascii=False),
            encoding="utf-8",
        )

        cs = CharacterSystem(tmp_path)

        assert "旧主角" in cs.get_character_names()
        assert not legacy.exists(), "旧文件应已改名归档"
        archived = tmp_path / "character_profile.json.migrated"
        assert archived.exists()
        assert json.loads(archived.read_text(encoding="utf-8"))["personality"] == "沉稳"

    def test_name_already_present_is_not_silently_dropped(self, tmp_path):
        """同名已存在时，旧文件内容必须留在归档里而不是被删掉。"""
        from app.character_system import CharacterSystem

        cs = CharacterSystem(tmp_path)
        cs.create_character("甲")

        legacy = tmp_path / "character_profile.json"
        legacy.write_text(
            json.dumps({"name": "甲", "personality": "旧版更丰富的设定"}, ensure_ascii=False),
            encoding="utf-8",
        )

        reloaded = CharacterSystem(tmp_path)

        assert "甲" in reloaded.get_character_names()
        archived = tmp_path / "character_profile.json.migrated"
        assert archived.exists()
        assert "旧版更丰富的设定" in archived.read_text(encoding="utf-8")

    def test_source_has_no_unconditional_unlink_of_legacy_file(self):
        """只锁定旧文件迁移块：该块内不得出现 unlink，只能 rename 归档。

        不能对全文件断言 `old_file.unlink()` 不存在 —— `rename_character` 里
        改名后清理旧文件是**合法**的 unlink，两者不可混为一谈。
        """
        src = _read("app/character_system.py")
        start = src.index("if old_file and old_file.exists():")
        end = min(
            src.index("\n    @property", start),
            src.index("\n    def ", start),
        )
        block = _strip_noise(src[start:end])

        assert "unlink" not in block, "旧文件迁移块不得删除文件，只能改名归档"
        assert "old_file.rename(" in block


# ======================================================================== L7


class TestSecureConfigNoSilentOverwrite:
    """L7：配置损坏 / 密钥解密失败都不得被空值静默覆盖。"""

    def test_corrupt_config_is_archived_and_flagged(self, tmp_path):
        from app.secure_config import SecureConfig

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "config.json").write_text("{不是 JSON", encoding="utf-8")

        sc = SecureConfig(cfg_dir)

        assert sc._load_failed is True
        assert sc.get("api_provider") == "ollama"  # 默认值仍可读，界面不至于崩
        archives = list(cfg_dir.glob("config.corrupt-*.json"))
        assert len(archives) == 1
        assert "不是 JSON" in archives[0].read_text(encoding="utf-8")

    def test_undecryptable_key_is_preserved_on_save(self, tmp_path):
        """解不开的密钥必须原样保留密文，不能被一次无关的 set() 抹掉。"""
        from app.secure_config import SecureConfig

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        foreign = SecureConfig(tmp_path / "foreign")  # 另一把 Fernet key
        cipher = foreign._encrypt("sk-real-key")

        (cfg_dir / "config.json").write_text(
            json.dumps({"api_key": cipher, "api_provider": "deepseek"}, ensure_ascii=False),
            encoding="utf-8",
        )

        sc = SecureConfig(cfg_dir)
        assert sc.get("api_key") == ""  # 解不开 → 界面显示空

        sc.set("theme", "dark")  # 触发一次全量保存

        saved = json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))
        assert saved["api_key"] == cipher, "无法解密的密钥必须原样写回，不得被空值覆盖"
        assert saved["theme"] == "dark"

    def test_save_is_atomic_and_keeps_mode(self, tmp_path):
        from app.secure_config import SecureConfig

        cfg_dir = tmp_path / "cfg"
        sc = SecureConfig(cfg_dir)
        sc.set("theme", "dark")

        assert list(cfg_dir.glob("*.tmp")) == [], "原子写不得留下临时文件"
        assert json.loads((cfg_dir / "config.json").read_text(encoding="utf-8"))["theme"] == "dark"

    def test_singleton_is_thread_safe(self, monkeypatch):
        """M7：并发首次获取单例只能构造一个实例（否则可能出现两把 key）。

        必须把构造过程与真实 DPAPI/密钥文件解耦：测试机上若存在一份由**其他
        账户**创建的 `.config_key`，`_init_encryption` 会抛 OSError，构造失败
        使 `_secure_config` 一直为 None，后续线程就会不断重试构造 —— 这会
        掩盖真正的被测行为（锁是否生效），并让断言随环境漂移。
        """
        from cryptography.fernet import Fernet

        import app.secure_config as sc_mod

        fixed_key = Fernet.generate_key()
        monkeypatch.setattr(sc_mod.SecureConfig, "_init_encryption", lambda self: Fernet(fixed_key))
        monkeypatch.setattr(sc_mod.SecureConfig, "_load", lambda self: {})

        created = []
        original = sc_mod.SecureConfig

        class _Counting(original):  # type: ignore[misc,valid-type]
            def __init__(self, *a, **kw):
                created.append(1)
                super().__init__(*a, **kw)

        sc_mod._secure_config = None
        sc_mod.SecureConfig = _Counting
        results = []
        try:
            barrier = threading.Barrier(8)

            def worker():
                barrier.wait(timeout=10)
                results.append(sc_mod.get_secure_config())

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            assert len(results) == 8, "所有线程都必须拿到单例（不得因构造异常而落空）"
            assert all(r is results[0] for r in results)
            assert len(created) == 1, f"并发首次获取只应构造一次，实际 {len(created)} 次"
        finally:
            sc_mod.SecureConfig = original
            sc_mod._secure_config = None


# ======================================================================== L8


class TestLauncherDoesNotBlockOnPipes:
    """L8：子进程输出必须被排空或重定向，不能留下永不读取的管道。"""

    def test_no_unread_pipes_are_created(self):
        # 只看真实代码：docstring 里会引用"旧实现用了 PIPE"，属说明文字。
        src = _code_only("installer/launcher.py")
        assert "stdout=subprocess.PIPE" not in src
        assert "stderr=subprocess.PIPE" not in src

    def test_output_is_redirected_to_log_files(self):
        src = _code_only("installer/launcher.py")
        assert "_open_service_log" in src
        assert "subprocess.DEVNULL" in src, "日志文件创建失败时必须退回 DEVNULL"

    def test_handles_are_closed_on_stop(self):
        src = _code_only("installer/launcher.py")
        assert "_close_service_logs" in src
        assert "stop_all_services" in src


# ======================================================================== L9


class TestBiographyInputValidation:
    """L9：传记字数输入与 AI 返回都必须校验。"""

    def test_word_count_parse_is_guarded(self):
        body = _method_body("app/character_ui.py", "def start_generate", "def run(")
        assert "except (TypeError, ValueError):" in body
        assert "messagebox.showwarning(" in body

    def test_word_dialog_is_destroyed_after_validation_only(self):
        """只有校验通过才关闭对话框：两个失败分支都必须 return，绝不走到 destroy()。

        必须先 ``_strip_noise``：函数上方的修复注释里本身就写了一句
        `word_dialog.destroy()`，不过滤会命中的是注释而非真实调用点。
        """
        body = _strip_noise(_method_body("app/character_ui.py", "def start_generate", "def run("))
        guard = body.index("except (TypeError, ValueError):")
        destroy = body.index("word_dialog.destroy()")
        assert guard < destroy, "校验失败分支必须早于 destroy"

        # 解析失败分支与越界分支都要先 return，否则对话框会被关掉
        error_path = body[guard:destroy]
        assert error_path.count("return") >= 2, "解析失败与越界两条分支都必须 return，不能继续执行 destroy()"

    def test_max_tokens_is_clamped(self):
        src = _read("app/character_ui.py")
        assert "MAX_BIO_TOKENS" in src
        assert "max_tokens=word_count * 2" not in src

    def test_empty_ai_result_is_rejected(self):
        body = _method_body("app/character_ui.py", "def run(", "self.root.after(0")
        assert "空传记" in body

    def test_missing_character_is_reported(self):
        body = _method_body("app/character_ui.py", "def run(", "self.root.after(0")
        assert "attached" in body and "未能挂到角色面板" in body


# ======================================================================== M6


class TestKeywordCacheThreadSafety:
    """M6：类级关键词缓存必须加锁。"""

    def test_cache_lock_exists(self):
        assert hasattr(MemoryManager, "_KW_CACHE_LOCK")

    def test_concurrent_extraction_is_safe_and_bounded(self):
        texts = [f"第{i}段测试文本，包含若干中文词组用于分词处理" for i in range(60)]
        errors = []

        def worker():
            try:
                for text in texts:
                    MemoryManager._extract_keywords(text)
            except Exception as e:  # pragma: no cover - 失败时提供诊断
                errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        assert len(MemoryManager._KW_CACHE) <= MemoryManager._KW_CACHE_MAX


# ================================================================= M8/M9/S7


class TestAIClientEndpointValidation:
    """S7：不得向非本机地址用明文 HTTP 发送 API Key。"""

    @staticmethod
    def _client(**overrides):
        from app.ai_client import AIClient

        config = {
            "api_provider": "deepseek",
            "api_key": "sk-test-key-1234567890",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-chat",
        }
        config.update(overrides)
        return AIClient(config)

    def test_remote_plaintext_http_is_rejected(self):
        with pytest.raises(ValueError, match="明文 HTTP"):
            self._client(api_base="http://api.deepseek.com")

    def test_non_http_scheme_is_rejected(self):
        with pytest.raises(ValueError, match="协议非法"):
            self._client(api_base="file:///etc/passwd")

    def test_localhost_http_is_allowed(self):
        client = self._client(api_provider="ollama", api_key="", api_base="http://localhost:11434")
        assert client.is_configured() is True

    def test_loopback_ip_http_is_allowed(self):
        client = self._client(api_provider="ollama", api_key="", api_base="http://127.0.0.1:11434")
        assert client.is_configured() is True

    def test_https_is_allowed(self):
        assert self._client().is_configured() is True


class TestAIClientConfigRefresh:
    """M9：运行中修改 API Key 应立即生效，无需重启。"""

    @staticmethod
    def _config():
        return {
            "api_provider": "deepseek",
            "api_key": "sk-old-key-123456",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-chat",
        }

    def test_changing_api_key_rebuilds_the_client(self):
        from app.ai_client import AIClient

        config = self._config()
        client = AIClient(config)
        old_auth = client.client.headers.get("authorization")

        config["api_key"] = "sk-new-key-987654"
        client.refresh_if_needed()

        new_auth = client.client.headers.get("authorization")
        assert new_auth != old_auth
        assert "sk-new-key-987654" in new_auth

    def test_unchanged_config_keeps_the_client(self):
        from app.ai_client import AIClient

        client = AIClient(self._config())
        same = client.client
        client.refresh_if_needed()
        assert client.client is same

    def test_chat_refreshes_before_use(self):
        src = _read("app/ai_client.py")
        assert "self.refresh_if_needed()" in src


class TestDiagnosticsDoNotLeakContent:
    """M8：诊断日志不得记录创作正文。"""

    def test_content_preview_is_gone(self):
        # 只看真实代码：修复说明会以注释形式提到 `content_preview`。
        src = _code_only("app/ai_client.py")
        assert "content_preview" not in src


class TestRetryPolicyIsTransientOnly:
    """M1：只有瞬时故障才重试（原 decorator 已删除，语义保留在辅助函数里）。"""

    def test_decorator_removed(self):
        src = _read("app/ai_client.py")
        assert "def retry_with_backoff" not in src

    def test_transient_helper_exists(self):
        import httpx

        from app.ai_client import _is_transient_error

        assert _is_transient_error(httpx.TimeoutException("t")) is True
        assert _is_transient_error(ValueError("x")) is False


# ============================================================== S3 / M11 / S4


@pytest.fixture(scope="module")
def compose():
    """解析 docker-compose.yml（模块级：避免 class-scoped 实例方法写法被 pytest 10 移除）。"""
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


class TestDockerComposeHardening:
    """S3/M11：只有边缘服务对外，口令必填，且不出现在进程 argv 里。"""

    def test_only_edge_services_bind_all_interfaces(self, compose):
        public = {
            name
            for name, svc in compose["services"].items()
            if any(str(p).split(":")[0] not in ("127.0.0.1", "localhost") for p in svc.get("ports", []))
        }
        assert public == {"frontend", "nginx"}

    def test_internal_services_bind_loopback(self, compose):
        for name in ("postgres", "redis", "ai-service", "novel-service"):
            ports = compose["services"][name]["ports"]
            assert all(str(p).startswith("127.0.0.1:") for p in ports), name

    def test_redis_password_is_required(self, compose):
        cmd = compose["services"]["redis"]["command"]
        assert "${REDIS_PASSWORD:?" in cmd
        assert "${REDIS_PASSWORD:-" not in cmd, "不得保留'没配就空口令'的降级默认值"

    def test_redis_healthcheck_does_not_put_password_in_argv(self, compose):
        test = compose["services"]["redis"]["healthcheck"]["test"]
        assert "REDISCLI_AUTH" in " ".join(test)
        assert "-a" not in test

    def test_auth_enabled_by_default(self, compose):
        env = compose["services"]["novel-service"]["environment"]
        assert "ENABLE_AUTH=${ENABLE_AUTH:-true}" in env


class TestProductionConfigValidationBlocksStartup:
    """S4：生产环境的配置校验必须阻止启动，而不是只打日志。"""

    def test_validate_settings_raises_in_production(self):
        src = _read("backend/ai-service/app/core/config.py")
        body = src[src.index("def validate_settings") :]
        assert "raise ValueError" in body
        assert "is_production" in body
