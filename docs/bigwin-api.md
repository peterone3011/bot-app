# Big Win 播报接口 — 对接说明

## 接口信息

| 项目 | 内容 |
|------|------|
| 地址 | `https://fortunepurplebot.vercel.app/api/broadcast/bigwin` |
| 方法 | `POST` |
| API Key | 由 Fortune Purple 团队通过安全渠道单独提供 |

---

## 请求格式

**Headers（必须）：**
```
Authorization: Bearer <BROADCAST_API_KEY>
Content-Type: application/json
```

**Body：**
```json
{
  "amount": "15,888.0",
  "game": "Fortune Dragon"
}
```

> ⚠️ `amount` 和 `game` **每次都应传玩家实际的中奖金额和游戏名称**，不是固定值。  
> 上面只是示例，实际调用时替换成系统里的真实数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `amount` | 字符串或数字 | 本次实际中奖金额，如 `"15,888.0"` 或 `15888.0`，每次传真实值 |
| `game` | 字符串 | 本次触发大奖的游戏名称，如 `"Fortune Dragon"`，每次传真实值 |

---

## 响应说明

| HTTP 状态码 | 响应体 | 含义 |
|------------|--------|------|
| 200 | `{"ok": true}` | ✅ 播报已发出 |
| 200 | `{"skipped": true, "reason": "cooldown"}` | ✅ 正常，4小时内已播报过，自动跳过，无需重试 |
| 401 | `{"error": "Unauthorized"}` | ❌ API Key 不对，检查 Authorization header |
| 400 | `{"error": "..."}` | ❌ 参数格式有误，见错误信息 |
| 503 | `{"error": "Server misconfigured"}` | ❌ 我方服务器配置问题，联系我们 |

> **收到 `{"ok": true}` 或 `{"skipped": true}` 都表示对接成功。**  
> 只有 4xx / 5xx 才需要排查。

---

## 第一步：先测试连通性

在服务器上运行以下命令，确认能正常调通接口：

```bash
curl -X POST https://fortunepurplebot.vercel.app/api/broadcast/bigwin \
  -H "Authorization: Bearer <BROADCAST_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"amount": "15,888.0", "game": "Fortune Dragon"}'
```

**预期结果：** 返回 `{"ok":true}` 或 `{"skipped":true,"reason":"cooldown"}`，两种都说明接口通了。

---

## 第二步：在大奖触发时调用

> ⚠️ **仅限 SC 大奖触发，GC 中奖不调用此接口。**

玩家触发 **SC 大奖**时，在后端发一次 POST 请求，把**本次的实际金额和游戏名**传过来：

```json
{
  "amount": "这里填玩家实际中奖的 SC 金额",
  "game": "这里填触发大奖的游戏名称"
}
```

我方收到后会自动：
- 发消息到 Discord `#big-wins` 频道（带图片、带跳转按钮）
- 4小时内自动去重，不会重复播报

---

## 常见问题

**Q：`amount` 需要带货币符号或千位符吗？**  
A：不需要，传原始数字就行，如 `15888.0` 或 `"15,888.0"` 都可以。

**Q：返回 `{"skipped": true}` 是报错吗？**  
A：不是，是正常的冷却机制——4小时内触发多次只播报一次，防止刷屏。HTTP 200 就是成功。

**Q：需要处理重试逻辑吗？**  
A：不需要。接口幂等，遇到 `skipped` 不用重试；遇到网络超时可以重试 1 次，多次失败请联系我们。

**Q：请求超时时间建议设多少？**  
A：建议 10 秒，正常响应在 1-2 秒内。

---

## 异常处理

遇到问题，把以下信息提供到这边即可快速排查：
1. 完整的响应体（包括 HTTP 状态码）
2. 发送时间（精确到分钟）
