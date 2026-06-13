# -*- coding: utf-8 -*-
"""bench.py — 线上系统评测"""
import json, time, urllib.request, threading

URL = "http://39.96.12.163:8080/webhook/feishu"

def make_payload(text, msg_id):
    return json.dumps({
        "type": "message",
        "event": {
            "message": {
                "message_id": msg_id,
                "content": json.dumps({"text": text}, ensure_ascii=False)
            },
            "sender": {"sender_id": {"user_id": "bench_user"}}
        }
    }, ensure_ascii=False).encode("utf-8")

def send(text, msg_id, timeout=120):
    payload = make_payload(text, msg_id)
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
    except Exception as e:
        code = 0
    return code, (time.perf_counter() - t0) * 1000

TEST_CASES = [
    ("你好",                     "chitchat"),
    ("谢谢",                     "chitchat"),
    ("怎么开发票",               "billing_faq"),
    ("我要退款",                 "billing_faq"),
    ("免费版有什么限制",          "billing_faq"),
    ("怎么注册账号",              "general_faq"),
    ("忘记密码了怎么办",          "general_faq"),
    ("如何邀请团队成员",          "general_faq"),
    ("文件上传失败怎么办",        "general_faq"),
    ("怎么删除项目",              "general_faq"),
    ("帮我查一下工单进度",        "ticket"),
    ("我要转人工",               "ticket"),
    ("系统崩溃了",               "complaint"),
    ("我要投诉你们客服",          "complaint"),
    ("帮帮我",                   "unknown"),
    ("这个功能不太会用",          "unknown"),
]

print("=" * 65)
print("  Benchmark — 15 test messages")
print("  " + URL)
print("=" * 65)
print()

# ── 预热 ──
print("Warmup...")
send("预热消息", "warmup_001")
time.sleep(2)

# ── 串行测试 ──
print()
print("%-4s %-22s %8s %8s   %s" % ("#", "Message", "Expect", "Time(ms)", "OK"))
print("-" * 65)

results = []
for i, (text, expected) in enumerate(TEST_CASES):
    code, ms = send(text, "seq_%03d" % i)
    ok = "OK" if code == 200 else "FAIL"
    results.append((text, expected, code, ms))
    print("%3d  %-22s %8s %8.0f   %s" % (i+1, text[:20], expected, ms, ok))
    time.sleep(0.5)

# ── 统计 ──
oks = [r for r in results if r[2] == 200]
fails = [r for r in results if r[2] != 200]
times = [r[3] for r in oks]

print()
print("=" * 65)
print("  Results")
print("=" * 65)
print("  Success rate:    %d/%d (%.1f%%)" % (len(oks), len(results), len(oks)/len(results)*100))
if times:
    print("  Response time:   min=%.0fms  max=%.0fms  avg=%.0fms  median=%.0fms" % (
        min(times), max(times), sum(times)/len(times), sorted(times)[len(times)//2]))

# ── 并发测试 ──
print()
print("  Concurrent test (3x '怎么开发票')...")
def worker(idx, out):
    out.append(send("怎么开发票", "conc_%02d" % idx))
conc_results = []
t0 = time.perf_counter()
threads = [threading.Thread(target=worker, args=(i, conc_results)) for i in range(3)]
for t in threads: t.start()
for t in threads: t.join()
total_time = (time.perf_counter() - t0) * 1000

conc_oks = [r for r in conc_results if r[0] == 200]
print("  Concurrent:       %d/%d ok, total %.0fms, %.2f req/s" % (
    len(conc_oks), 3, total_time,
    len(conc_oks) / (total_time/1000) if total_time > 0 else 0))

# ── 失败详情 ──
if fails:
    print()
    print("  Failed messages:")
    for text, expected, code, ms in fails:
        print("    %s (expected=%s, time=%.0fms)" % (text, expected, ms))
