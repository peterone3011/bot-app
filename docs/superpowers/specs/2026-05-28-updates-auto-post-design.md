# Updates 频道自动发布系统 — 设计文档

## 概览

为 `📣updates`（exclusive-updates）频道实现全流程自动化：Claude Code 读图生成文案 → 写入 Lark → 人工审核 → Bot 定时发布 → 自动加表情。

---

## 工作流

```
用户填配图 → Claude Code 生成文案写入 Lark（待审核）
→ 用户审核确认（改为待发布）
→ Bot 周二/四/六 23:50 BJT 自动发布
→ 加 10 个随机正向表情
→ 回写 Lark：状态=已发布，备注=消息 ID
```

---

## Lark 表格结构

| 列 | 字段 | 说明 |
|----|------|------|
| A | 日期 | 由 Claude Code 自动填写，格式 `YYYY-M-D HH:MM` |
| B | 发布频道 | 固定写 `exclusive-updates` |
| C | 内容类型 | `游戏上新` 或 `引流reddit` |
| D | 发布文案 | AI 生成的纯文字内容 |
| E | 配图 | 用户预填图片；`无` 表示纯文字 |
| F | 状态 | `待审核` → `待发布`（用户手动）→ `已发布`（Bot 自动） |
| G | 备注 | Bot 发布后写入 Discord 消息 ID |

---

## 文案生成（Claude Code 执行）

触发方式：用户在 Claude Code 对话里说"生成下周文案"。

执行步骤：
1. 读取 Lark 表格，找到用户已预填配图但无文案的行
2. 计算下周二/四/六的日期
3. 对两张游戏配图：下载图片 → 调用视觉能力看图 → 生成游戏上新文案
4. 生成第三条引流 Reddit 文案（链接占位符空着）
5. 将三行写入 Lark，状态标"待审核"

文案规范：
- 风格参考已有帖子（见表格现有行）
- 严禁出现赌博、赢钱、jackpot 等高风险词汇
- URL 必须带 `https://` 前缀
- 游戏上新固定结尾：`👉 PLAY NOW: https://fortunepurple.com`
- 引流帖链接部分写 `👉 [REDDIT LINK]` 作为占位符

---

## Bot 自动发布（`cogs/updates.py`）

### 定时任务

每周二/四/六 UTC 15:50（北京时间 23:50）触发。

### 发布逻辑

1. 读 Lark 表格，找第一条满足条件的行：
   - 发布频道 = `exclusive-updates`
   - 状态 = `待发布`
   - 日期 ≤ 今天（北京时间）
2. 将 D 列富文本转为纯文字，处理 URL 类型节点
3. 判断 E 列：
   - 有图片（embed-image 类型）：用 Lark API 下载图片字节，作为 `discord.File` 附件
   - 值为"无"或空：纯文字消息
4. 发送到 `exclusive-updates` 频道（channel ID: `1501874966940094687`）
5. 依次加 10 个随机正向表情
6. 更新 Lark 该行：F 列改"已发布"，G 列写入 Discord 消息 ID

### 环境变量

| 变量 | 说明 |
|------|------|
| `UPDATE_CHANNEL_ID` | exclusive-updates 频道 ID（`1501874966940094687`） |
| `LARK_APP_ID` | Lark 应用 ID |
| `LARK_APP_SECRET` | Lark 应用密钥 |
| `LARK_SPREADSHEET_TOKEN` | 表格 token（`VdvlsAsnChhGMwtrwIfj7Ynypyb`） |
| `LARK_SHEET_ID` | Sheet ID（`cBez8N`） |

### 表情池（正向，不含负向）

```
🎉 🎊 🔥 💜 ✨ 🚀 💰 🎰 👑 🌟 💎 🙌 😍 🤩 💪 🎯 ⚡ 🏆 🎁 💫
```

每次从中随机不重复取 10 个。

---

## 斜杠命令 `/edit_update`

位置：`cogs/updates.py` 内，限 staff-chat 频道使用。

流程：
1. 用户在 staff-chat 输入 `/edit_update`
2. Bot 弹出 Modal，包含两个字段：
   - 消息 ID（必填）
   - 新文案（必填，多行文本）
3. 用户提交后，Bot 编辑对应 Discord 消息

---

## 富文本解析规则

Lark 表格 D 列有两种格式：
- **纯字符串**：直接使用
- **富文本数组**：遍历每个节点，`type=text` 取 `text` 字段，`type=url` 取 `link` 字段（确保有 `https://`）

---

## 不在范围内

- 自动生成 Reddit 帖子内容（链接由用户手动填写）
- 发布失败重试（Bot 下次触发时会重新检查）
- 图片尺寸/格式校验
