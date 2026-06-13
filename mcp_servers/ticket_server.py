
"""
ticket_server.py - 工单管理 MCP Server
"""

import json
import sqlite3
import sys
import uuid
from datetime import datetime

# 强制 stdout 使用 UTF-8，否则 nanobot MCP client 会解码失败
sys.stdout.reconfigure(encoding="utf-8")


DB_PATH = "tickets.db"


def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            user_id TEXT NOT NULL,
            user_name TEXT DEFAULT '',
            platform TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            comments TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    conn.close()


class TicketMCPServer:
    def __init__(self):
        init_database()

    def handle_request(self, request: dict):
        method = request.get("method")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "ticket-server",
                        "version": "1.0.0"
                    }
                }
            }

        # 这个是通知，不能返回内容
        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tools()
                }
            }

        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            args = params.get("arguments", {})

            result = self.call_tool(tool_name, args)

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False)
                        }
                    ]
                }
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unknown method: {method}"
            }
        }

    def get_tools(self):
        return [
            {
                "name": "create_ticket",
                "description": "创建新的客服工单",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "工单标题"},
                        "description": {"type": "string", "description": "问题描述"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "urgent"],
                            "description": "优先级"
                        },
                        "user_id": {"type": "string", "description": "用户ID"},
                        "user_name": {"type": "string", "description": "用户名称"},
                        "platform": {"type": "string", "description": "来源平台"}
                    },
                    "required": ["title", "description", "user_id"]
                }
            },
            {
                "name": "get_ticket",
                "description": "查询工单详情",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string", "description": "工单ID"}
                    },
                    "required": ["ticket_id"]
                }
            },
            {
                "name": "list_user_tickets",
                "description": "查询用户所有工单",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "用户ID"},
                        "status": {
                            "type": "string",
                            "enum": ["open", "in_progress", "resolved", "closed"],
                            "description": "工单状态"
                        }
                    },
                    "required": ["user_id"]
                }
            },
            {
                "name": "update_ticket",
                "description": "更新工单状态或备注",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string", "description": "工单ID"},
                        "status": {
                            "type": "string",
                            "enum": ["open", "in_progress", "resolved", "closed"],
                            "description": "新状态"
                        },
                        "comment": {"type": "string", "description": "备注"}
                    },
                    "required": ["ticket_id"]
                }
            }
        ]

    def call_tool(self, name, args):
        if name == "create_ticket":
            return self.create_ticket(args)
        if name == "get_ticket":
            return self.get_ticket(args)
        if name == "list_user_tickets":
            return self.list_user_tickets(args)
        if name == "update_ticket":
            return self.update_ticket(args)

        return {
            "success": False,
            "message": f"未知工具：{name}"
        }

    def create_ticket(self, args):
        ticket_id = f"TK-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tickets
            (ticket_id, title, description, priority, status,
             user_id, user_name, platform, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                args["title"],
                args["description"],
                args.get("priority", "medium"),
                args["user_id"],
                args.get("user_name", ""),
                args.get("platform", ""),
                now,
                now
            )
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "ticket_id": ticket_id,
            "status": "open",
            "priority": args.get("priority", "medium"),
            "message": f"工单 {ticket_id} 创建成功"
        }

    def get_ticket(self, args):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?",
            (args["ticket_id"],)
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return {
                "success": False,
                "message": "工单不存在"
            }

        return {
            "success": True,
            "ticket": dict(row)
        }

    def list_user_tickets(self, args):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if args.get("status"):
            cursor.execute(
                """
                SELECT * FROM tickets
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC
                """,
                (args["user_id"], args["status"])
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tickets
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (args["user_id"],)
            )

        rows = cursor.fetchall()
        conn.close()

        return {
            "success": True,
            "count": len(rows),
            "tickets": [dict(row) for row in rows]
        }

    def update_ticket(self, args):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM tickets WHERE ticket_id = ?",
            (args["ticket_id"],)
        )

        row = cursor.fetchone()

        if not row:
            conn.close()
            return {
                "success": False,
                "message": "工单不存在"
            }

        now = datetime.now().isoformat()
        updates = []
        values = []

        if args.get("status"):
            updates.append("status = ?")
            values.append(args["status"])

        if args.get("comment"):
            comments = json.loads(row["comments"])
            comments.append({
                "text": args["comment"],
                "timestamp": now
            })
            updates.append("comments = ?")
            values.append(json.dumps(comments, ensure_ascii=False))

        updates.append("updated_at = ?")
        values.append(now)
        values.append(args["ticket_id"])

        cursor.execute(
            f"UPDATE tickets SET {', '.join(updates)} WHERE ticket_id = ?",
            values
        )

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": f"工单 {args['ticket_id']} 更新成功",
            "updated_at": now
        }

    def run(self):
        while True:
            line = sys.stdin.readline()

            if not line:
                break

            try:
                request = json.loads(line.strip())
                response = self.handle_request(request)

                if response is not None:
                    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

            except Exception as e:
                error = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }
                sys.stdout.write(json.dumps(error, ensure_ascii=False) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = TicketMCPServer()
    server.run()
