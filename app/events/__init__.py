"""事件总线包（v3 §2.3）。

`app/events/bus.py` 是唯一实现；本文件只做转出，让调用方写
`from app.events import EventBus, TOPIC_CHAPTER_SAVED` 而不必知道内部布局。
"""

from .bus import (
    ALL_TOPICS,
    TOPIC_AI_USAGE,
    TOPIC_BIOGRAPHY_GENERATED,
    TOPIC_CHAPTER_SAVED,
    TOPIC_CHARACTER_CHANGED,
    TOPIC_CONFIG_CHANGED,
    TOPIC_NOVEL_CLOSED,
    TOPIC_NOVEL_OPENED,
    TOPIC_OUTLINE_CHANGED,
    TOPIC_TIMELINE_CHANGED,
    WILDCARD,
    EventBus,
    EventSink,
    publish_threadaware,
)

__all__ = [
    "ALL_TOPICS",
    "WILDCARD",
    "TOPIC_AI_USAGE",
    "TOPIC_BIOGRAPHY_GENERATED",
    "TOPIC_CHAPTER_SAVED",
    "TOPIC_CHARACTER_CHANGED",
    "TOPIC_CONFIG_CHANGED",
    "TOPIC_NOVEL_CLOSED",
    "TOPIC_NOVEL_OPENED",
    "TOPIC_OUTLINE_CHANGED",
    "TOPIC_TIMELINE_CHANGED",
    "EventBus",
    "EventSink",
    "publish_threadaware",
]
