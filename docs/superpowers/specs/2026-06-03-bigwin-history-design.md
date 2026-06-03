# Big Win 播报历史记录 — 设计文档

**日期：** 2026-06-03
**背景：** 目前无法可靠追溯某条播报是由 bot 自动触发还是技术接口手动触发。需要持久化每条播报记录，并在 Dashboard 提供可筛选的查看页面。

---

## 1. 数据存储

### Redis Sorted Set

维护三个 Sorted Set，分别存全量、cron 专属、api 专属，查询时直接读对应 key，避免"先取再过滤"导致结果不足的问题：

| Key | 说明 |
|---|---|
| `bigwin:history` | 全量记录 |
| `bigwin:history:cron` | 仅 bot 自动触发 |
| `bigwin:history:api` | 仅技术接口手动触发 |

**Score：** `Date.now()` 毫秒时间戳，同一秒内多条记录顺序稳定。

**Member（JSON 字符串）：**
```json
{
  "id": "<discordMessageId>",
  "ts": 1748880000000,
  "amount": "932",
  "game": "MONEY COMING",
  "source": "api",
  "discordMessageId": "1234567890123456789"
}
```

`id` 直接使用 Discord 返回的 message ID，既保证唯一性，也方便日后在 Discord 里直接定位到那条消息。`ts` 与 Score 一致，均为毫秒。

`source` 取值：
- `cron`：Railway bot 每 6–14 小时自动触发（GET 请求）
- `api`：技术接口手动传入真实数据（POST 请求）

### 只记录成功发送的播报

以下情况**不写入**历史：
- 冷却期内被跳过（cooldown skipped）
- 鉴权失败（401）
- 参数校验失败（400）
- Discord API 报错或网络不通

只有 Discord 返回 2xx、消息确认发出后才写入。

### 历史写入失败的处理

写入历史是审计操作，不应影响播报结果。三个 Sorted Set 通过 Redis pipeline 批量执行，减少中间状态。任意一个写入失败均视为写入失败整体：
- 播报接口仍返回成功
- `console.error` 记录错误
- 响应体附带 `"recorded": false`，让调用方知道审计记录未写入

### 播报成功响应结构

成功时统一返回完整字段，方便外部接口和日志对账：
```json
{ "ok": true, "id": "1234567890123456789", "amount": "932", "game": "MONEY COMING", "source": "api", "recorded": true }
```
写入历史失败时 `recorded` 改为 `false`，其余字段不变。

### 30 天自动清理

每次写入时同步删除 30 天前的数据，三个 key 随 pipeline 一并清理，不需要定时任务。`ts_30days_ago` 为毫秒：
```
ZADD bigwin:history <ts_ms> <json>
ZREMRANGEBYSCORE bigwin:history 0 <ts_ms_30days_ago>
// bigwin:history:cron 或 bigwin:history:api 同理
```

---

## 2. 查询接口

**URL：** `GET /api/broadcast/bigwin/history`
**文件：** `dashboard/app/api/broadcast/bigwin/history/route.ts`

**鉴权：** 在 route handler 内部显式调用 `auth()` 检查 session，未登录返回 401。
> 注意：不要依赖 middleware 兜底——现有 middleware 不保护 `/api/broadcast/*`（因为播报接口走 Bearer token），只有历史接口需要 session 保护，故在 route 内单独处理。

**查询参数：**
- `source=cron`：直接读 `bigwin:history:cron`
- `source=api`：直接读 `bigwin:history:api`
- 不传：读 `bigwin:history`
- 其他值（如 `source=foo`）：返回 400 `{ "error": "Invalid source" }`，不静默当全量处理

**返回：** 最近 200 条，按时间倒序（最新在前）。

```json
{
  "records": [
    {
      "id": "1234567890123456789",
      "ts": 1748880000,
      "amount": "932",
      "game": "MONEY COMING",
      "source": "api",
      "discordMessageId": "1234567890123456789"
    }
  ]
}
```

Redis 中出现坏 JSON 时跳过该条记录，不崩溃，不影响其余数据返回。Redis 本身不可用时返回 500 `{ "error": "History unavailable" }`，前端显示"加载失败，请刷新"。

---

## 3. Dashboard 页面

**路由：** `/dashboard/bigwin`
**文件：** `dashboard/app/dashboard/bigwin/page.tsx`

**侧边栏：** 在 `dashboard/components/sidebar.tsx` 中新增「Big Win 记录」入口（Trophy 图标），插入现有三个导航项之后。

**页面结构：**
- 顶部：页面标题 + 右侧来源筛选下拉（全部 / 我们的Bot / 技术接口）
- 主体：表格
  - 列：时间 / 金额 / 游戏 / 来源
  - **时间列**：格式化为本地时间 `YYYY-MM-DD HH:mm:ss`，不展示 Unix 秒
  - 来源标签：`cron` 绿色，`api` 蓝色
- UI 状态：加载中（转圈）/ 空状态（暂无记录）/ 出错（加载失败，请刷新）

**交互：** 切换筛选项时重新请求接口，客户端 `useEffect` 驱动。

---

## 4. 改动范围

| 文件 | 操作 |
|---|---|
| `dashboard/app/api/broadcast/bigwin/route.ts` | 在 `broadcast()` Discord 成功后追加 Redis 写入（三个 key），写入失败不阻断响应 |
| `dashboard/app/api/broadcast/bigwin/history/route.ts` | 新建，历史查询接口 |
| `dashboard/app/dashboard/bigwin/page.tsx` | 新建，历史记录页面 |
| `dashboard/components/sidebar.tsx` | 新增导航项 |

---

## 5. 测试覆盖

| 场景 | 预期结果 |
|---|---|
| POST 播报成功 | 写入 `bigwin:history` 和 `bigwin:history:api` |
| GET（cron）播报成功 | 写入 `bigwin:history` 和 `bigwin:history:cron` |
| cooldown skipped | 不写入任何 history key |
| Discord 发送失败 | 不写入任何 history key |
| Redis 写入历史报错 | 播报接口仍返回成功，响应带 `recorded: false` |
| 历史接口未登录 | 返回 401 |
| `source=cron` 筛选 | 只返回 cron 记录 |
| `source=api` 筛选 | 只返回 api 记录 |
| Redis 中存在坏 JSON | 跳过该条，其余正常返回，不抛异常 |
| `source=foo` 非法参数 | 返回 400 `{ "error": "Invalid source" }` |
| Redis 查询不可用 | 返回 500 `{ "error": "History unavailable" }` |
| 播报成功且历史写入成功 | 响应含 `recorded: true` 及完整字段 |
| 播报成功但历史写入失败 | 响应含 `recorded: false`，其余字段不变 |
