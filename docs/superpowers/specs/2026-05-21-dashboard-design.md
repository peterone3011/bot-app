# Bot 网页后台设计文档

**日期：** 2026-05-21  
**状态：** 已审批，待实施

---

## 一、目标

为 Fortune Purple Discord Bot 构建一个内部网页后台，让管理员可以通过浏览器配置 Bot 的所有功能，替代部分斜杠命令操作。斜杠命令保留作为备用入口，两者共享同一数据库，互不冲突。

---

## 二、技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 + API | Next.js (App Router) | 部署到 Vercel 免费层 |
| 样式 | Tailwind CSS + shadcn/ui | 现代风格，参考 Vercel/Linear 视觉 |
| 数据库 | Supabase (PostgreSQL) | 免费层，500MB |
| 认证 | next-auth + Discord OAuth2 | 自动处理 state/CSRF |
| 限速 | Upstash + @upstash/ratelimit | 免费层，防接口滥用 |
| Bot 运行 | Railway（不变） | Bot 改为从 Supabase 读写数据 |

---

## 三、数据库设计

### 表一：messages（Embed 消息）

存储所有 Embed 消息，包括草稿、定时发送、已发出三种状态。字段与现有 messages.json 完全一致，直接迁移。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| status | text | draft / scheduled / published |
| label | text | 用户自定义标签（可选） |
| created_at | timestamptz | 创建时间 |
| channel_id | bigint | 目标频道 ID |
| send_at | timestamptz | 定时发送时间（可选） |
| message_id | bigint | Discord 消息 ID（发出后填入） |
| title | text | Embed 标题 |
| description | text | Embed 正文 |
| footer | text | 底部文字 |
| image_url | text | 图片链接 |
| button_label | text | 按钮文字 |
| button_url | text | 按钮链接 |
| color | integer | 颜色（十六进制整数） |

### 表二：sites（站点列表）

替代 roles.py 中硬编码的 SITES 列表，支持在网页上增删改序。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | text | 站点名称（对应 Discord 身份组名） |
| display_order | integer | 排列顺序 |
| created_at | timestamptz | 创建时间 |

### 表三：config（全局设置）

存储 Bot 零散的全局配置，键值对结构，方便未来扩展。

| 字段 | 类型 | 说明 |
|------|------|------|
| key | text | 配置键（主键） |
| value | text | 配置值 |

初始数据：`roles_channel_name = "🔔roles"`

---

## 四、网页页面结构

### 整体布局
左侧固定导航栏 + 右侧主内容区，深色/浅色主题，现代简洁风格。

### 页面列表

**登录页 `/login`**
- 单一"用 Discord 登录"按钮
- 无权限时显示"无权访问"提示

**Embed 消息页 `/dashboard/embeds`**
- Tab 切换：草稿 / 定时中 / 已发出
- 列表展示每条消息的标题、频道、状态、时间
- 点击进入编辑页，功能与现有斜杠命令完全一致
- 右上角"新建消息"按钮

**站点管理页 `/dashboard/sites`**
- 显示所有站点，支持增加、删除、改名、拖动排序
- 保存后 Bot 自动使用新列表

**全局设置页 `/dashboard/settings`**
- 角色频道名称等配置的输入框
- 保存按钮

---

## 五、认证与权限

**登录流程：**
1. 用户点击"用 Discord 登录"
2. 跳转 Discord OAuth2 授权页
3. Discord 回调，next-auth 自动验证 state 参数（防 CSRF）
4. 服务器检查用户在指定 Guild 中是否拥有指定管理员身份组
5. 有权限 → 创建 Session，进入后台；无权限 → 显示"无权访问"

**配置项（部署时需设置）：**
- 允许登录的 Discord Guild ID
- 允许登录的身份组名称（如"管理员"）

---

## 六、安全设计（共 10 项）

| # | 项目 | 实现方式 |
|---|------|---------|
| 1 | OAuth CSRF 防护 | next-auth 自动验证 state 参数 |
| 2 | Cookie 安全 | httpOnly Cookie，JavaScript 无法读取 |
| 3 | 每次请求验权 | 每个 API Route 都验证 Session + Discord 身份组 |
| 4 | 数据库密钥隔离 | Supabase 密钥仅存 Vercel 环境变量，不暴露给浏览器 |
| 5 | SQL 注入防护 | 使用 Supabase 官方查询构造器，不拼接原始 SQL |
| 6 | 输入校验 | 服务器端验证所有用户输入的格式和长度 |
| 7 | 数据库行级权限 | Supabase RLS 作为额外防护层 |
| 8 | 频率限制 | Upstash @upstash/ratelimit，每 IP 每分钟最多 30 次 API 请求 |
| 9 | Session 过期 | 7 天后自动失效，需重新登录 |
| 10 | 密钥不入仓库 | Bot Token、Supabase Key、Discord Secret 均不进 GitHub |

---

## 七、Bot 改造范围

**改动文件：**
- `cogs/embed.py`：`load_messages()` / `save_messages()` / `upsert_message()` / `delete_message()` 改为 Supabase 查询，其余逻辑不动
- `cogs/roles.py`：SITES 列表改为从 Supabase `sites` 表读取，ROLES_CHANNEL_NAME 改为从 `config` 表读取

**不改动：**
- 所有斜杠命令继续保留，作为备用入口
- Bot 在 Railway 的部署方式不变
- Railway Volume 在迁移完成确认后删除

**新增依赖：**
- `supabase` Python 客户端（添加至 requirements.txt）
- `dnd-kit` 前端拖拽库（站点排序使用）

---

## 八、部署架构

```
用户浏览器
    ↓ HTTPS
Vercel（Next.js）
    ↓ Supabase JS SDK（服务器端）
Supabase PostgreSQL
    ↑ Supabase Python SDK
Railway（Discord Bot）
    ↑ WebSocket Gateway
Discord
```

---

## 九、已知限制

- **Supabase 免费层保活：** 项目连续 7 天无活动会被暂停。内部后台日常使用不会触发此限制，但若长期不用需手动唤醒或设置定时保活请求。
- **时区：** 所有时间存储和显示均以 UTC+8（CST）为准，与现有 Bot 一致。

---

## 十、不在本次范围内

- 多 Guild 支持（仅单 Guild）
- 用户操作日志
- Embed 消息的富文本编辑器（使用简单输入框即可）
- 移动端适配（内部工具，桌面端优先）
