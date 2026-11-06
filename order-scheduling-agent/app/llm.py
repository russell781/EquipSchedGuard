"""大模型客户端：OpenAI 兼容协议的流式调用，可替换供应商；无 Key 时用 Mock 演示。"""
import json
from collections.abc import AsyncGenerator

import httpx

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MOCK, LLM_MODEL
from .errors import err_llm


def use_mock() -> bool:
    """判断是否使用 Mock 模式：auto 时看是否配置了 API Key。"""
    if LLM_MOCK == "auto":
        return not LLM_API_KEY
    return LLM_MOCK == "true"


async def _mock_stream(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Mock 流式回答：基于制度检索内容拼一段演示文本，分段输出模拟打字效果。"""
    # 系统消息中已注入制度片段，这里简单提取用于演示
    system_text = messages[0]["content"] if messages else ""
    question = messages[-1]["content"] if messages else ""
    answer = (
        "根据制度检索结果，为你说明如下（当前为本地演示模式，未连接真实大模型）：\n\n"
        f"你咨询的问题是：「{question}」。\n\n"
        "处理原则：\n"
        "1. 涉及插单、缺料、停机等变更时，须先发起变更单，经审批后方可调整当日计划；\n"
        "2. 变更须保留原计划版本，并注明受影响的订单；\n"
        "3. 现场只执行唯一生效版本，旧版计划自动作废。\n\n"
        "具体条款请见下方引用的制度来源。"
        if "制度" in system_text else
        f"已收到你的问题：「{question}」。当前为本地演示模式，请配置 LLM_API_KEY 后获取真实回答。"
    )
    # 按小片段逐步输出，模拟真实流式响应
    step = 12
    for i in range(0, len(answer), step):
        yield answer[i:i + step]


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """统一的流式问答入口：逐段 yield 回答文本。

    参数 messages 为 OpenAI 格式的消息列表（含 system / user / assistant）。
    任何供应商异常统一转换为大模型错误（50001）。
    """
    if use_mock():
        async for chunk in _mock_stream(messages):
            yield chunk
        return

    # 真实调用：OpenAI 兼容的 /chat/completions 流式接口
    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {"model": LLM_MODEL, "messages": messages, "stream": True}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    # 供应商返回错误（额度不足、模型不存在等）
                    raise err_llm()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue  # 忽略心跳或不完整帧
                    if delta:
                        yield delta
    except httpx.HTTPError:
        # 网络层异常（超时、连接失败等）
        raise err_llm()
