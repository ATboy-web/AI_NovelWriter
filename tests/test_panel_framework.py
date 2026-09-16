"""面板框架测试（v3 §2.2）。

框架的验收标准只有一条硬指标：**新增一个面板只需 1 处改动**
（v2 要改 5 处：新建文件 + `panels/__init__` + `novel_app` + `shell_ui` 的 Radiobutton
+ `toolkit_ui` 的 elif 链）。本文件用三种方式锁死它：

1. **机制验证**：带 `key` 的子类被自动登记；`NATIVE_PANEL_MODULES` 是唯一的原生清单
2. **回归断言**：`toolkit_ui` 里不得再出现 `_build_*_tool` 分发链、
   `shell_ui` 里不得再出现硬编码的面板键（源码扫描，先剔除注释与文档字符串）
3. **覆盖断言**：`app/panels/` 下每个 `*_panel.py` 都必须被登记表覆盖 ——
   新建了面板文件却忘了登记，这是"静默失灵"最常见的一种

迁移适配器的代理语义（读走宿主、写也走宿主、容器留给自己）用**假 Mixin + 假控件**验证，
不创建真实 Tk 根窗口（CI 无显示环境）。
"""

import re
import sys
from pathlib import Path

import pytest

from app.events import TOPIC_CHAPTER_SAVED, TOPIC_NOVEL_OPENED
from app.panels import registry
from app.panels.base import BasePanel
from app.panels.host import PanelHost
from app.panels.legacy import LEGACY_PANEL_SPECS, LegacyPanelAdapter, _make_adapter_class
from app.ui_style import UIStyle

sys.path.insert(0, str(Path(__file__).parent))
import _source_scan as _scan  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
PANELS_DIR = REPO_ROOT / "app" / "panels"

#: 框架自身文件（不是面板，不参与"每个模块都要被登记"的覆盖检查）
FRAMEWORK_MODULES = {"__init__.py", "base.py", "registry.py", "legacy.py", "host.py"}


@pytest.fixture(scope="module")
def loaded():
    """把面板登记表载入（幂等）。"""
    registry.load_panels()
    return registry


# ============================================================ 假宿主 / 假控件


class FakeApp:
    """最小宿主：提供共享状态供面板代理读取。"""

    def __init__(self):
        self.ai_client = "AI-CLIENT"
        self.current_novel_dir = "/tmp/novel"
        self.genre_var = "科幻"
        self.logs = []

    def _log(self, message):
        self.logs.append(message)


class FakeWidget:
    """只实现面板框架用到的那几个方法。"""

    def __init__(self, *args, **kwargs):
        self.children = []
        self.destroyed = 0
        self.pack_calls = []
        self.pack_forget_calls = 0
        self.options = kwargs

    # 容器协议
    def winfo_children(self):
        """Tk 的语义：控件被销毁后就不再是父控件的子项。"""
        return [child for child in self.children if child.destroyed == 0]

    def destroy(self):
        self.destroyed += 1
        self.children.clear()

    def pack(self, **kwargs):
        self.pack_calls.append(kwargs)

    def pack_forget(self):
        self.pack_forget_calls += 1

    def cget(self, key):
        return "#101020" if key == "bg" else ""


class FakeMixin:
    """冒充 v2 面板 Mixin：构建时写控件属性、读宿主状态。"""

    def _build_fake_tool(self):
        frame = self.tool_content_frame  # 必须解析到**本面板自己的**容器
        frame.children.append(FakeWidget())  # 模拟"往容器里画了一个控件"
        self.fake_result = ("widget", frame)  # 写入 → 应落到宿主
        self.read_back = self.ai_client  # 读取 → 走宿主代理
        # ⚠️ `self.x += 1` 会先读 `x`：读取走代理（面板 → 宿主），
        # 宿主没有就 AttributeError —— 与 v2 完全一致（见 legacy.py 模块文档）。
        self.build_count = getattr(self, "build_count", 0) + 1


def _fake_adapter_cls():
    """造一个假 Mixin 的适配器类（**只造一次**，与 `legacy._ADAPTER_CLASSES` 同理）。

    重复 `type(...)` 会得到不同类却共用同一个 key，注册表会（正确地）报重复。
    造好后立刻从全局表里摘掉：它只是探针，不该影响 `all_panels()` 的计数。
    """
    global _FAKE_ADAPTER_CLS
    if _FAKE_ADAPTER_CLS is None:
        _FAKE_ADAPTER_CLS = type(
            "FakeLegacyPanel",
            (LegacyPanelAdapter,),
            {
                "key": "fake-adapter",
                "title": "假面板",
                "category": "运维",
                "order": 999,
                "_legacy_build_func": staticmethod(FakeMixin._build_fake_tool),
                "source_module": "tests.fake",
            },
        )
        registry.PANEL_REGISTRY.pop("fake-adapter", None)
    return _FAKE_ADAPTER_CLS


_FAKE_ADAPTER_CLS = None


def _make_fake_adapter(app):
    return _fake_adapter_cls()(app)


def _drop(key):
    registry.PANEL_REGISTRY.pop(key, None)


# ============================================================ 注册表


class TestRegistry:
    def test_all_legacy_panels_are_registered(self, loaded):
        registered = {spec.key for spec in loaded.all_panels() if spec.legacy}
        expected = {spec.key for spec in LEGACY_PANEL_SPECS}
        assert registered == expected
        assert len(expected) == 12  # v2 的 12 个工具面板一个不少

    def test_panel_metadata_is_complete(self, loaded):
        for spec in loaded.all_panels():
            assert spec.key and spec.title and spec.category
            assert spec.category in loaded.CATEGORY_ORDER, spec.category
            assert isinstance(spec.order, int)

    def test_grouped_follows_category_order_and_is_lossless(self, loaded):
        groups = loaded.grouped()
        names = [name for name, _specs in groups]
        assert names == loaded.categories()
        # 分组顺序必须与 CATEGORY_ORDER 一致（未登记的分组排在最后）
        index = {name: i for i, name in enumerate(loaded.CATEGORY_ORDER)}
        assert names == sorted(names, key=lambda n: index.get(n, len(index)))
        # 分组不得丢面板
        assert sum(len(specs) for _n, specs in groups) == len(loaded.all_panels())

    def test_default_key_is_the_first_panel(self, loaded):
        assert loaded.default_key() == loaded.all_panels()[0].key
        assert loaded.default_key() == "elements"  # 与 v2 的默认工具页一致

    def test_duplicate_key_is_rejected(self):
        class First(BasePanel):
            key = "dup-key-probe"
            title = "A"

        try:
            with pytest.raises(ValueError, match="重复"):

                class Second(BasePanel):
                    key = "dup-key-probe"
                    title = "B"
        finally:
            _drop("dup-key-probe")

    def test_missing_key_is_rejected(self):
        with pytest.raises(ValueError, match="缺少 key"):

            class NoKey(BasePanel):
                title = "没有 key"

            registry.register(NoKey)

    def test_reregistering_same_class_is_idempotent(self, loaded):
        spec = loaded.get("elements")
        again = registry.register(spec.panel_cls)
        assert again is spec

    def test_get_and_create_unknown_key(self, loaded):
        assert loaded.get("does-not-exist") is None
        with pytest.raises(KeyError):
            loaded.create("does-not-exist", FakeApp())

    def test_subclass_with_key_auto_registers(self, loaded):
        """「新增面板只需 1 处改动」的机制保证：类一被定义就进表。"""

        class AutoPanel(BasePanel):
            key = "auto-register-probe"
            title = "自动登记"
            category = "运维"

        try:
            assert loaded.get("auto-register-probe") is not None
        finally:
            _drop("auto-register-probe")

    def test_load_panels_is_idempotent(self, loaded):
        before = len(loaded.all_panels())
        loaded.load_panels()
        loaded.load_panels(force=True)
        assert len(loaded.all_panels()) >= before
        assert loaded.get("elements") is not None


# ============================================================ 登记覆盖（防漏登记）


class TestRegistrationCoverage:
    def test_every_panel_module_is_registered(self, loaded):
        """新建了 `*_panel.py` 却忘了登记 → 面板存在但选不到（v2 的典型静默故障）。"""
        covered = {spec.module for spec in LEGACY_PANEL_SPECS}
        covered |= set(loaded.NATIVE_PANEL_MODULES)

        actual = {
            f"app.panels.{path.stem}"
            for path in PANELS_DIR.glob("*.py")
            if path.name not in FRAMEWORK_MODULES and path.name.endswith("_panel.py")
        }

        assert actual - covered == set(), f"这些面板文件没有被任何登记表覆盖：{sorted(actual - covered)}"
        assert covered - actual == set(), f"登记表指向了不存在的面板模块：{sorted(covered - actual)}"

    def test_legacy_specs_point_to_real_build_methods(self):
        for spec in LEGACY_PANEL_SPECS:
            module_src = _scan.read(f"{spec.module.replace('.', '/')}.py")
            assert f"class {spec.mixin}" in module_src, f"{spec.module} 里没有 {spec.mixin}"
            assert f"def {spec.build}(" in module_src, f"{spec.module} 里没有 {spec.build}()"
            # 一个模块恰好一个构建方法 —— 多一个说明表格与方法名已经对不上了
            builders = re.findall(r"def (_build_\w+_tool)\(", module_src)
            assert builders == [spec.build], f"{spec.module} 的构建方法为 {builders}"

    def test_every_legacy_spec_produces_a_panel_class(self):
        for spec in LEGACY_PANEL_SPECS:
            adapter = _make_adapter_class(spec)
            assert issubclass(adapter, LegacyPanelAdapter)
            assert adapter.key == spec.key
            assert adapter.proxy_writes is True


# ============================================================ 代理语义（迁移核心）


class TestBasePanelProxy:
    def test_read_falls_back_to_host(self):
        app = FakeApp()
        panel = BasePanel(app)
        assert panel.ai_client == app.ai_client
        assert panel.current_novel_dir == app.current_novel_dir
        # 方法代理必须仍然**调用到宿主**（绑定方法每次取值都是新对象，不能用 is 比较）
        panel._log("hello")
        assert app.logs == ["hello"]

    def test_own_attribute_wins_over_host(self):
        app = FakeApp()
        panel = BasePanel(app)
        panel.ai_client = "OWN"
        assert panel.ai_client == "OWN"

    def test_writes_stay_local_by_default(self):
        """v3 原生面板：属性写在自己身上，不污染宿主（15 个面板共享宿主会互相踩）。"""
        app = FakeApp()
        panel = BasePanel(app)
        panel.temp_state = 42
        assert panel.temp_state == 42
        assert "temp_state" not in app.__dict__

    def test_writes_forward_to_host_when_proxy_writes(self):
        """迁移面板：写入落点必须与 v2 一致（v2 里 `self` 就是应用）。"""
        app = FakeApp()
        panel = _make_fake_adapter(app)
        panel.fake_result = "WIDGET"
        assert app.fake_result == "WIDGET"
        assert "fake_result" not in panel.__dict__

    def test_private_and_local_names_never_forwarded(self):
        app = FakeApp()
        panel = _make_fake_adapter(app)
        panel._private_flag = 1
        panel.tool_content_frame = "FRAME"

        assert panel._private_flag == 1
        assert panel.__dict__["tool_content_frame"] == "FRAME"
        assert "_private_flag" not in app.__dict__
        assert "tool_content_frame" not in app.__dict__

    def test_dunder_names_are_never_proxied(self):
        """`copy`/`pickle` 会探测一堆 dunder；命中宿主只会得到迷惑行为。"""
        app = FakeApp()
        app.__wrapped__ = "宿主上的属性"
        panel = BasePanel(app)
        with pytest.raises(AttributeError):
            panel.__wrapped__

    def test_unbound_panel_raises_clear_error(self):
        panel = BasePanel(None)
        with pytest.raises(AttributeError, match="未绑定宿主"):
            panel.anything

    def test_build_must_be_implemented(self):
        panel = BasePanel(FakeApp())
        with pytest.raises(NotImplementedError):
            panel.build(FakeWidget())

    def test_lifecycle_flags(self):
        panel = BasePanel(FakeApp())
        assert panel.is_built is False
        panel.mark_built()
        assert panel.is_built is True

    def test_detach_releases_host_but_calls_on_hide(self):
        calls = []

        class P(BasePanel):
            def on_hide(self):
                calls.append("hide")

        panel = P(FakeApp())
        panel.mark_built()
        panel.detach()

        assert calls == ["hide"]
        assert panel.app is None
        assert panel.is_built is False


class TestAdapterRendering:
    def test_adapter_owns_its_container(self):
        """15 个面板共用一个 `tool_content_frame` 会互相覆盖 —— 必须各有一份。"""
        app = FakeApp()
        first = _make_fake_adapter(app)
        second = _make_fake_adapter(app)
        frame_a, frame_b = FakeWidget(), FakeWidget()

        first.build(frame_a)
        second.build(frame_b)

        assert len(frame_a.winfo_children()) == 1
        assert len(frame_b.winfo_children()) == 1
        assert frame_a.winfo_children()[0] is not frame_b.winfo_children()[0]
        assert "tool_content_frame" not in app.__dict__

    def test_adapter_writes_land_on_host_and_reads_see_them(self):
        app = FakeApp()
        panel = _make_fake_adapter(app)
        frame = FakeWidget()

        panel.build(frame)

        # 写入落到宿主（v2 语义），且读回来是同一个对象
        assert app.fake_result == ("widget", frame)
        assert panel.fake_result == ("widget", frame)
        assert panel.read_back == "AI-CLIENT"
        assert panel.is_built is True

    def test_on_show_rebuilds_like_v2(self):
        """v2 的 `_refresh_toolkit()` 每次选择都销毁重建，观感必须保持。"""
        app = FakeApp()
        panel = _make_fake_adapter(app)
        frame = FakeWidget()

        panel.build(frame)
        assert len(frame.winfo_children()) == 1
        assert app.build_count == 1
        first_child = frame.winfo_children()[0]

        panel.on_show()

        assert first_child.destroyed == 1  # 旧内容被清掉
        assert len(frame.winfo_children()) == 1  # 又画了一份
        assert frame.winfo_children()[0] is not first_child
        assert app.build_count == 2
        assert app.fake_result[1] is frame

    def test_build_func_is_a_plain_function(self):
        spec = LEGACY_PANEL_SPECS[0]
        adapter = _make_adapter_class(spec)
        assert isinstance(adapter._legacy_build_func, type(FakeMixin._build_fake_tool))
        assert adapter._legacy_build_func.__qualname__.endswith(spec.build)

    def test_missing_container_is_reported_not_crashed(self):
        """未先 `build()` 就 `on_show()` 时不得抛错（宿主可能只在显示时构建）。"""
        app = FakeApp()
        panel = _make_fake_adapter(app)
        panel.mark_built()
        panel.on_show()  # 不应抛异常

    def test_read_of_attribute_missing_everywhere_raises_like_v2(self):
        """`self.x += 1` 这类"先读后写"要求宿主持有 `x` —— 与 v2 语义一致。

        v2 的 `NovelWriterApp.__init__` 预置 `dialogue_engine = None`、
        `story_flow_engine = None` 等一长串单例属性，正是为了让面板能这样读写；
        迁移后这些预置不能删，否则面板在构建中途就会 AttributeError。
        """
        app = FakeApp()
        panel = _make_fake_adapter(app)

        with pytest.raises(AttributeError):
            panel.never_defined_anywhere  # noqa: B018 - 就是要它抛

        app.predefined_engine = None
        assert panel.predefined_engine is None  # 宿主预置过的就能正常读写


# ============================================================ 事件订阅（显式声明）


class TestPanelEventSubscription:
    def test_no_declaration_means_no_subscription(self):
        """v2 迁移面板没有 `on_event`，订阅只会产生 12 个永不干活的处理器。"""
        from app.events import EventBus

        class Quiet(BasePanel):
            key = "quiet-probe"
            title = "安静"

        try:
            bus = EventBus(name="t")
            panel = Quiet(FakeApp())
            assert panel.attach_events(bus) == []
            assert bus.topics() == []
        finally:
            _drop("quiet-probe")

    def test_declared_topics_are_subscribed(self):
        from app.events import EventBus

        class Talkative(BasePanel):
            key = "talkative-probe"
            title = "健谈"
            topics_of_interest = (TOPIC_CHAPTER_SAVED,)

            def __init__(self, app=None):
                super().__init__(app)
                self.seen = []

            def on_event(self, topic, payload=None):
                self.seen.append((topic, payload))

        try:
            bus = EventBus(name="t")
            panel = Talkative(FakeApp())
            handles = panel.attach_events(bus)
            assert len(handles) == 1

            bus.publish(TOPIC_CHAPTER_SAVED, {"chapter": 1})
            bus.publish(TOPIC_NOVEL_OPENED, {"novel_dir": "x"})  # 未声明 → 不收

            assert panel.seen == [(TOPIC_CHAPTER_SAVED, {"chapter": 1})]
        finally:
            _drop("talkative-probe")

    def test_wildcard_declaration_collapses_to_single_subscription(self):
        from app.events import WILDCARD, EventBus

        class Everything(BasePanel):
            key = "everything-probe"
            title = "全部"
            topics_of_interest = (WILDCARD, TOPIC_CHAPTER_SAVED)

        try:
            bus = EventBus(name="t")
            handles = Everything(FakeApp()).attach_events(bus)
            assert len(handles) == 1  # 通配已覆盖，不重复订阅
            assert bus.subscriber_count(WILDCARD) == 1
        finally:
            _drop("everything-probe")


# ============================================================ 宿主生命周期


class TestPanelHost:
    @pytest.fixture
    def host_env(self, monkeypatch):
        """无 Tk 环境的宿主：用假控件顶替 `tk.Frame`。"""
        import app.panels.host as host_module

        monkeypatch.setattr(host_module.tk, "Frame", lambda *a, **kw: FakeWidget())

        class Recording(BasePanel):
            key = "host-recording-probe"
            title = "录制"
            category = "运维"
            topics_of_interest = (TOPIC_CHAPTER_SAVED,)

            def __init__(self, app=None):
                super().__init__(app)
                self.calls = []

            def build(self, parent):
                self.calls.append(("build", parent))
                self.mark_built()
                return parent

            def on_show(self):
                self.calls.append(("on_show",))

            def on_hide(self):
                self.calls.append(("on_hide",))

            def on_event(self, topic, payload=None):
                self.calls.append(("event", topic))

        class Other(Recording):
            key = "host-other-probe"
            title = "另一个"

        try:
            yield Recording, Other
        finally:
            _drop("host-recording-probe")
            _drop("host-other-probe")

    def _host(self, bus=None):
        app = FakeApp()
        app.event_bus = bus
        return PanelHost(app, FakeWidget(), bus=bus), app

    def test_select_unknown_key_returns_false(self, host_env):
        host, _app = self._host()
        assert host.select("nope") is False
        assert host.current_key == ""

    def test_first_select_builds_then_later_selects_call_on_show(self, host_env):
        Recording, _Other = host_env
        host, _app = self._host()

        assert host.select("host-recording-probe") is True
        panel = host.panel("host-recording-probe")
        assert [c[0] for c in panel.calls] == ["build"]
        assert host.current_key == "host-recording-probe"

        host.refresh()  # 重建：先清 built 标记再 build
        assert [c[0] for c in panel.calls] == ["build", "build"]

        host.select("host-recording-probe")
        assert panel.calls[-1] == ("on_show",)

    def test_switch_calls_on_hide_and_hides_frame(self, host_env):
        Recording, Other = host_env
        host, _app = self._host()

        host.select("host-recording-probe")
        first = host.panel("host-recording-probe")
        host.select("host-other-probe")

        assert ("on_hide",) in first.calls
        assert host.current_key == "host-other-probe"

    def test_select_sets_select_var(self, host_env):
        Recording, _Other = host_env
        app = FakeApp()
        app.event_bus = None
        var = type("Var", (), {"value": "", "set": lambda self, v: setattr(self, "value", v)})()
        host = PanelHost(app, FakeWidget(), select_var=var)

        host.select("host-recording-probe")
        assert var.value == "host-recording-probe"

    def test_broken_panel_does_not_break_host(self, host_env, monkeypatch):
        Recording, _Other = host_env

        class Exploding(Recording):
            key = "host-exploding-probe"
            title = "会炸"

            def build(self, parent):
                raise RuntimeError("构建失败")

        try:
            host, _app = self._host()
            assert host.select("host-exploding-probe") is False
        finally:
            _drop("host-exploding-probe")

    def test_broken_on_show_is_isolated(self, host_env):
        Recording, _Other = host_env
        host, _app = self._host()
        host.select("host-recording-probe")
        panel = host.panel("host-recording-probe")
        panel.on_show = lambda: 1 / 0
        host.select("host-recording-probe")  # 不应抛异常

    def test_panels_subscribe_through_host(self, host_env):
        from app.events import EventBus

        Recording, _Other = host_env
        bus = EventBus(name="t")
        host, _app = self._host(bus)

        host.select("host-recording-probe")
        panel = host.panel("host-recording-probe")

        bus.publish(TOPIC_CHAPTER_SAVED, {"chapter": 2})
        assert ("event", TOPIC_CHAPTER_SAVED) in panel.calls

    def test_notify_reaches_instantiated_panels_without_bus(self, host_env):
        Recording, _Other = host_env
        host, _app = self._host()
        host.select("host-recording-probe")

        assert host.notify(TOPIC_CHAPTER_SAVED, {}) == 1
        assert host.panel("host-recording-probe").calls[-1] == ("event", TOPIC_CHAPTER_SAVED)

    def test_novel_opened_refreshes_current_panel(self, host_env):
        from app.events import EventBus

        Recording, _Other = host_env
        bus = EventBus(name="t")
        host, _app = self._host(bus)
        host.select("host-recording-probe")
        panel = host.panel("host-recording-probe")
        before = len(panel.calls)

        bus.publish(TOPIC_NOVEL_OPENED, {"novel_dir": "x"})

        assert len(panel.calls) > before  # 换书 → 重建当前面板

    def test_detach_all_unsubscribes_and_releases(self, host_env):
        from app.events import EventBus

        Recording, _Other = host_env
        bus = EventBus(name="t")
        host, _app = self._host(bus)
        host.select("host-recording-probe")
        panel = host.panel("host-recording-probe")

        host.detach_all()

        assert panel.app is None
        assert bus.has_subscribers(TOPIC_CHAPTER_SAVED) is False


# ============================================================ 分发层已去硬编码


class TestDispatchLayerHasNoHardcodedPanels:
    def test_toolkit_ui_has_no_build_dispatch_chain(self):
        code = _scan.code_only("app/toolkit_ui.py")
        # 只盯 `_build_<key>_tool` 这一族（`_build_cover_html` 等是正常的构建方法）
        assert re.search(r"_build_[a-z_]+_tool", code) is None, "toolkit_ui 里仍有 `_build_*_tool` 分发链"
        assert "tool_type ==" not in code, "toolkit_ui 里仍有按 key 的 if/elif 分发"

    def test_shell_ui_has_no_hardcoded_panel_list(self):
        code = _scan.code_only("app/shell_ui.py")
        for key in ("elements", "bridges", "memory_viz", "batch_ops"):
            assert key not in code, f"shell_ui 里仍硬编码了面板键 {key!r}"

    def test_no_module_keeps_a_second_panel_module_list(self):
        """面板模块清单只能出现在 registry（原生）与 legacy（迁移）里。

        一旦别处也维护一份，就回到 v2「同一信息多处登记、必漂移」的老路。
        """
        allowed = {
            "app/panels/registry.py",
            "app/panels/legacy.py",
            "app/panels/__init__.py",  # 只做转出，不新增清单
        }
        pattern = re.compile(r"['\"]app\.panels\.[a-z_]+_panel['\"]")
        offenders = []
        for path in REPO_ROOT.glob("app/**/*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in allowed:
                continue
            if pattern.search(_scan.code_only(rel)):
                offenders.append(rel)

        assert offenders == [], f"这些文件又维护了一份面板模块清单：{offenders}"

    def test_native_panel_list_is_referenced_only_by_registry_and_exports(self):
        allowed = {"app/panels/registry.py", "app/panels/__init__.py"}
        offenders = []
        for path in REPO_ROOT.glob("app/**/*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in allowed:
                continue
            if "NATIVE_PANEL_MODULES" in _scan.code_only(rel):
                offenders.append(rel)

        assert offenders == [], f"这些文件引用了原生面板清单（应只读注册表）：{offenders}"


# ============================================================ 样式令牌（真实 bug 的回归）


class TestPanelColorTokensExist:
    def test_every_c_token_exists_in_ui_style(self):
        """`C['xxx']` 用了不存在的键会让面板**建到一半崩掉**。

        `websearch_panel` 与 `story_flow_panel` 曾用 `C['input_bg']`（`UIStyle.COLORS`
        里从未定义过），在 v2 里异常被 Tk 回调吞掉，表现为"点了没反应、面板半截"。
        这里扫全部 `app/` 源码，把这类笔误挡在提交前。
        """
        # ⚠️ 覆盖面（2026-09-16 加固）：原判据只认字面 `C = UIStyle.COLORS`，
        # 于是任何**间接取色**的写法都会逃过检查（例如 `C = _colors()`、
        # 或直接写 `UIStyle.COLORS["x"]`）。现改为"文件里出现过 `UIStyle.COLORS` 即检查"，
        # 并同时扫 `C['x']` 与 `UIStyle.COLORS['x']` 两种写法。
        mentions_colors = re.compile(r"UIStyle\.COLORS")
        usage_c = re.compile(r"\bC\[['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\]")
        usage_direct = re.compile(r"UIStyle\.COLORS\[['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\]")
        colors = set(UIStyle.COLORS)

        checked_files = 0
        bad = []
        for path in REPO_ROOT.glob("app/**/*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            code = _scan.code_only(rel)
            if not mentions_colors.search(code):
                continue
            checked_files += 1
            for key in usage_c.findall(code):
                if key not in colors:
                    bad.append(f"{rel}: C[{key!r}]")
            for key in usage_direct.findall(code):
                if key not in colors:
                    bad.append(f"{rel}: UIStyle.COLORS[{key!r}]")

        # 下限跟着覆盖面一起提高（原为 10）：间接取色的文件现在也计入
        assert checked_files >= 20, f"只扫到 {checked_files} 个使用 COLORS 的文件，扫描可能已失效"
        assert bad == [], f"这些颜色键在 UIStyle.COLORS 里不存在：{bad}"


class TestLoadFailuresAreRecorded:
    """面板模块导入失败必须**留痕**（本轮踩到的真实坑）。

     `load_panels()` 对单个模块的失败只记 error 后跳过；打包成 windowed EXE 后
    没有控制台，那条日志永远看不到 —— 表现为"面板少了几块却毫无痕迹"。
    现在失败会记进 `registry.LOAD_FAILURES`，并由启动时的诊断记录写到磁盘日志。
    现在失败会记进 ，并由启动时的诊断记录写到磁盘日志。
    """

    def test_broken_module_is_recorded(self, monkeypatch):
        registry.reset_registry()
        monkeypatch.setattr(registry, "NATIVE_PANEL_MODULES", ("app.panels.definitely_missing",))
        try:
            specs = registry.load_panels()
            assert specs, "迁移面板仍应正常登记"
            assert registry.LOAD_FAILURES, "导入失败必须被记录"
            assert "definitely_missing" in registry.LOAD_FAILURES[0]
            # 坏模块不该混进注册表
            assert all(not spec.key == "definitely_missing" for spec in specs)
        finally:
            monkeypatch.undo()
            registry.reset_registry()
            registry.load_panels()

    def test_healthy_environment_has_no_failures(self, loaded):
        assert registry.LOAD_FAILURES == [], f"有面板模块导入失败：{registry.LOAD_FAILURES}"
