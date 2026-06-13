"""
message_router.py - 飞书 Webhook 消息接收器
"""

import json
import os
import subprocess
import time
from datetime import datetime

from flask import Flask, request, jsonify

from intent_recognizer import recognize

handled_messages = set()
app = Flask(__name__)

# 闲聊直接回复（不消耗 AI token）
CHITCHAT_REPLIES = {
    "chitchat": "您好！请问有什么可以帮您的？",
}
# 意图 → 知识库路由提示
INTENT_ROUTE_HINT = {
    "general_faq": "请直接读取 knowledge_base/general.md 查找答案，跳过意图判断步骤。",
    "billing_faq": "请直接读取 knowledge_base/billing.md 查找答案，跳过意图判断步骤。",
    "ticket":      "请使用 MCP ticket_server 工具处理，跳过意图判断步骤。",
    "complaint":   "这是一个紧急/投诉问题，请创建高优先级工单（priority=urgent）。",
}


class NanobotBridge:
    """Nanobot 交互桥接器"""

    @staticmethod
    def send_to_nanobot(prompt: str, session_id: str) -> str:
        try:
            result = subprocess.run(
                [
                    "nanobot", "agent",
                    "-c", "/root/.nanobot/config.json",
                    "-s", session_id,
                    "-m", prompt
                ],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace"
            )

            print("====== Nanobot 调试信息 ======", flush=True)
            print("session_id:", session_id, flush=True)
            print("returncode:", result.returncode, flush=True)
            print("stdout:", result.stdout[:1000], flush=True)
            print("stderr:", result.stderr[:1000], flush=True)
            print("============================", flush=True)

            if result.stdout.strip():
                lines = result.stdout.splitlines()
                clean_lines = []

                for line in lines:
                    s = line.strip()
                    if not s:
                        continue
                    if s.startswith("Using config:"):
                        continue
                    if s.startswith("🐈"):
                        continue
                    clean_lines.append(line)

                return "\n".join(clean_lines).strip()

            if result.stderr.strip():
                return "Nanobot 没有返回正文，错误信息：" + result.stderr[:300]

            return "Nanobot 没有返回内容。"

        except subprocess.TimeoutExpired:
            return "抱歉，处理超时了，请稍后再试。"

        except Exception as e:
            print("调用 Nanobot 异常：", repr(e), flush=True)
            return f"系统暂时出了点问题：{e}"


@app.route("/webhook/feishu", methods=["POST"])
def feishu_webhook():
    t0 = time.perf_counter()

    data = request.json

    print("收到飞书事件：", json.dumps(data, ensure_ascii=False)[:1500], flush=True)

    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})

    event = data.get("event", {})
    message = event.get("message", {})

    message_id = message.get("message_id")
    print("message_id:", message_id, flush=True)

    if message_id in handled_messages:
        print("重复消息，跳过：", message_id, flush=True)
        return jsonify({"code": 0})

    handled_messages.add(message_id)

    try:
        content = json.loads(message.get("content", "{}"))
    except Exception as e:
        print("解析 content 失败：", repr(e), flush=True)
        return jsonify({"code": 0})

    text = content.get("text", "").strip()
    print("解析到文本：", text, flush=True)

    if text in ["此消息已删除", "消息已删除"]:
        print("删除消息提示，跳过。", flush=True)
        return jsonify({"code": 0})

    if not text:
        print("文本为空，跳过。", flush=True)
        return jsonify({"code": 0})

    sender = event.get("sender", {})
    user_id = sender.get("sender_id", {}).get("user_id", "unknown")

    session_id = f"feishu:{user_id}"
    print("session_id:", session_id, flush=True)

    # ── 分层意图识别 ──
    intent = recognize(text)
    t1 = time.perf_counter()
    t_intent = (t1 - t0) * 1000
    print(f"[TIMING] 意图识别: {t_intent:.0f}ms", flush=True)
    print(f"意图识别结果: intent={intent['intent']}, confidence={intent['confidence']}, source={intent['source']}", flush=True)

    t_nanobot = 0
    t_feishu = 0

    # 低置信度 → 反问用户，不走 nanobot
    if intent["intent"] == "unknown" and intent["ask"]:
        print("意图不明确，直接反问用户。", flush=True)
        feishu_reply(message_id, intent["ask"])
        t2 = time.perf_counter()
        t_feishu = (t2 - t1) * 1000
        print(f"[TIMING] 意图=unknown 反问: {t_feishu:.0f}ms | 总耗时: {(t2-t0)*1000:.0f}ms", flush=True)
        return jsonify({"code": 0})

    # 闲聊 → 直接回复，不走 nanobot
    if intent["intent"] == "chitchat":
        reply = CHITCHAT_REPLIES.get("chitchat", "您好！请问有什么可以帮您的？")
        print("闲聊消息，直接回复。", flush=True)
        feishu_reply(message_id, reply)
        t2 = time.perf_counter()
        t_feishu = (t2 - t1) * 1000
        print(f"[TIMING] 意图=chitchat 直接回复: {t_feishu:.0f}ms | 总耗时: {(t2-t0)*1000:.0f}ms", flush=True)
        return jsonify({"code": 0})

    # 其他意图 → 带路由提示发给 nanobot
    route_hint = INTENT_ROUTE_HINT.get(intent["intent"], "")
    prompt = (
        f"[来源: 飞书] [用户ID: {user_id}] "
        f"[意图: {intent['intent']}] [置信度: {intent['confidence']}]\n\n"
        f"用户提问: {text}\n\n"
        f"{route_hint}"
    ).strip()

    reply = NanobotBridge.send_to_nanobot(prompt, session_id)
    t2 = time.perf_counter()
    t_nanobot = (t2 - t1) * 1000
    print(f"[TIMING] nanobot agent: {t_nanobot:.0f}ms", flush=True)

    if not reply or not reply.strip():
        reply = "我收到你的消息了，但暂时没有生成回复。"

    print("准备回复飞书：", reply[:1000], flush=True)

    feishu_reply(message_id, reply)
    t3 = time.perf_counter()
    t_feishu = (t3 - t2) * 1000
    print(f"[TIMING] 飞书回复: {t_feishu:.0f}ms | 总计: 意图{t_intent:.0f}ms + nanobot{t_nanobot:.0f}ms + 飞书{t_feishu:.0f}ms = {(t3-t0)*1000:.0f}ms", flush=True)

    return jsonify({"code": 0})



def feishu_reply(message_id: str, text: str):
    import urllib.request

    if not message_id:
        print("没有 message_id，无法回复。", flush=True)
        return

    token = get_feishu_tenant_token()
    print("tenant_access_token 是否存在：", bool(token), flush=True)

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"

    payload = {
        "content": json.dumps({"text": text}, ensure_ascii=False),
        "msg_type": "text",
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = resp.read().decode("utf-8", errors="replace")
            print("飞书回复接口返回：", result, flush=True)
    except Exception as e:
        print("回复飞书失败：", repr(e), flush=True)


def get_feishu_tenant_token() -> str:
    import urllib.request

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    payload = {
        "app_id": os.getenv("FEISHU_APP_ID"),
        "app_secret": os.getenv("FEISHU_APP_SECRET"),
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        print("获取 token 返回：", result, flush=True)
        return result.get("tenant_access_token", "")


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "platforms": {
            "feishu": bool(os.getenv("FEISHU_APP_ID")),
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)