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
  "amount": "10,000.0",
  "game": "Fortune Dragon"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `amount` | string | 格式化金额，**必须含一位小数**，如 `"10,000.0"`、`"500.0"` |
| `game` | string | 游戏名称 |

> **货币说明：** 此接口仅供 SC 赢局使用。技术团队负责在他们系统内过滤（门槛设为 10,000），GC 赢局不发送到此接口。消息中货币固定显示为 `SC`。

### 响应

| 状态码 | 含义 |
|--------|------|
| `200 { ok: true }` | 播报已发送 |
| `200 { skipped: true, reason: "cooldown" }` | 4 小时内已播报过，跳过 |
| `400` | 缺少必填字段 |
| `401` | API 密钥无效 |
| `502` | Discord API 调用失败（可在 5 秒后重试） |

---

## 处理流程

```
收到请求
  → 验证 Authorization header → 失败返回 401
  → 缺少 amount 或 game → 返回 400
  → 检查 Redis 中是否存在冷却 key → 存在则返回 skipped: cooldown
  → 用 Bot Token 调用 Discord API 发消息 → 失败返回 502
  → 在 Redis 写入冷却 key（TTL 4 小时）
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
- 链接：`BIGWIN_BUTTON_URL` 环境变量

**颜色：** `#9B59B6`（紫色，与品牌一致）

---

## 环境变量

| 变量名 | 用途 | 备注 |
|--------|------|------|
| `BROADCAST_API_KEY` | 给技术团队的鉴权密钥 | 新增，随机生成 |
| `BIGWIN_CHANNEL_ID` | #big-wins 频道 ID | 新增 |
| `BIGWIN_BUTTON_URL` | 按钮跳转链接 | 新增，现为 `https://fortunepurple.com`，可随时在 Vercel 后台修改 |
| `DISCORD_BOT_TOKEN` | Bot Token | 已存在 |
| `UPSTASH_REDIS_REST_URL` | Redis（4 小时冷却用） | 已存在 |
| `UPSTASH_REDIS_REST_TOKEN` | Redis Token | 已存在 |

### 密钥轮换流程

如 `BROADCAST_API_KEY` 泄露需更换：
1. 在 Vercel 后台更新 `BROADCAST_API_KEY`，重新部署后生效
2. 将新密钥告知技术团队，让他们更新他们系统里的配置

---

## 日志记录

服务端输出到 Vercel Function Logs，可在 Vercel 后台查看：

| 情况 | 日志级别 |
|------|---------|
| 播报成功发送 | info |
| 冷却期内跳过 | info |
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
- 触发门槛设为 10,000 SC，低于此值无需发送
- `amount` 格式：千分位 + 一位小数，如 `"10,000.0"`
- 我方有 4 小时冷却限制，同一窗口内多次触发只会播报第一次
- Discord 调用失败时返回 502，可在 5 秒后重试一次
