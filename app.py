"""抖音直播复盘分析 Streamlit 看板。

启动：
    streamlit run app.py
"""
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from analyzer import align_and_color, summarize_with_llm, rows_to_records, PROVIDERS
from excel_export import export_rows_to_excel, get_desktop_path
from sources import AnchorSource, ManualUploadSource
from sources.base import LiveSession, TranscriptSegment

st.set_page_config(page_title="抖音直播复盘分析", layout="wide", page_icon="📊")

st.title("抖音直播复盘分析")
st.caption("按分钟对齐流量曲线与主播话术，红/绿/白染色，AI 出复盘建议")

# ---------- 侧边栏 ----------
with st.sidebar:
    st.header("数据源")
    source_choice = st.radio(
        "选择",
        ["抖音直播服务中心（自动抓）", "手动上传 Excel/CSV"],
        index=0,
    )
    st.markdown("---")
    threshold = st.slider(
        "染色阈值（净进出 / 全场均人数）",
        min_value=0.02, max_value=0.5, value=0.10, step=0.01,
        help="净进出占全场平均在线的比例超过该值，染绿/红",
    )
    st.markdown("---")
    st.subheader("AI 总结")
    provider_label = st.selectbox(
        "选模型",
        ["DeepSeek（推荐：便宜、国内直连）", "Anthropic Claude"],
        index=0,
    )
    provider = "deepseek" if provider_label.startswith("DeepSeek") else "anthropic"
    env_key = "DEEPSEEK_API_KEY" if provider == "deepseek" else "ANTHROPIC_API_KEY"
    api_key = os.environ.get(env_key, "")
    if not api_key:
        api_key = st.text_input(
            f"{'DeepSeek' if provider == 'deepseek' else 'Anthropic'} API Key",
            type="password",
            help=PROVIDERS[provider]["key_hint"],
        )

# ---------- Session state 缓存 ----------
if "source" not in st.session_state:
    st.session_state.source = None
if "sessions" not in st.session_state:
    st.session_state.sessions = []
if "rows" not in st.session_state:
    st.session_state.rows = []
if "current_traffic" not in st.session_state:
    st.session_state.current_traffic = []
if "current_session" not in st.session_state:
    st.session_state.current_session = None
if "current_transcript" not in st.session_state:
    st.session_state.current_transcript = []
if "summary_text" not in st.session_state:
    st.session_state.summary_text = ""


def render_colored_table(rows):
    df = pd.DataFrame(rows_to_records(rows))
    df = df.rename(columns={
        "minute": "分钟",
        "timestamp_str": "时间",
        "online": "在线",
        "net": "净进出",
        "enter": "进入",
        "leave": "离开",
        "text": "话术",
        "color": "_color",
    })

    def colorize(row):
        bg = {"green": "#c6efce", "white": "", "red": "#ffc7ce"}.get(row["_color"], "")
        return [f"background-color: {bg}" if bg else ""] * len(row)

    styled = df.style.apply(colorize, axis=1)
    if hasattr(styled, "hide"):
        styled = styled.hide(["_color"], axis=1)
    st.dataframe(styled, height=600, use_container_width=True)


# ========== 抖音直播服务中心 模式 ==========
if source_choice.startswith("抖音直播"):
    st.subheader("第一步：拉取近 30 天直播场次")
    st.caption("会弹出 Chrome 窗口（必须可见，headless 会被抖音风控）调用 anchor.douyin.com。首次约 20 秒。")

    if st.button("拉取场次列表", type="primary"):
        with st.spinner("启动浏览器、调用 anchor.douyin.com 中..."):
            try:
                src = AnchorSource(headless=False, timeout=60)
                sessions = src.list_sessions(days=30)
                st.session_state.source = src
                st.session_state.sessions = sessions
                if not sessions:
                    st.warning("没拉到场次。可能：登录态过期（重跑 `python login.py`）或近 30 天没开过播。")
            except Exception as e:
                st.error(f"抓取失败：{type(e).__name__}: {e}")

    if st.session_state.sessions:
        st.success(f"已拉取 {len(st.session_state.sessions)} 场")
        st.markdown("---")
        st.subheader("第二步：选场次")
        opts = {
            f"{s.start_time:%m-%d %H:%M} | {s.duration_min}分钟 | {s.title or '(无标题)'} | id={s.session_id}": s
            for s in st.session_state.sessions
        }
        chosen_label = st.selectbox("选一场分析", list(opts.keys()))
        chosen: LiveSession = opts[chosen_label]

        if st.button("拉取这场分钟级流量", type="primary"):
            with st.spinner("调用 minute_trend 接口中..."):
                try:
                    traffic = st.session_state.source.fetch_traffic(chosen)
                    if not traffic:
                        st.warning("这场没分钟级数据。常见：开播时长过短，抖音不生成复盘。换一场试。")
                    else:
                        rows = align_and_color(traffic, [], threshold_ratio=threshold)
                        st.session_state.rows = rows
                        st.session_state.current_traffic = traffic
                        st.session_state.current_session = chosen
                        st.session_state.current_transcript = []
                        st.session_state.summary_text = ""
                        st.success(f"已拉取 {len(traffic)} 分钟数据")
                except Exception as e:
                    st.error(f"抓取失败：{type(e).__name__}: {e}")

    if st.session_state.rows:
        st.markdown("---")
        st.subheader("第三步：拉取话术（可选）")
        st.caption("优先自动抓抖音「内容分析 → 文字记录」；如果该场没生成 ASR，再上传 CSV/Excel 兜底。")

        if st.button("自动拉取这场话术", type="primary"):
            with st.spinner("调用文字记录接口中..."):
                try:
                    src = st.session_state.source or AnchorSource(headless=False, timeout=60)
                    transcript = src.fetch_transcript(st.session_state.current_session)
                    st.session_state.current_transcript = transcript
                    rows = align_and_color(
                        st.session_state.current_traffic, transcript, threshold_ratio=threshold
                    )
                    st.session_state.rows = rows
                    st.session_state.summary_text = ""
                    if transcript:
                        st.success(f"已自动拉取并对齐 {len(transcript)} 条话术")
                    else:
                        st.warning("这场没有拉到话术。可能：未生成文字记录、账号权限不足，或接口返回空。可继续上传话术文件兜底。")
                except Exception as e:
                    st.error(f"话术抓取失败：{type(e).__name__}: {e}")

        ts_file = st.file_uploader("话术 CSV / Excel", type=["csv", "xlsx"], key="ts_upload")
        if ts_file:
            try:
                ts_df = pd.read_csv(ts_file) if ts_file.name.endswith(".csv") else pd.read_excel(ts_file)
                transcript = [
                    TranscriptSegment(
                        minute_index=int(r.get("minute", i)),
                        timestamp=datetime.now(),
                        text=str(r.get("text", "")),
                        source="manual",
                    )
                    for i, r in ts_df.iterrows()
                ]
                rows = align_and_color(
                    st.session_state.current_traffic, transcript, threshold_ratio=threshold
                )
                st.session_state.rows = rows
                st.session_state.current_transcript = transcript
                st.success(f"话术已对齐 {len(transcript)} 条")
            except Exception as e:
                st.error(f"解析失败：{e}")

# ========== 手动上传模式 ==========
else:
    st.subheader("上传 Excel / CSV")
    st.caption("两份文件：流量（必含 `minute`、`online`）+ 话术（必含 `minute`、`text`）。按 minute 对齐。")

    col1, col2 = st.columns(2)
    with col1:
        traffic_file = st.file_uploader("流量 CSV / Excel", type=["csv", "xlsx"], key="m_traffic")
    with col2:
        transcript_file = st.file_uploader("话术 CSV / Excel", type=["csv", "xlsx"], key="m_ts")

    if traffic_file:
        try:
            tdf = pd.read_csv(traffic_file) if traffic_file.name.endswith(".csv") else pd.read_excel(traffic_file)
            src = ManualUploadSource()
            sess = src.load_traffic_from_df("manual-1", traffic_file.name, tdf)

            if transcript_file:
                tsdf = pd.read_csv(transcript_file) if transcript_file.name.endswith(".csv") else pd.read_excel(transcript_file)
                src.load_transcript_from_df("manual-1", tsdf)

            traffic = src.fetch_traffic(sess)
            transcript = src.fetch_transcript(sess)
            rows = align_and_color(traffic, transcript, threshold_ratio=threshold)
            st.session_state.rows = rows
            st.session_state.current_traffic = traffic
            st.session_state.current_session = sess
            st.session_state.current_transcript = transcript
            st.session_state.summary_text = ""
            st.success(f"加载 {len(traffic)} 分钟流量、{len(transcript)} 条话术")
        except Exception as e:
            st.error(f"解析失败：{type(e).__name__}: {e}")

# ========== 染色表格 + Claude 总结 ==========
if st.session_state.rows:
    st.markdown("---")
    st.subheader("染色表格")
    st.caption("🟢 涨人段 　🔴 掉人段 　⚪ 平稳段　（左侧滑条调阈值）")
    render_colored_table(st.session_state.rows)

    st.markdown("---")
    st.subheader(f"AI 复盘总结（{provider_label.split('（')[0]}）")
    if not api_key:
        st.info(f"左侧填 API Key 后可调 {provider}")
    elif st.button("生成总结", type="primary"):
        with st.spinner(f"{provider} 分析中..."):
            try:
                summary = summarize_with_llm(
                    st.session_state.rows, api_key, provider=provider,
                )
                st.session_state.summary_text = summary
            except Exception as e:
                st.error(f"{provider} 调用失败：{type(e).__name__}: {e}")
    if st.session_state.summary_text:
        st.markdown(st.session_state.summary_text)

    st.markdown("---")
    st.subheader("导出到桌面")
    desktop = get_desktop_path()
    st.caption(f"将染色表格 + Claude 总结导出成 Excel 保存到：`{desktop}`")
    if st.button("📥 导出 Excel 到桌面", type="primary"):
        try:
            saved = export_rows_to_excel(
                st.session_state.rows,
                session=st.session_state.current_session,
                summary_text=st.session_state.summary_text,
            )
            st.success(f"已保存：`{saved}`")
        except Exception as e:
            st.error(f"导出失败：{type(e).__name__}: {e}")
