# Big Win 播报历史记录 — 设计文档

**日期：** 2026-06-03
**背景：** 目前无法可靠追溯某条播报是由 bot 自动触发还是技术接口手动触发。需要持久化每条播报记录，并在 Dashboard 提供可筛选的查看页面。

---

## 1. 数据存储

### Redis Sorted Set

| 属性 | 值 |
|---|---|
| Key | `bigwin:history` |
| Type | Sorted Set |
| Score | Unix 时间戳（秒） |
| Member | JSON 字符串 |

Member 结构：
```json
{
  "ts": 1748880000,
  "amount": "932",
  "game": "MONEY COMING",
  "source": "api"
}
```

`source` 取值：
- `cron`：Railway bot 每 6–14 小时自动触发（GET 请求）
- `api`：技术接口手动传入真实数据（POST 请求）

### 写入时机

在现有 `broadcast()` 函数中，Discord 消息发送成功后写入。两条路径（GET/POST）共用同一函数，一处修改全覆盖。

### 30 天自动清理

每次写入时附带删除 30 天前的旧数据：
```
ZADD bigwin:history <ts> <json>
ZREMRANGEBYSCORE bigwin:history 0 <ts_30days_ago>
```

不需要定时任务，不需要单独的 TTL 管理。

---

## 2. 查询接口

**URL：** `GET /api/broadcast/bigwin/history`
**文件：** `app/api/broadcast/bigwin/history/route.ts`

**鉴权：** Dashboard 登录态（session），未登录返回 401。

**查询参数：**
- `source=cron`：只返回 bot 自动发的
- `source=api`：只返回技术接口发的
- 不传：返回全部

**返回：** 最近 200 条，按时间倒序（最新在前）。

```json
{
  "records": [
    { "ts": 1748880000, "amount": "932", "game": "MONEY COMING", "source": "api" },
    ...
  ]
}
```

---

## 3. Dashboard 页面

**路由：** `/dashboard/bigwin`

**侧边栏：** 新增「Big Win 记录」入口（Trophy 图标），插入现有三个导航项之后。

**页面结构：**
- 顶部：页面标题 + 右侧来源筛选下拉（全部 / 我们的Bot / 技术接口）
- 主体：表格
  - 列：时间 / 金额 / 游戏 / 来源
  - 来源标签：`cron` 绿色，`api` 蓝色
- UI 状态：加载中（转圈）/ 空状态（暂无记录）/ 出错（加载失败，请刷新）

**交互：** 切换筛选项时重新请求接口，客户端 `useEffect` 驱动。

---

## 4. 改动范围

| 文件 | 操作 |
|---|---|
| `app/api/broadcast/bigwin/route.ts` | 在 `broadcast()` 成功后追加 Redis 写入 |
| `app/api/broadcast/bigwin/history/route.ts` | 新建，查询接口 |
| `app/dashboard/bigwin/page.tsx` | 新建，历史记录页面 |
| `components/sidebar.tsx` | 新增导航项 |
