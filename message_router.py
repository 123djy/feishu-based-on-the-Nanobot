"""
message_router.py - 多平台消息路由器
将不同平台的消息统一转发给 Nanobot 处理
"""

import hashlib
import hmac
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime

from flask import Flask, request, jsonify

app = Flask(__name__)

class NanobotBridge:
    """Nanobot 交互桥接器"""

    @staticmethod
    def send_to_nanobot(prompt: str) -> str:
        """将消息发送给 Nanobot 并获取回复"""
        try:
            result = subprocess.run(
                ["nanobot", "chat", "--config", "config.json", prompt],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return "抱歉，处理超时了，请稍后再试。"
        except Exception as e:
            return f"系统暂时出了点问题，请稍后再试。(错误码: {hash(str(e)) % 10000})"

@app.route("/webhook/feishu", methods=["POST"])
def feishu_webhook():
    """飞书消息接收端点"""
    data = request.json

    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})

    event = data.get("event", {})
    message = event.get("message", {})
    content = json.loads(message.get("content", "{}"))
    text = content.get("text", "").strip()

    if not text:
        return jsonify({"code": 0})

    sender = event.get("sender", {})
    user_id = sender.get("sender_id", {}).get("user_id", "unknown")

    prompt = (
        f"[来源: 飞书] [用户ID: {user_id}]\n\n"
        f"用户提问: {text}"
    )

    reply = NanobotBridge.send_to_nanobot(prompt)

    feishu_reply(message.get("message_id"), reply)

    return jsonify({"code": 0})

def feishu_reply(message_id: str, text: str):
    """回复飞书消息"""
    import urllib.request

    token = get_feishu_tenant_token()
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    payload = {
        "content": json.dumps({"text": text}),
        "msg_type": "text",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    urllib.request.urlopen(req, timeout=10)


def get_feishu_tenant_token() -> str:
    """获取飞书 tenant_access_token"""
    import urllib.request

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": os.getenv("FEISHU_APP_ID"),
        "app_secret": os.getenv("FEISHU_APP_SECRET"),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        return result.get("tenant_access_token", "")

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "platforms": {
            "feishu": bool(os.getenv("FEISHU_APP_ID")),
            "dingtalk": bool(os.getenv("DINGTALK_APP_KEY")),
            "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)