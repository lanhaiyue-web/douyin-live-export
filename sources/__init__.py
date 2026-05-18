"""数据源插件。

每个数据源实现 DataSource 接口，吐统一的 LiveSession / MinuteData / TranscriptSegment。
analyzer 和 app 层完全不知道数据来自哪里。
"""
from .base import DataSource, LiveSession, MinuteData, TranscriptSegment
from .anchor import AnchorSource
from .manual import ManualUploadSource

__all__ = [
    "DataSource",
    "LiveSession",
    "MinuteData",
    "TranscriptSegment",
    "AnchorSource",
    "ManualUploadSource",
]
