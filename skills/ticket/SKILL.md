# 工单管理技能

## 描述

使用 ticket_server MCP 工具管理用户工单。

当 FAQ 无法解决问题时，可以创建工单并转交人工处理。

---

## 可用工具

### create_ticket

创建新工单。

参数：

* title：工单标题
* description：问题描述
* priority：优先级（low / medium / high / urgent）
* user_id：用户 ID
* user_name：用户名称
* platform：来源平台

---

### get_ticket

查询工单状态。

参数：

* ticket_id：工单编号

---

### list_user_tickets

查询用户历史工单。

参数：

* user_id：用户 ID
* status：工单状态（可选）

---

### update_ticket

更新工单状态。

参数：

* ticket_id：工单编号
* status：新状态
* comment：备注

---

## 工作流程

### 第一步：优先尝试 FAQ

用户提问时：

1. 先查询 FAQ 知识库
2. 如果 FAQ 能回答，则直接回答
3. 不创建工单

---

### 第二步：FAQ 无法解决

如果出现以下情况：

* 知识库没有相关内容
* 用户问题需要人工介入
* 系统异常
* 数据错误
* 账户异常
* 支付异常

创建工单：

priority = medium

---

### 第三步：紧急问题

如果用户出现：

* 无法登录
* 数据丢失
* 支付失败
* 系统崩溃
* 投诉升级

创建：

priority = urgent

---

### 第四步：查询工单

当用户询问：

* 我的工单怎么样了
* 工单处理到哪了
* 查询工单状态

使用：

get_ticket

或

list_user_tickets

---

### 第五步：关闭工单

当用户明确表示：

* 已解决
* 问题处理完成
* 不需要继续跟进

使用：

update_ticket

将状态更新为：

resolved

---

## 回复规范

创建工单成功：

```text
已为您创建工单。

工单编号：TICKET_ID

优先级：PRIORITY

技术支持团队将尽快处理。
```

查询工单：

```text
工单编号：TICKET_ID

当前状态：STATUS

最新进展：

DETAILS
```

知识库无答案且工单创建失败：

```text
知识库中没有找到相关信息。

同时工单系统暂时不可用，请联系人工客服。
```
