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
  "amount": "10,000",
  "game": "Fortune Dragon",
  "raw_amount": 10000
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `amount` | string | 格式化后的金额字符串，直接填入文案 |
| `game` | string | 游戏名称 |
| `raw_amount` | number | 纯数字金额，用于门槛比较 |

> **货币说明：** 此接口仅供 SC 赢局使用。技术团队负责在他们系统内过滤，GC 赢局不发送到此接口。我们不做货币字段判断，避免内部字段名不一致导致的问题。消息中货币固定显示为 `SC`。

### 响应

| 状态码 | 含义 |
|--------|------|
| `200 { ok: true }` | 播报已发送 |
| `200 { skipped: true, reason: "below_threshold" }` | 未达门槛，跳过 |
| `400` | 缺少必填字段 |
| `401` | API 密钥无效 |
| `502` | Discord API 调用失败 |

---

## 处理流程

```
收到请求
  → 验证 Authorization header（Bearer token）
  → raw_amount < BIGWIN_THRESHOLD → 返回 skipped: below_threshold
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
- 链接：`https://fortunepurple.com`

**颜色：** `#9B59B6`（紫色，与品牌一致）

---

## 环境变量

| 变量名 | 用途 | 备注 |
|--------|------|------|
| `BROADCAST_API_KEY` | 给技术团队的鉴权密钥 | 新增，随机生成 |
| `BIGWIN_THRESHOLD` | 播报最低门槛（纯数字） | 新增，可随时修改 |
| `BIGWIN_CHANNEL_ID` | #big-wins 频道 ID | 新增 |
| `DISCORD_BOT_TOKEN` | Bot Token | 已存在 |

> `BIGWIN_BUTTON_URL` 固定为 `https://fortunepurple.com`，写死在代码里（需要改时改代码部署）。  
> 如需随时改链接无需部署，可改为环境变量。

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
**要求：** 此接口仅供 SC 赢局调用，GC 赢局请勿发送。建议只发 raw_amount ≥ 500（或与我方商定的值）的赢局，低于此值我方会跳过不播报。  
