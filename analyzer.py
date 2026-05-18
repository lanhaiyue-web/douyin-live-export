"""核心分析逻辑：流量×话术按分钟对齐 + 染色 + LLM 总结。

输入用 sources.base 里的统一契约：MinuteData / TranscriptSegment。
LLM 支持 DeepSeek（OpenAI 兼容）和 Anthropic Claude，按需切换。
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Sequence

from sources.base import MinuteData, TranscriptSegment


@dataclass
class Row:
    minute: int
    timestamp_str: str
    online: int
    net: int               # 净进出（与上一分钟相比）
    enter: int
    leave: int
    text: str
    color: str             # "green" / "white" / "red"


def align_and_color(
    traffic: Sequence[MinuteData],
    transcript: Sequence[TranscriptSegment],
    threshold_ratio: float = 0.1,
) -> List[Row]:
    """按分钟对齐流量×话术，并按净进出染色。

    threshold_ratio: 净进出绝对值 / 全场平均在线人数 ≥ 该比例时染色。
    """
    if not traffic:
        return []

    text_by_min: Dict[int, str] = {t.minute_index: t.text for t in transcript}

    onlines = [m.online for m in traffic]
    avg = sum(onlines) / len(onlines) if onlines else 1
    threshold = max(1.0, avg * threshold_ratio)

    rows: List[Row] = []
    prev = onlines[0]
    for m in traffic:
        net = m.online - prev
        if net >= threshold:
            color = "green"
        elif net <= -threshold:
            color = "red"
        else:
            color = "white"
        rows.append(Row(
            minute=m.minute_index,
            timestamp_str=m.timestamp.strftime("%H:%M") if m.timestamp else "",
            online=m.online,
            net=net,
            enter=m.enter,
            leave=m.leave,
            text=text_by_min.get(m.minute_index, ""),
            color=color,
        ))
        prev = m.online
    return rows


PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "key_hint": "https://platform.deepseek.com/api_keys 拿到，sk- 开头",
    },
    "anthropic": {
        "base_url": None,
        "default_model": "claude-opus-4-7",
        "key_hint": "https://console.anthropic.com 拿到，sk-ant- 开头",
    },
}


def _build_prompt(rows: List[Row]) -> str:
    green = [r.text for r in rows if r.color == "green" and r.text.strip()]
    red = [r.text for r in rows if r.color == "red" and r.text.strip()]

    return f"""你是一位资深抖音直播复盘教练，专门帮主播找"哪句话进人、哪句话掉人"。

下面是一场直播按分钟切分的话术片段。

【涨人段话术】（这些时间段观众进得多）：
{chr(10).join(f"- {t}" for t in green) if green else "（无）"}

【掉人段话术】（这些时间段观众跑了）：
{chr(10).join(f"- {t}" for t in red) if red else "（无）"}

请给出：
1. 涨人话术的 3 条共性（具体到话术结构、节奏、用词）
2. 掉人话术的 3 条问题（具体什么动作/表达赶客）
3. 下一场直播 5 条可执行改进建议（按优先级排序）

中文，简洁直白，不要废话。"""


def _has_content(rows: List[Row]) -> bool:
    return any(r.color in ("green", "red") and r.text.strip() for r in rows)


def summarize_with_llm(
    rows: List[Row],
    api_key: str,
    provider: str = "deepseek",
    model: str = "",
) -> str:
    """用 LLM 读完所有绿/红话术，给出共性和改进建议。

    provider: "deepseek" 或 "anthropic"
    model: 不传则用 provider 默认模型
    """
    if not _has_content(rows):
        return (
            "暂无可分析的话术片段。可能原因：\n"
            "- 流量数据全场波动都在阈值内 → 调低左侧染色阈值再试\n"
            "- 还没上传话术 → 流量分析没问题，但需要话术才能给改进建议"
        )

    if provider not in PROVIDERS:
        raise ValueError(f"未知 provider：{provider}，支持：{list(PROVIDERS)}")

    cfg = PROVIDERS[provider]
    model = model or cfg["default_model"]
    prompt = _build_prompt(rows)

    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    # DeepSeek（OpenAI 兼容）
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    resp = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


# 向后兼容：保留旧名字
def summarize_with_claude(rows: List[Row], api_key: str) -> str:
    return summarize_with_llm(rows, api_key, provider="anthropic")


def rows_to_records(rows: List[Row]) -> List[Dict]:
    return [asdict(r) for r in rows]
