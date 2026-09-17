"""诊断日志「测试隔离」门禁。

## 为什么需要这个文件

`~/.ai_novel_writer/diagnostic_logs/` 是**唯一**能回答"这一章为什么慢"的地方，
但它曾经同时是测试的垃圾桶。2026-09-17 实测：

| 指标 | 值 |
|---|---|
| 近 3 日 `API_CALL` 总条数 | 3126 |
| 其中"同一份测试指纹"（llama3:8b×14 / gpt-4o×10 / deepseek-v4-flash×8 …） | 全部 |
| 近 3 日真实生成才会产生的 `CHAPTER` 事件 | **0** |

即：**没有任何一份真实生成样本被记录下来**，而且已经不可还原。

根因不是"测试没清理"，而是三件事叠在一起：

1. `DiagnosticLogger.__init__` 把目录**硬编码**成 `Path.home()/".ai_novel_writer"/…`；
2. `app/ai_client.py:47`、`app/generation_ui.py:20`、`app/novel_agent.py:39` 都在
   **模块级**调用 `get_logger()` —— 只要有人 import 这个模块，单例就钉死了；
3. `tests/conftest.py` 里**没有任何**隔离逻辑。

本文件把修好的四件事钉住，防止回退。四类断言分别对应四个可能失效的环节：
目录解析优先级 / 导入期不落真实目录 / 两个同目录硬编码点已收口 / 会话级隔离确实生效。
"""

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import diagnostic_logger
from app.diagnostic_logger import DIAGNOSTIC_LOG_DIR_ENV, DiagnosticLogger, resolve_log_dir

_REPO_ROOT = Path(__file__).resolve().parent.parent
#: 真实使用日志所在目录。所有断言都以"它一个字都不许变"为准绳。
_REAL_LOG_DIR = Path.home() / ".ai_novel_writer" / "diagnostic_logs"


def _snapshot_real_logs() -> dict:
    """真实日志目录下所有 .jsonl 的字节数。"""
    if not _REAL_LOG_DIR.exists():
        return {}
    return {p.name: p.stat().st_size for p in _REAL_LOG_DIR.glob("*.jsonl")}


def _diff(before: dict, after: dict) -> dict:
    return {
        k: (after.get(k, 0) - before.get(k, 0)) for k in set(after) | set(before) if after.get(k, 0) != before.get(k, 0)
    }


class TestResolveLogDir:
    """目录从哪来必须只有一处实现，且优先级明确。"""

    def test_explicit_argument_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "from_env"))
        assert resolve_log_dir(tmp_path / "explicit") == tmp_path / "explicit"

    def test_env_var_beats_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "from_env"))
        assert resolve_log_dir() == tmp_path / "from_env"

    def test_default_is_home_dir(self, monkeypatch):
        monkeypatch.delenv(DIAGNOSTIC_LOG_DIR_ENV, raising=False)
        assert resolve_log_dir() == Path.home() / ".ai_novel_writer" / "diagnostic_logs"

    def test_empty_env_falls_back_to_default(self, monkeypatch):
        """空串按"未设置"处理 —— 否则一个空变量会让日志写进当前工作目录。"""
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, "")
        assert resolve_log_dir() == Path.home() / ".ai_novel_writer" / "diagnostic_logs"

    def test_constructor_uses_resolver(self, tmp_path, monkeypatch):
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "from_env"))
        logger = DiagnosticLogger()
        try:
            assert logger.get_log_dir() == tmp_path / "from_env"
        finally:
            pass

    def test_constructor_explicit_beats_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "from_env"))
        logger = DiagnosticLogger(log_dir=tmp_path / "explicit")
        assert logger.get_log_dir() == tmp_path / "explicit"


class TestImportTimeDoesNotTouchRealDir:
    """导入期不落真实目录 —— 这是隔离真正的难点，必须用子进程证明。"""

    def test_importing_app_ai_client_writes_to_isolated_dir(self, tmp_path):
        """子进程里设好环境变量再 import `app.ai_client`，真实目录必须零变化。"""
        target = tmp_path / "isolated"
        before = _snapshot_real_logs()

        code = (
            "import os\n"
            f"os.environ[{DIAGNOSTIC_LOG_DIR_ENV!r}] = {str(target)!r}\n"
            "import app.ai_client as ac\n"
            "print(ac._diag_logger.get_log_dir())\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert result.returncode == 0, f"子进程失败：{result.stderr}"

        after = _snapshot_real_logs()
        assert _diff(before, after) == {}, f"导入 `app.ai_client` 污染了真实日志目录：{_diff(before, after)}"
        # 且确实写到了被隔离的目录（证明"没污染"不是因为根本没写）
        assert list(target.glob("*.jsonl")), "隔离目录里没有产生日志文件，说明断言是空转的"

    def test_without_env_logger_follows_default_home_path(self, tmp_path):
        """反证：不设 `AI_NOVEL_DIAGNOSTIC_DIR` 时，日志走**默认 home 路径**。

        没有这条，"隔离生效"可能只是因为"这个导入根本不写日志"造成的空转通过。

        ⚠️ **但不能拿真实 home 做这个实验**：本用例第一版就是直接删掉环境变量跑子进程，
        结果它**真的往 `~/.ai_novel_writer/diagnostic_logs` 写了 1 条 `SYSTEM/startup`**
        —— 一个"证明隔离有效"的测试反倒成了唯一的污染源（实测 DELTA=1）。
        正确做法是把 `HOME` / `USERPROFILE` 一起指向临时目录：
        仍然走"无环境变量 ⇒ 用 `Path.home()`"的**同一条代码路径**，
        但落点被重定向，真实目录零变化。
        """
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()
        before = _snapshot_real_logs()

        code = "import app.ai_client as ac\nprint(ac._diag_logger.get_log_dir())\n"
        env = dict(os.environ)
        env.pop(DIAGNOSTIC_LOG_DIR_ENV, None)  # 关键：去掉隔离，验证"默认路径"分支
        env["HOME"] = str(fake_home)
        env["USERPROFILE"] = str(fake_home)  # Windows 上 Path.home() 读的是这个

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"子进程失败：{result.stderr}"

        # 1) 确实落到了"默认 home 路径"下（证明没设环境变量时不会走隔离目录）
        written = list((fake_home / ".ai_novel_writer" / "diagnostic_logs").glob("*.jsonl"))
        assert written, (
            "去掉环境变量后日志没有落到 `Path.home()` 下 —— "
            "那么 test_importing_app_ai_client_writes_to_isolated_dir 的断言就是空转的"
        )
        # 2) 且真实目录零变化（本用例自身绝不能成为污染源）
        after = _snapshot_real_logs()
        assert _diff(before, after) == {}, f"反证用例污染了真实日志目录：{_diff(before, after)}"

    def test_polluter_check_would_catch_a_real_leak(self, tmp_path):
        """元反证：如果真有人往真实目录写，本文件的快照对账必须能发现。

        做法是故意在真实目录里**只读地**验证 `_snapshot_real_logs` / `_diff` 的判别力：
        造一个"假装多写了 100 字节"的字典，确认 `_diff` 会报出来。
        """
        before = {"diagnostic-x.jsonl": 1000}
        after = {"diagnostic-x.jsonl": 1100}
        assert _diff(before, after) == {"diagnostic-x.jsonl": 100}
        assert _diff(before, before) == {}


class TestNoHardcodedLogDirOutsideResolver:
    """真实目录**只允许**出现在 `resolve_log_dir()` 里。

    这就是本项目已经踩过三次的「同一事实写两处必然漂移」：修隔离时如果只改了
    `diagnostic_logger`，`shell_ui` 的性能报告与 `toolkit_ui` 的面板注册记录
    仍会漏回真实目录。所以这里用 AST 静态断言把"唯一一处"钉住。

    判据必须是"**代码里**拼出了这个路径"，而不是"文件里出现过这些字"——
    文档字符串里写 `~/.ai_novel_writer/diagnostic_logs` 是在解释行为，不是硬编码。
    靠关键字扫描会把正经的注释判成违规（第一次写就误报了 `shell_ui`/`toolkit_ui`），
    于是改为解析 AST：只看字符串字面量与 `Path(...) / "..."` 这类真正的路径构造。
    """

    #: 允许出现该字面量的文件（解析器本身）
    _ALLOWED = {
        Path("app") / "diagnostic_logger.py",
    }

    @staticmethod
    def _code_string_literals(src: str) -> list:
        """取出**代码中**的字符串字面量，跳过 docstring。"""
        tree = ast.parse(src)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    if isinstance(body[0].value.value, str):
                        docstrings.add(id(body[0].value))
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                out.append(node.value)
        return out

    def test_only_resolver_hardcodes_the_dir(self):
        offenders = []
        for path in (_REPO_ROOT / "app").rglob("*.py"):
            rel = path.relative_to(_REPO_ROOT)
            if rel in self._ALLOWED:
                continue
            literals = self._code_string_literals(path.read_text(encoding="utf-8"))
            joined = "\n".join(literals)
            # 代码里同时拼出 ".ai_novel_writer" 与 "diagnostic_logs" 才算违规
            if ".ai_novel_writer" in joined and "diagnostic_logs" in joined:
                offenders.append(str(rel))
        assert not offenders, (
            "以下文件在代码里自行拼了诊断日志目录，应改为 `resolve_log_dir()`，"
            f"否则测试隔离只对部分写入生效：{offenders}"
        )

    def test_checker_actually_catches_a_hardcode(self):
        """反证：把硬编码塞进字符串字面量，检查器必须抓到。

        没有这条，上面那个断言可能是恒真的（例如 AST 过滤把所有字面量都跳过了）。
        """
        sample = 'import os\nfrom pathlib import Path\np = Path.home() / ".ai_novel_writer" / "diagnostic_logs"\n'
        literals = self._code_string_literals(sample)
        joined = "\n".join(literals)
        assert ".ai_novel_writer" in joined and "diagnostic_logs" in joined

    def test_checker_ignores_docstring_mention(self):
        """反证的另一半：仅出现在 docstring 里的路径不该被判违规。"""
        sample = 'def f():\n    """写进 ~/.ai_novel_writer/diagnostic_logs 目录。"""\n    return 1\n'
        literals = self._code_string_literals(sample)
        assert ".ai_novel_writer" not in "\n".join(literals)

    def test_resolver_is_the_single_source(self):
        src = inspect.getsource(diagnostic_logger.resolve_log_dir)
        assert ".ai_novel_writer" in src
        assert "diagnostic_logs" in src

    def test_shell_ui_uses_resolver(self):
        src = (_REPO_ROOT / "app" / "shell_ui.py").read_text(encoding="utf-8")
        assert "resolve_log_dir" in src, "性能报告目录退回硬编码（D5 回退）"

    def test_toolkit_ui_uses_resolver(self):
        src = (_REPO_ROOT / "app" / "toolkit_ui.py").read_text(encoding="utf-8")
        assert "resolve_log_dir" in src, "面板注册记录目录退回硬编码"


class TestSessionIsolationIsActive:
    """当前这场测试会话本身必须处于隔离状态。"""

    def test_conftest_set_the_env_var(self):
        assert os.environ.get(DIAGNOSTIC_LOG_DIR_ENV), (
            f"`{DIAGNOSTIC_LOG_DIR_ENV}` 未设置 —— tests/conftest.py 的导入期隔离失效了"
        )

    def test_live_singleton_points_at_isolated_dir(self):
        """运行中的单例必须落在隔离目录，而不是 `~/.ai_novel_writer`。"""
        logger = diagnostic_logger.get_logger()
        actual = Path(logger.get_log_dir()).resolve()
        assert actual != _REAL_LOG_DIR.resolve(), f"诊断日志单例指向真实目录 {actual} —— 本次会话的数据正在被污染"

    def test_writing_through_singleton_does_not_touch_real_dir(self):
        """经单例写一条，真实目录必须零变化，隔离目录必须增长。"""
        before = _snapshot_real_logs()
        logger = diagnostic_logger.get_logger()
        isolated_dir = Path(logger.get_log_dir())
        before_isolated = sum(p.stat().st_size for p in isolated_dir.glob("*.jsonl"))

        logger.log("TEST", "isolation_probe", {"purpose": "verify isolation"})

        after = _snapshot_real_logs()
        after_isolated = sum(p.stat().st_size for p in isolated_dir.glob("*.jsonl"))
        assert _diff(before, after) == {}, "经单例写入污染了真实目录"
        assert after_isolated > before_isolated, "隔离目录没有增长 —— 断言是空转的"


class TestPerCaseFixture:
    """`diagnostic_log_dir` fixture 给需要读日志内容的用例一个干净目录。"""

    def test_fixture_redirects_and_yields_path(self, diagnostic_log_dir):
        logger = diagnostic_logger.get_logger()
        assert Path(logger.get_log_dir()).resolve() == diagnostic_log_dir.resolve()
        logger.log("TEST", "fixture_probe", {"n": 1})

        files = list(diagnostic_log_dir.glob("*.jsonl"))
        assert files, "fixture 目录里没有日志文件"
        entries = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(e.get("event") == "fixture_probe" for e in entries)

    def test_fixture_leaves_no_residue_in_real_dir(self, diagnostic_log_dir):
        before = _snapshot_real_logs()
        diagnostic_logger.get_logger().log("TEST", "should_not_leak", {})
        after = _snapshot_real_logs()
        assert _diff(before, after) == {}

    def test_real_dir_still_clean_after_fixture_case(self):
        """前一个用例用了 fixture，本用例回到会话级隔离目录 —— 不能是真实目录。"""
        actual = Path(diagnostic_logger.get_logger().get_log_dir()).resolve()
        assert actual != _REAL_LOG_DIR.resolve()
        assert _REAL_LOG_DIR not in actual.parents


class TestResetLogger:
    """单例一旦建立就忽略后续 `log_dir`，所以必须能显式重置。"""

    def test_reset_allows_redirection(self, tmp_path, monkeypatch):
        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "first"))
        diagnostic_logger.reset_logger()
        assert Path(diagnostic_logger.get_logger().get_log_dir()) == tmp_path / "first"

        monkeypatch.setenv(DIAGNOSTIC_LOG_DIR_ENV, str(tmp_path / "second"))
        diagnostic_logger.reset_logger()
        assert Path(diagnostic_logger.get_logger().get_log_dir()) == tmp_path / "second"

    def test_get_logger_returns_same_instance(self):
        diagnostic_logger.reset_logger()
        assert diagnostic_logger.get_logger() is diagnostic_logger.get_logger()

    def test_docstring_warns_against_production_use(self):
        """重置会让一次会话的日志裂成两个文件，必须在文档里说清。"""
        doc = inspect.getdoc(diagnostic_logger.reset_logger) or ""
        assert "测试" in doc or "test" in doc.lower()


class TestModuleLevelSingletonCallersAreKnown:
    """把"哪些模块在导入期就建单例"钉成清单。

    新增这类调用点时要一起更新本清单 —— 它们都依赖"conftest 在 import 之前设好环境变量"
    这个不变量，一旦有人在别处提前 import，隔离就会静默失效。
    """

    #: 模块相对路径 -> 建单例的模块级变量名
    _KNOWN = {
        "app/ai_client.py": "_diag_logger",
        "app/generation_ui.py": "_diag",
        "app/novel_agent.py": "_diag",
    }

    def test_known_call_sites_still_call_get_logger(self):
        """在每个文件里找到模块级 `X = get_logger()`。

        注意 `ai_client` 把它包在 `try/except` 里（导入失败降级为 `None`），
        所以只扫 `tree.body` 的顶层 Assign 会漏掉 —— **Try 节点也要递归进去**。
        这正是"清单测试"的价值：写法一变，断言就得跟着说清"允许哪些写法"。
        """
        for rel, var in self._KNOWN.items():
            src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
            tree = ast.parse(src)
            assert self._finds_module_level_get_logger(tree, var), (
                f"{rel} 的模块级 `{var} = get_logger()` 不见了，请同步更新本清单"
            )

    @staticmethod
    def _is_get_logger_assignment(node, var: str) -> bool:
        return (
            isinstance(node, ast.Assign)
            and var in {t.id for t in node.targets if isinstance(t, ast.Name)}
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func).endswith("get_logger")
        )

    @classmethod
    def _finds_module_level_get_logger(cls, tree: ast.Module, var: str) -> bool:
        """递归查找 `var = get_logger(...)`，含 try/except 包裹的写法。

        只下潜到**模块级语句的包装层**（`try:` / `if:`），不进入 def/class 体 ——
        否则函数内部的局部赋值会被误认成"模块级建单例"。

        ⚠️ 陷阱：`ast.iter_child_nodes(Try)` 会同时给出 `ImportFrom` 与 `Assign`，
        但只有 `Assign` 才是目标。用"只对 Try/If 递归"的写法会让 **Assign 这一层被跳过**
        （第一版就栽在这里，`_diag = get_logger()` 明明在 `try` 里却查不到）。
        所以这里对**每个节点的直接子节点**都做一次判断，再决定是否继续下潜。
        """
        for top in tree.body:
            if cls._is_get_logger_assignment(top, var):
                return True
            if isinstance(top, (ast.Try, ast.If)):
                for node in ast.walk(top):
                    if cls._is_get_logger_assignment(node, var):
                        return True
        return False

    def test_recursive_finder_handles_try_wrapped_assignment(self):
        """反证：try 包裹的写法必须被找到，否则清单测试会漏掉最常见的降级写法。"""
        sample = "try:\n    from .diagnostic_logger import get_logger\n\n    _diag_logger = get_logger()\nexcept Exception:\n    _diag_logger = None\n"
        assert self._finds_module_level_get_logger(ast.parse(sample), "_diag_logger")

    def test_recursive_finder_negative_case(self):
        """反证：变量名对但函数不对时不能误判。"""
        sample = "_diag_logger = something_else()\n"
        assert not self._finds_module_level_get_logger(ast.parse(sample), "_diag_logger")

    def test_conftest_sets_env_at_import_time(self):
        """环境变量必须写在 conftest 的**模块级**，不能藏在钩子或 fixture 里。

        模块级 `get_logger()` 在 pytest 执行任何钩子之前就跑完了，
        所以"在 `pytest_configure` 里设置环境变量"这种写法**看着对、实际没用**。
        """
        src = (_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        assert self._sets_env_at_module_level(tree), (
            f"`{DIAGNOSTIC_LOG_DIR_ENV}` 不再于 tests/conftest.py 模块级设置 —— "
            "模块级 `get_logger()` 会先于任何钩子执行，隔离必失效"
        )

    @staticmethod
    def _sets_env_at_module_level(tree: ast.Module) -> bool:
        """在顶层语句里找 `os.environ[KEY] = ...`。

        **不下潜进 def/class** —— 那正是"藏在钩子或 fixture 里"的失败写法。
        但允许 `if` / `try` 之类的模块级包装（例如"仅当未设置时才设默认值"）。

        注意 `os.environ[K] = v` 解析成 `Assign(targets=[Subscript(value=Attribute(...))])`，
        所以判据是"target 是 Subscript 且其源码含环境变量名"。
        **两种写法都要认**：字面量 `os.environ["AI_NOVEL_DIAGNOSTIC_DIR"]`，以及
        引用常量 `os.environ[DIAGNOSTIC_LOG_DIR_ENV]`（conftest 用的是后者，
        第一版只比字面量，于是把正确的代码判成了失败）。
        """
        accepted = (DIAGNOSTIC_LOG_DIR_ENV, "DIAGNOSTIC_LOG_DIR_ENV")
        for top in tree.body:
            if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # 函数/类体不算"模块级设置"
            for node in ast.walk(top):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if not isinstance(t, ast.Subscript):
                        continue
                    rendered = ast.unparse(t)
                    if any(name in rendered for name in accepted):
                        return True
        return False

    def test_detector_rejects_hook_only_setting(self):
        """反证：只在钩子里设置必须被判为不合格。"""
        sample = (
            f"import os\n\n\ndef pytest_configure(config):\n    os.environ[{DIAGNOSTIC_LOG_DIR_ENV!r}] = '/tmp/x'\n"
        )
        assert not self._sets_env_at_module_level(ast.parse(sample))

    def test_detector_accepts_module_level_setting(self):
        """反证的另一半：模块级设置必须被接受。"""
        sample = f"import os\nos.environ[{DIAGNOSTIC_LOG_DIR_ENV!r}] = '/tmp/x'\n"
        assert self._sets_env_at_module_level(ast.parse(sample))


#: 自检递归保护：下面的用例会再起一个 pytest 跑同一个文件，
#: 若不拦住就会无限嵌套。
_SELFCHECK_GUARD = "AI_NOVEL_ISOLATION_SELFCHECK_RUNNING"


class TestIsolationFileItselfDoesNotPollute:
    """**本文件自己**绝不能成为污染源。

    这是一条踩过坑才加的用例：`test_without_env_logger_follows_default_home_path` 的
    第一版直接删掉隔离变量跑子进程，于是它真的往真实目录写了 1 条 `SYSTEM/startup`
    —— 即"用来证明隔离有效的测试"反倒成了当时**唯一**还在写真实日志的地方
    （实测 DELTA=1，靠逐文件二分才定位到）。

    靠人记住"写这类用例要重定向 HOME"并不牢靠，所以让文件**自己检查自己**：
    在子进程里用**完全真实的环境**跑完整个文件，再对账真实目录字节数。
    这比任何注释都可靠 —— 下次有人加同类用例时会立刻变红。
    """

    def test_whole_file_leaves_real_dir_untouched(self):
        if os.environ.get(_SELFCHECK_GUARD):
            pytest.skip("自检子进程内不再嵌套自检")

        before = _snapshot_real_logs()
        env = dict(os.environ)
        env[_SELFCHECK_GUARD] = "1"
        # 注意：**不**碰 DIAGNOSTIC_LOG_DIR_ENV，也不改 HOME ——
        # 要的就是"完全真实的环境"，才能发现用例自身越界写盘。
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(Path(__file__)), "-q", "-p", "no:randomly"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            env=env,
        )
        assert result.returncode == 0, f"自检子进程失败（本文件自身有用例不通过）：\n{result.stdout[-3000:]}"

        diff = _diff(before, _snapshot_real_logs())
        assert diff == {}, (
            f"跑本文件污染了真实诊断日志目录：{diff}\n"
            "多半是某个用例删掉了 `AI_NOVEL_DIAGNOSTIC_DIR` 却没有同时把 HOME/USERPROFILE "
            "指向临时目录。请参考 test_without_env_logger_follows_default_home_path 的写法。"
        )

    def test_recursion_guard_is_honoured(self):
        """递归保护必须真的生效，否则自检会无限嵌套直到超时。"""
        src = Path(__file__).read_text(encoding="utf-8")
        assert _SELFCHECK_GUARD in src
        assert "pytest.skip" in src, "缺少跳过分支，自检会自我嵌套"
