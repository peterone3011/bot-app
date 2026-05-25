# Big Win 播报接口设计

**日期：** 2026-05-25  
**状态：** 已确认，待实现  
**范围：** 仅 Big Win（Jackpot 暂不做）

---

## 背景

技术团队（外部）的后端系统在玩家赢得大奖时需要自动向 Discord #big-wins 频道发送播报消息。

Discord Webhook 不支持按钮组件，因此不能直接用 Webhook。解决方案是在 Dashboard（Vercel）上暴露一个 HTTP 接口，由 Dashboard 用 Bot Token 调用 Discord API 发送带按钮的消息。

---

## 接口规格

### Endpoint

```
POST https://fortunepurplebot.vercel.app/api/broadcast/bigwin
```

### 请求头

```
Authorization: Bearer <BROADCAST_API_KEY>
Content-Type: application/json
```

### 请求体

```json
{
  "event_id": "win_abc123",
  "amount": "10,000.0",
  "game": "Fortune Dragon",
  "raw_amount": 10000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `event_id` | string | 赢局唯一标识，用于防重（10 分钟内同一 ID 不重复播报） |
| `amount` | string | 格式化金额，**必须含一位小数**，如 `"10,000.0"`、`"500.0"` |
| `game` | string | 游戏名称 |
| `raw_amount` | number | 纯数字金额，用于门槛比较 |

> **货币说明：** 此接口仅供 SC 赢局使用。技术团队负责在他们系统内过滤，GC 赢局不发送到此接口。消息中货币固定显示为 `SC`。

### 响应

| 状态码 | 含义 |
|--------|------|
| `200 { ok: true }` | 播报已发送 |
| `200 { skipped: true, reason: "below_threshold" }` | 未达门槛，跳过 |
| `200 { skipped: true, reason: "duplicate" }` | 10 分钟内已播报过此 event_id，跳过 |
| `400` | 缺少必填字段或格式错误 |
| `401` | API 密钥无效 |
| `502` | Discord API 调用失败（技术团队可重试，建议间隔 5 秒） |

---

## 处理流程

```
收到请求
  → 验证 Authorization header
  → 缺少必填字段 → 返回 400
  → 检查 event_id 是否在 Redis 中存在（10 分钟 TTL）→ 存在则返回 skipped: duplicate
  → raw_amount < BIGWIN_THRESHOLD → 返回 skipped: below_threshold
  → 将 event_id 写入 Redis（TTL 10 分钟）
  → 用 Bot Token 调用 Discord API 发消息
  → 返回 ok: true
```

---

## Discord 消息格式

**Embed 内容：**

```
🏆 BIG WIN ALERT!!

A Fortune Chasers just won **{amount} SC** on **{game}**!
Think you're next? Jump in and spin! 🎰💜
```

**按钮：**
- 样式：Link Button（style 5）
- 文字：`Play Now`
- 链接：`https://fortunepurple.com`（写死在代码里）

**颜色：** `#9B59B6`（紫色，与品牌一致）

---

## 门槛说明

- `BIGWIN_THRESHOLD` 是**最终判断依据**，我方可随时调整
- 技术团队可在他们系统内做预筛选（如只发 raw_amount ≥ 某值的赢局），目的是减少无效请求流量，不是正式规则
- 两边门槛不需要一致，我方门槛以环境变量为准

---

## 环境变量

| 变量名 | 用途 | 备注 |
|--------|------|------|
| `BROADCAST_API_KEY` | 给技术团队的鉴权密钥 | 新增，随机生成 |
| `BIGWIN_THRESHOLD` | 播报最低门槛（纯数字） | 新增，可随时在 Vercel 后台修改 |
| `BIGWIN_CHANNEL_ID` | #big-wins 频道 ID | 新增 |
| `DISCORD_BOT_TOKEN` | Bot Token | 已存在 |
| `UPSTASH_REDIS_REST_URL` | Redis（幂等去重用） | 已存在（限流已在用） |
| `UPSTASH_REDIS_REST_TOKEN` | Redis Token | 已存在 |

> 按钮链接 `https://fortunepurple.com` 写死在代码里。如需随时改链接无需重新部署，可在实现时改为环境变量。

### 密钥轮换流程

如 `BROADCAST_API_KEY` 泄露需要更换：
1. 在 Vercel 后台更新 `BROADCAST_API_KEY` 的值（重新部署后生效）
2. 将新密钥告知技术团队，让他们更新他们系统里的配置
3. 旧密钥失效，之前的请求会返回 401

---

## 日志记录

服务端在以下情况写日志（输出到 Vercel Function Logs，可在 Vercel 后台查看）：

| 情况 | 日志级别 |
|------|---------|
| 播报成功发送 | info |
| 跳过（门槛/重复） | info |
| Discord API 失败 | error |
| 鉴权失败 | warn |

---

## 独立性说明

- 此接口与 Bot（Python/Railway）完全无关，Bot 代码无需改动
- 此接口与 Dashboard 其他功能（embed 编辑器、登录等）文件隔离，互不影响
- 环境变量单独命名，不与现有变量冲突

---

## 新增文件

- `dashboard/app/api/broadcast/bigwin/route.ts`

## 不涉及文件

- `bot.py`、`cogs/` 下所有文件
- Dashboard 现有页面和 API 路由

---

## 给技术团队的对接说明（待实现后发给他们）

**接口地址：** `https://fortunepurplebot.vercel.app/api/broadcast/bigwin`  
**方法：** POST  
**鉴权：** `Authorization: Bearer <密钥>`（密钥由我方提供）  
**要求：**
- 此接口仅供 SC 赢局调用，GC 赢局请勿发送
- `event_id` 必填，填赢局的唯一 ID，用于防止重复播报
- `amount` 格式：千分位 + 一位小数，如 `"10,000.0"`
- 建议预筛选，只发 raw_amount 超过一定值的赢局（与我方商定）
- Discord 调用失败时接口返回 502，可在 5 秒后重试一次
