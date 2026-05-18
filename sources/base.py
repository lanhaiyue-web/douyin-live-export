"""统一数据契约 + DataSource 抽象基类。

所有数据源（anchor.douyin.com / 巨量百应 / 抖店罗盘 / 直播伴侣 / 手动上传）
最后都吐这套结构。analyzer.py 只认这个契约，不关心数据来自哪。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict


@dataclass
class LiveSession:
    """一场直播。"""
    source: str               # 数据源名（如 "anchor.douyin.com"）
    session_id: str           # 抖音 roomID
    title: str
    start_time: datetime
    end_time: datetime
    duration_min: int         # 时长（分钟）
    cover_url: str = ""
    peak_online: int = 0      # 峰值在线
    watch_ucnt: int = 0       # 累计观看 UV
    raw: dict = field(default_factory=dict)


@dataclass
class MinuteData:
    """单场直播的某一分钟。"""
    minute_index: int         # 0-based，这场的第几分钟
    timestamp: datetime       # 真实时间
    online: int               # 该分钟末在线人数（watchUcnt）
    enter: int = 0            # 该分钟新进入人数（推算：max(0, Δonline + leave)）
    leave: int = 0            # 该分钟离开人数（leaveUcnt）
    comments: int = 0
    likes: int = 0
    shares: int = 0
    gifts: int = 0
    follows: int = 0
    raw: dict = field(default_factory=dict)


@dataclass
class TranscriptSegment:
    """主播某一分钟说的话。"""
    minute_index: int         # 与 MinuteData.minute_index 对齐
    timestamp: datetime
    text: str
    source: str = "manual"    # "anchor" / "whisper" / "manual" / ...


class DataSource:
    """抽象基类。每个数据源继承并实现这三个方法。"""

    name: str = "abstract"

    def list_sessions(self, days: int = 30) -> List[LiveSession]:
        raise NotImplementedError

    def fetch_traffic(self, session: LiveSession) -> List[MinuteData]:
        raise NotImplementedError

    def fetch_transcript(self, session: LiveSession) -> List[TranscriptSegment]:
        """无原生话术的源返回空列表，由 UI 引导用户走 Whisper / 上传。"""
        return []
