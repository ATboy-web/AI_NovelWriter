"""打包校验清单的守门测试。

`scripts/check_bundle.py` 的两张清单（必需 / 声明但未用）是**对源码的手工归纳**——
而手工归纳会漂移：有人给 `app/` 加上 `import markdown`，清单里"声明但未用"就成了假话，
之后再构建 EXE 就会漏掉一个真需要的包，而且**不报错**。

"同一事实写两处必然漂移"在本项目已踩过多次。这里的做法不是再抄一遍清单，
而是**让测试从源码重新推导，再与清单对账**：

- `REQUIRED_BY_IMPORT` 里的每个模块，必须**真的能在 `app/` 里找到 import**；
- `DECLARED_BUT_UNUSED` 里的每个模块，必须**真的在 `app/` 里找不到 import**。

这样清单一旦过期，测试立刻变红，而不是等到用户的 EXE 少个功能才发现。
"""

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import check_bundle  # noqa: E402


def _imported_top_level_names() -> set:
    """扫 `app/` 下所有模块的 import，返回被导入的顶层包名。

    要同时覆盖 `import x` / `import x.y` / `from x import y` / `from x.y import z`
    四种写法 —— 只查一种会漏（本项目"判死代码只 grep 方法名"就栽过这个坑）。
    函数体内的 import 也要算：本仓的关键依赖（docx / ebooklib / pypdf）全都在函数里
    （为了"用到才加载"），只扫模块级会把它们判成"未使用"。
    """
    names = set()
    for path in (_REPO_ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                # 相对导入（level>0）指向本包内部，不是第三方依赖
                if node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
    return names


@pytest.fixture(scope="module")
def imported_names():
    return _imported_top_level_names()


class TestRequiredListIsGroundedInSource:
    """`REQUIRED_BY_IMPORT` 里的每一项都必须真的被 import。"""

    def test_every_required_module_is_actually_imported(self, imported_names):
        false_claims = sorted(m for m in check_bundle.REQUIRED_BY_IMPORT if m not in imported_names)
        assert not false_claims, (
            f"这些模块被列进「必需」但 app/ 里根本没人 import：{false_claims}\n"
            "要么删掉该条（它不必进 EXE），要么补上真实的调用点说明。\n"
            "若它是传递依赖，应放进 REQUIRED_TRANSITIVE。"
        )

    def test_required_list_is_not_empty(self):
        assert check_bundle.REQUIRED_BY_IMPORT, "必需清单为空等于没有校验"

    def test_transitive_list_is_really_transitive(self, imported_names):
        """`REQUIRED_TRANSITIVE` 里的模块**不能**同时被 app/ 直接 import。

        否则它该待在 `REQUIRED_BY_IMPORT` 里 —— 分类错了会让"必需"判据失去区分力
        （第一版就是把 `lxml` 放错类别，被本文件的守门测试抓出来的）。
        """
        misplaced = sorted(m for m in check_bundle.REQUIRED_TRANSITIVE if m in imported_names)
        assert not misplaced, f"这些模块其实被 app/ 直接 import 了，不该放在「传递依赖」里：{misplaced}"

    def test_transitive_list_is_not_empty(self):
        assert check_bundle.REQUIRED_TRANSITIVE, "传递依赖清单为空；python-docx 的 lxml 应至少在里面"

    def test_two_required_lists_do_not_overlap(self):
        overlap = set(check_bundle.REQUIRED_BY_IMPORT) & set(check_bundle.REQUIRED_TRANSITIVE)
        assert not overlap, f"同一模块同时出现在两张必需清单里：{sorted(overlap)}"


class TestDeclaredUnusedListIsGroundedInSource:
    """`DECLARED_BUT_UNUSED` 里的每一项都必须真的**没有**被 import。

    这条是防"清单过期"的关键：有人给 app/ 加上 `import markdown` 之后，
    清单若不同步，构建时就会漏掉一个真需要的包 —— 而且**不报错**。
    """

    def test_declared_unused_modules_are_really_unused(self, imported_names):
        stale = sorted(m for m in check_bundle.DECLARED_BUT_UNUSED if m in imported_names)
        assert not stale, (
            f"这些模块已被 app/ import，但仍被列为「声明但未用」：{stale}\n"
            "请把它们移进 REQUIRED_BY_IMPORT（否则构建出的 EXE 会缺这个包且不报错）。"
        )

    def test_beautifulsoup4_entry_uses_import_name(self):
        """`beautifulsoup4` 的 **import 名**是 `bs4`，清单键必须用 import 名。

        否则 `test_declared_unused_modules_are_really_unused` 永远为真（因为没人
        `import beautifulsoup4`），成了一个空转断言。
        """
        assert "bs4" in check_bundle.DECLARED_BUT_UNUSED
        assert "beautifulsoup4" not in check_bundle.DECLARED_BUT_UNUSED

    def test_every_key_is_an_import_name(self, imported_names):
        """清单里的键都必须是**合法的 import 名**（小写、无连字符）。

        `python-docx` / `beautifulsoup4` 这类发行名混进来会让断言空转。
        """
        bad = [k for k in check_bundle.DECLARED_BUT_UNUSED if k != k.lower() or "-" in k]
        assert not bad, f"这些键不是 import 名（是发行名）：{bad}"


class TestIntentionalExcludesMatchSpec:
    """有意排除清单必须与 `installer/novel_app.spec` 一致。

    `INTENTIONAL_EXCLUDES` 说"这是有意排除的、别当缺口"；如果 spec 里其实**没有**排除它，
    那这句话就是假的，会掩盖一个真缺口（例如某天 spec 的 excludes 被清空）。
    """

    def _spec_excludes(self) -> set:
        spec = (_REPO_ROOT / "installer" / "novel_app.spec").read_text(encoding="utf-8")
        tree = ast.parse(spec)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Analysis":
                for kw in node.keywords:
                    if kw.arg == "excludes":
                        return set(ast.literal_eval(kw.value))
        raise AssertionError("在 novel_app.spec 里找不到 Analysis(..., excludes=[...])")

    def test_every_intentional_exclude_is_in_spec(self):
        spec_excludes = self._spec_excludes()
        phantom = sorted(m for m in check_bundle.INTENTIONAL_EXCLUDES if m not in spec_excludes)
        assert not phantom, (
            f"这些模块被标为「有意排除」，但 spec 的 excludes 里并没有它们：{phantom}\n"
            "要么补进 spec，要么从清单删除 —— 否则它会掩盖一个真缺口。"
        )

    def test_spec_excludes_nothing_required(self):
        """反向守卫：不能一边说某模块必需，一边在 spec 里排除它。

        这正是 `PIL` 的历史状态（pyproject 声明 Pillow，spec 却排除 PIL）——
        之所以现在不算缺口，是因为代码里有显式降级分支，且 PIL **不在**必需清单里。
        """
        spec_excludes = self._spec_excludes()
        conflict = sorted(set(check_bundle.REQUIRED_BY_IMPORT) & spec_excludes)
        assert not conflict, (
            f"这些模块既被列为「必需」又被 spec 排除：{conflict}\n构建产物一定会缺它们，且应用不会报错只会静默丢功能。"
        )


class TestTocParsingIsRobust:
    """TOC 解析必须能在真实产物上工作，且不能退化成字符串匹配。"""

    def test_analyse_handles_synthetic_toc(self):
        # 形状取自真实 Analysis-00.toc：索引 5=excludes, 14=pure, 15=bins, 18=datas
        toc = (
            [],
            [],
            [],
            [],
            {},
            ["PIL"],
            [],
            False,
            {},
            0,
            [],
            [],
            [],
            [],
            [("httpx", "p", "PYMODULE")],
            [],
            [],
            [],
            [("x", "p", "DATA")],
        )
        info = check_bundle.analyse(toc)
        assert "httpx" in info["pure"]
        assert info["excludes"] == {"PIL"}

    def test_has_module_matches_submodules(self):
        names = {"docx", "lxml.etree", "httpx._client"}
        assert check_bundle.has_module(names, "docx")
        assert check_bundle.has_module(names, "lxml")  # 子模块要算
        assert check_bundle.has_module(names, "httpx")
        assert not check_bundle.has_module(names, "pypdf")

    def test_pil_typecode_does_not_produce_false_positive(self):
        """回归：字符串搜索会把 TOC 的 `PIL` **类型标签**误判成 Pillow 包。

        这是写本脚本时真实踩到的坑 —— 于是判据从"文件里出现过 PIL"改为
        "解析后模块名集合里有 PIL"。
        """
        toc = (
            [],
            [],
            [],
            [],
            {},
            ["PIL"],
            [],
            False,
            {},
            0,
            [],
            [],
            [],
            [],
            [("httpx", "p", "PYMODULE")],
            [],
            [],
            [],
            [],
        )
        info = check_bundle.analyse(toc)
        assert "PIL" not in info["pure"], "把 excludes 里的 PIL 当成了已打包的模块"
        assert "PIL" not in info["all_names"]
