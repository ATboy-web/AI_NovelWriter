"""凭据不落日志的守卫。

## 为什么值得单独守

`_safe_error` 已经做得对（字面量替换 + 正则清查询串），但它**依赖调用方把
secret 传进来**。这类约定的失效方式很隐蔽：新写一行日志时忘了传参数，
或者直接 `logger.error(f"{e}")` —— 而 httpx / 网盘 SDK 的异常文本里常带完整
URL（含 `access_token=...`），一次失败就把长期令牌打进日志文件。

这里从三个角度守：
1. `_safe_error` 本身的行为（含边界：空 secret、非字符串 secret）；
2. 全仓日志调用里**不得**出现裸 `api_key` 插值；
3. `AIClient` 构造的调试信息不含密钥。
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.cloud_storage import _safe_error

REPO = pathlib.Path(__file__).resolve().parent.parent


class TestSafeError:
    def test_masks_explicit_secret(self):
        # secret 必须**真的出现在错误文本里**才谈得上"被擦掉"：
        # 若原文没有它，输出里自然也不该凭空多出 ***
        text = _safe_error("上传失败", RuntimeError("boom SECRET_TOKEN_123"), "SECRET_TOKEN_123")
        assert "SECRET_TOKEN_123" not in text
        assert "***" in text

    def test_masks_url_query_token(self):
        """网盘 SDK 的异常常带完整 URL，token 在查询串里。"""
        err = RuntimeError("GET https://pan.baidu.com/rest/2.0/x?access_token=abcdef123&path=/a failed")
        text = _safe_error("下载失败", err)
        assert "abcdef123" not in text
        assert "access_token=***" in text

    @pytest.mark.parametrize("key", ["api_key", "apikey", "token", "password", "secret", "refresh_token"])
    def test_masks_common_key_names(self, key):
        text = _safe_error("失败", RuntimeError(f"https://x/y?{key}=SENSITIVE"))
        assert "SENSITIVE" not in text, f"{key} 没有被擦除：{text}"

    def test_ignores_empty_secret(self):
        """空 secret 不能把整个文本替换成 ***（会丢掉全部错误信息）。"""
        text = _safe_error("失败", RuntimeError("真实错误"), "", None)
        assert "真实错误" in text

    def test_keeps_actionable_message(self):
        """擦除后仍要能看出是什么失败。"""
        text = _safe_error("迅雷网盘上传失败", RuntimeError("timeout"))
        assert "迅雷网盘上传失败" in text
        assert "timeout" in text

    def test_case_insensitive(self):
        text = _safe_error("失败", RuntimeError("?ACCESS_TOKEN=ABC"))
        assert "ABC" not in text


class TestNoRawKeyInLogs:
    """源码守卫：日志语句里不得直接插值 api_key / Authorization。"""

    RISKY = re.compile(r"(logger\.\w+|self\._log|print)\([^)]*\b(api_key|authorization)\b", re.IGNORECASE)

    def test_no_direct_key_interpolation(self):
        offenders = []
        for f in sorted((REPO / "app").rglob("*.py")):
            source = f.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if self.RISKY.search(line) and "_safe_error" not in line:
                    offenders.append(f"{f.relative_to(REPO)}:{lineno}  {stripped[:100]}")
        assert not offenders, "以下位置可能把密钥写进日志：\n  " + "\n  ".join(offenders)


class TestAIClientLogsNoKey:
    def test_debug_snapshot_excludes_key(self):
        """`AIClient` 的日志/调试输出不得包含明文 key。"""

        # 只检查源码中的日志语句，不实例化（避免读真实配置）
        source = (REPO / "app" / "ai_client.py").read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            if "api_key" in line and ("_log(" in line or "logger." in line):
                assert "***" in line or "len(" in line or "mask" in line.lower(), (
                    f"ai_client.py:{lineno} 可能打印明文 key: {line.strip()[:100]}"
                )
