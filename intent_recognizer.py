"""
intent_recognizer.py — 分层意图识别

流程：关键词匹配 → 未命中则 LLM 分类 → 低置信度反问用户

意图只分 5 类，每类对应一个具体动作：
  general_faq → 读 knowledge_base/general.md
  billing_faq → 读 knowledge_base/billing.md
  ticket      → 用 MCP ticket_server 工具
  complaint   → 创建高优先级工单
  chitchat    → 直接回复，不查知识库
  unknown     → 反问用户，不硬猜
"""

import json, os, re, urllib.request

# ── 关键词 → 意图 映射（命中即返回，confidence=1.0）──
# 格式: (意图ID, [关键词列表])
# 按顺序匹配，先命中的优先

KEYWORD_RULES = [
    # ── billing_faq: 计费相关 → 读 billing.md ──
    ("billing_faq", [
        "收费", "套餐", "发票", "退款", "订阅", "账单", "支付",
        "价格", "多少钱", "升级", "免费版", "专业版", "企业版",
        "年付", "月付", "API.*量", "额度", "欠费", "续费",
        "降级", "试用", "折扣",
    ]),
    # ── ticket: 工单相关 → MCP ticket tools ──
    ("ticket", [
        "工单", "转人工", "人工处理", "人工", "找人工",
    ]),
    # ── complaint: 投诉/紧急 → 高优先级工单 ──
    ("complaint", [
        "投诉", "差评", "举报", "无法登录", "数据丢失",
        "系统崩溃", "支付失败", "宕机", "不能用", "紧急", "着急",
        "账号.*异常", "账户.*异常", "不满意", "骂", "垃圾",
    ]),
    # ── chitchat: 闲聊 → 直接回复，不消耗 AI token ──
    ("chitchat", [
        "你好", "hi\\b", "hello", "早上好", "下午好", "晚上好", "嗨\\b",
        "在吗", "在不在", "谢谢", "感谢", "thank", "多谢", "辛苦了",
        "你是谁", "你叫什么", "你能做什么", "你有什么功能", "天气",
        "讲个笑话", "聊天",
    ]),
]

# 反问文案
CLARIFICATION = {
    "billing_faq": "请问您具体想了解哪方面的收费信息？比如套餐升级、发票下载、退款政策等。",
    "ticket":      "请问您是想创建新工单、查询工单进度，还是关闭已有工单？",
    "complaint":   "非常抱歉给您带来不便，请您详细描述遇到的问题。",
    "general_faq": "请问您想咨询哪方面的问题？比如账号注册、项目管理、文件上传等。",
    "chitchat":    "",
    "unknown":     "抱歉，我不太确定您具体想问什么，能再详细描述一下吗？",
}

# LLM 分类 prompt
CLASSIFY_PROMPT = """分析用户消息，判断意图类别。只输出 JSON。

类别（每类对应不同处理路径）：
- billing_faq: 收费、套餐、发票、退款、API额度、订阅 → 查 billing 知识库
- ticket: 工单操作（创建/查询/关闭）、转人工 → 调用工单系统
- complaint: 投诉、紧急问题（无法登录/数据丢失/崩溃）→ 创建高优先级工单
- chitchat: 问候、感谢、闲聊、问天气 → 直接回复
- general_faq: 账号、密码、注册、项目、上传、技术支持等其他FAQ → 查 general 知识库
- unknown: 完全无法判断

规则：
- confidence 0.0~1.0，表示你的把握度
- 模糊消息 confidence 应 < 0.6
- 无法判断时 intent="unknown", confidence=0.0

用户消息：{message}

只输出: {{"intent":"<类别>","confidence":<0.0~1.0>}}"""


# ── 核心 ──

def match_keywords(text: str) -> str | None:
    """Layer 1: 关键词匹配，命中返回意图ID，否则 None"""
    for intent_id, keywords in KEYWORD_RULES:
        for kw in keywords:
            try:
                if re.search(kw, text):
                    return intent_id
            except re.error:
                if kw in text:
                    return intent_id
    return None


def classify_by_llm(text: str, threshold: float = 0.6) -> tuple[str, float]:
    """Layer 2: LLM 分类，返回 (意图, 置信度)"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return ("unknown", 0.0)

    try:
        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个精确的意图分类器。只输出 JSON。"},
                {"role": "user", "content": CLASSIFY_PROMPT.format(message=text)},
            ],
            "temperature": 0.0,
            "max_tokens": 200,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        raw = body["choices"][0]["message"]["content"].strip()
        # 清理 markdown 包裹
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
        confidence = float(parsed.get("confidence", 0.0))
        return (intent, confidence)

    except Exception as e:
        print(f"[intent] LLM 分类失败: {e}", flush=True)
        return ("unknown", 0.0)


def recognize(text: str, threshold: float = 0.6) -> dict:
    """
    主入口：分层意图识别

    返回: {
        "intent": str,       # 意图ID
        "confidence": float, # 0.0~1.0
        "source": str,       # "rule" / "llm" / "fallback"
        "ask": str,          # 反问文案（低置信度时非空）
    }
    """
    text = text.strip()
    if not text:
        return {"intent": "unknown", "confidence": 0.0, "source": "fallback", "ask": CLARIFICATION["unknown"]}

    # Layer 1: 关键词
    intent = match_keywords(text)
    if intent:
        return {"intent": intent, "confidence": 1.0, "source": "rule", "ask": ""}

    # Layer 2: LLM
    intent, confidence = classify_by_llm(text, threshold)

    # Layer 3: 置信度门控
    if confidence < threshold:
        ask = CLARIFICATION.get(intent, CLARIFICATION["unknown"])
        if not ask:
            ask = CLARIFICATION["unknown"]
        return {"intent": "unknown", "confidence": confidence, "source": "llm", "ask": ask}

    return {"intent": intent, "confidence": confidence, "source": "llm", "ask": ""}


# ── 自检 ──

if __name__ == "__main__":
    cases = [
        ("怎么注册账号？",              "general_faq"),  # 无关键词命中 → 走 LLM
        ("如何升级套餐",               "billing_faq"),
        ("能开发票吗",                 "billing_faq"),
        ("我要投诉你们客服",            "complaint"),
        ("系统崩溃了！",               "complaint"),
        ("帮我查一下工单进度",          "ticket"),
        ("我要转人工",                 "ticket"),
        ("你好",                       "chitchat"),
        ("谢谢你的帮助",               "chitchat"),
    ]
    print("=" * 60)
    print("[Keyword Rule Self-Test]")
    print("=" * 60)
    for text, expected in cases:
        result = match_keywords(text)
        if result == expected:
            ok = "PASS"
        elif result is None:
            ok = "NEED_LLM"
        else:
            ok = "FAIL"
        print(f"  [{ok:9s}] {text:20s} -> {result or '(need LLM)':20s} | expect {expected}")
