"""手动上传数据源（兜底，永远不被反爬影响）。

接受三种格式：
1. minute_trend JSON 原始响应（从 anchor.douyin.com 自己导出）
2. 自定义 minute 列表 JSON
3. Excel / CSV（含 minute、online 列）
"""
import json
from datetime import datetime
from io import BytesIO, StringIO
from typing import List, Optional

import pandas as pd

from .base import DataSource, LiveSession, MinuteData, TranscriptSegment


class ManualUploadSource(DataSource):
    name = "manual"

    def __init__(self):
        self._cached_sessions: List[LiveSession] = []
        self._cached_traffic: dict = {}  # session_id -> List[MinuteData]
        self._cached_transcripts: dict = {}  # session_id -> List[TranscriptSegment]

    def list_sessions(self, days: int = 30) -> List[LiveSession]:
        return self._cached_sessions

    def fetch_traffic(self, session: LiveSession) -> List[MinuteData]:
        return self._cached_traffic.get(session.session_id, [])

    def fetch_transcript(self, session: LiveSession) -> List[TranscriptSegment]:
        return self._cached_transcripts.get(session.session_id, [])

    # ---------- 给 Streamlit 用的灌数据方法 ----------

    def load_traffic_from_df(self, session_id: str, title: str, df: pd.DataFrame) -> LiveSession:
        """从 DataFrame 灌流量数据。df 需含 minute、online 列；其余字段可选。"""
        rows: List[MinuteData] = []
        prev = 0
        for i, row in df.iterrows():
            online = int(row.get("online", 0))
            leave = int(row.get("leave", 0)) if "leave" in df.columns else 0
            enter = int(row.get("enter", 0)) if "enter" in df.columns else max(0, (online - prev) + leave)
            ts = pd.to_datetime(row.get("timestamp", datetime.now())) if "timestamp" in df.columns else datetime.now()
            rows.append(MinuteData(
                minute_index=int(row.get("minute", i)),
                timestamp=ts,
                online=online,
                enter=enter,
                leave=leave,
                comments=int(row.get("comments", 0)) if "comments" in df.columns else 0,
                likes=int(row.get("likes", 0)) if "likes" in df.columns else 0,
                shares=int(row.get("shares", 0)) if "shares" in df.columns else 0,
                gifts=int(row.get("gifts", 0)) if "gifts" in df.columns else 0,
                follows=int(row.get("follows", 0)) if "follows" in df.columns else 0,
            ))
            prev = online

        # 推断 start/end/duration
        start = rows[0].timestamp if rows else datetime.now()
        end = rows[-1].timestamp if rows else datetime.now()
        peak = max((r.online for r in rows), default=0)
        sess = LiveSession(
            source=self.name,
            session_id=session_id,
            title=title,
            start_time=start,
            end_time=end,
            duration_min=len(rows),
            peak_online=peak,
        )
        self._cached_sessions.append(sess)
        self._cached_traffic[session_id] = rows
        return sess

    def load_transcript_from_df(self, session_id: str, df: pd.DataFrame) -> None:
        """从 DataFrame 灌话术。df 需含 minute、text 列。"""
        segs: List[TranscriptSegment] = []
        for i, row in df.iterrows():
            segs.append(TranscriptSegment(
                minute_index=int(row.get("minute", i)),
                timestamp=pd.to_datetime(row["timestamp"]) if "timestamp" in df.columns else datetime.now(),
                text=str(row.get("text", "")),
                source="manual",
            ))
        self._cached_transcripts[session_id] = segs
