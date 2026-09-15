# 多项目 Discord Bot 通用核心设计

**日期：** 2026-09-15  
**状态：** 已确认，待编写实施计划

## 目标

将 FortunePurple 现有 Discord Bot 收缩为一套可复用的通用核心。此后使用同一个 GitHub 仓库、同一个 Railway 项目及一套共享代码，运行任意数量的独立 Discord Bot。每个项目保有独立的 Discord Bot Token、Bot 名称和头像、Guild、频道、Role、飞书多维表格与功能开关；新增项目只新增配置和密钥，不复制代码仓库。

FortunePurple 是第一个使用该核心的真实项目。先将它稳定迁移至通用核心，再接入后续项目，避免同时维护多套 Bot 代码。

## 范围

### 保留并通用化的能力

1. 管理员通过 Discord 指令手动发布 Embed。
2. 指定频道中的自助 Role 分配。
3. 指定频道每条新消息自动添加固定 Reaction。
4. `exclusive-updates` 频道的自动 Reaction，作为可独立开关的专用规则。
5. 每日社群数据记录到各项目独立的飞书多维表格。
6. 从飞书多维表格读取日常贴，并在北京时间每天 `00:01` 自动发布；仅在首次读取、图片下载或发送失败时于 `00:06`、`00:16` 重试。

每日社群数据字段和统计时间统一为：

- 日期
- 当前总人数
- 今日新增人数
- 今日离开人数
- 今日净增长
- 北京时间每天 `23:59` 写入

### 收缩后不再保留的能力

- Vercel Dashboard、其 Supabase 管理 API 与后台网页
- Big Win 广播、Big Win 历史和 Upstash Redis
- Jackpot 定时广播
- 通用活动系统、活动码池与提交记录
- 截图兑奖活动
- 财务关键词客服引导
- 新成员 Autorole

这些能力不会在切换当天直接删除。先停止注册、完成验收并稳定运行，再删除实现、依赖和不再使用的云端变量，以保留可验证的 Git 回滚点。

## 总体架构

```text
GitHub: 一个 fpbot 仓库
          |
Railway: 一个项目 / 一个 Bot 服务
          |
          +-- ProjectRuntime(fortunepurple)
          |     +-- Discord Bot Token A / Guild A
          |     +-- Feishu Base A
          |     +-- 已启用的通用 Cogs
          |
          +-- ProjectRuntime(project_b)
          |     +-- Discord Bot Token B / Guild B
          |     +-- Feishu Base B
          |     +-- 已启用的通用 Cogs
          |
          +-- ProjectRuntime(project_c)
                +-- Discord Bot Token C / Guild C
                +-- Feishu Base C
                +-- 已启用的通用 Cogs
```

`runner.py` 读取 `ENABLED_PROJECTS`，为每个项目建立一个独立的 `ProjectRuntime` 和 Discord 客户端，并使用 `asyncio` 并发运行。每个实例拥有独立的 Token、Guild、HTTP connector、Discord 组件处理器、定时任务、飞书客户端、状态文件和日志前缀。

一个项目的 Token、飞书或 Discord 连接失败时，只记录并重连该项目；其他 Bot 不受影响。运行器同时支持只启动一个项目，未来项目需要更强隔离时，可以在不改业务代码的情况下，将同一仓库部署为每项目一个 Railway 服务。

## 目录和模块边界

```text
app/
  runner.py                 # 读取项目列表并监督多个 Bot 实例
  core/
    config.py               # 项目 YAML 加载、密钥解析、严格校验
    runtime.py              # ProjectRuntime、Bot 生命周期、项目日志
    registry.py             # 按 feature flags 注册 Cogs
    feishu.py               # 飞书多维表格客户端与通用请求处理
    state.py                # 项目隔离的本地状态文件和原子写入
  cogs/
    manual_embed.py         # 管理员 Slash Command 立即发布 Embed
    role_selector.py        # Role 下拉框
    auto_reaction.py        # 可配置的频道 Reaction 规则
    daily_updates.py        # 飞书日常贴读取、发布与状态写回
    community_metrics.py    # 加入/离开计数与每日飞书写入
projects/
  example.yaml              # 不含密钥的新项目模板
  fortunepurple.yaml        # FortunePurple 配置
tests/
  ...
```

每个 Cog 接收 `ProjectRuntime`，绝不在模块导入时读取全局 `os.getenv()`。因此配置只在该项目实例内可见，多个 Bot 不会串频道、Role、飞书表格或状态。

Discord 组件的 `custom_id` 必须带项目 slug，例如 `roles:fortunepurple`。Slash Command 同步仅对当前项目的 Guild 执行，避免多 Bot 在启动时错误同步彼此的命令。

## 项目配置和密钥

每个项目保存一份可提交的非机密 YAML 配置：

```yaml
project:
  slug: fortunepurple
  brand_name: FortunePurple

discord:
  token_env: DISCORD_TOKEN_FORTUNEPURPLE
  guild_id: "1498581314495053834"
  admin_role_ids:
    - "<ADMIN_ROLE_ID>"

features:
  manual_embed: true
  role_selector: true
  auto_reaction: true
  exclusive_updates_reaction: true
  daily_updates: true
  community_metrics: true

channels:
  roles: "<ROLES_CHANNEL_ID>"
  exclusive_updates: "<EXCLUSIVE_UPDATES_CHANNEL_ID>"
  daily_updates: "<DAILY_UPDATES_CHANNEL_ID>"
  staff_alerts: "<STAFF_ALERTS_CHANNEL_ID>"

role_selector:
  title: Select Your Notifications
  options:
    - label: Exclusive Updates
      role_id: "<ROLE_ID>"
      description: Get product updates

auto_reactions:
  - channel_id: "<CHANNEL_ID>"
    mode: random
    random_count: 10
    emojis: ["👍", "🎉", "🔥", "💜", "✨", "🚀", "💎", "🏆", "🎁", "💫"]
    include_bot_messages: true

feishu:
  app_id_env: FEISHU_FP_APP_ID
  app_secret_env: FEISHU_FP_APP_SECRET
  updates_base_env: FEISHU_FP_UPDATES_BASE
  updates_table_env: FEISHU_FP_UPDATES_TABLE
  metrics_base_env: FEISHU_FP_METRICS_BASE
  metrics_table_env: FEISHU_FP_METRICS_TABLE
```

真实 Token、飞书 App Secret 和 Base Token 只保存在 Railway Variables。例如：

```text
ENABLED_PROJECTS=fortunepurple,project_b
DISCORD_TOKEN_FORTUNEPURPLE=...
FEISHU_FP_APP_ID=...
FEISHU_FP_APP_SECRET=...
FEISHU_FP_UPDATES_BASE=...
FEISHU_FP_UPDATES_TABLE=...
FEISHU_FP_METRICS_BASE=...
FEISHU_FP_METRICS_TABLE=...
```

Discord Bot 名称和头像由各自 Discord Developer Portal 的应用配置决定，代码不修改它们。`brand_name` 仅用于 Embed、提示文本和项目日志。

新增项目的标准操作是：创建独立 Discord Bot，复制 `projects/example.yaml`，填写 Discord/飞书资源 ID，在 Railway 添加该项目密钥，然后将 slug 加入 `ENABLED_PROJECTS`。

### FortunePurple 兼容迁移

FortunePurple 是从旧单项目 Bot 迁入共享核心的首个项目。为保留其已在线运行的配置，角色选择器允许以现有 Discord 角色名和 `🔔roles` 频道名解析资源；运行时必须精确匹配，找不到时记录明确错误且不创建替代对象。新项目必须使用频道和角色 ID。

FortunePurple 保留现有管理员身份组的 `/embed` 使用限制，但其空的频道白名单代表可发布到任意文字频道，与旧版行为一致。其 `exclusive-updates` 日常贴继续使用既有 20 个表情的池，并随机添加 10 个互不重复的 Reaction。

## 功能行为

### 手动 Embed

管理员通过 Slash Command 创建并立即发送 Embed。配置定义允许执行的管理 Role 和目标频道白名单。此功能不保存 Dashboard 草稿，不依赖 Supabase。

### Role 分配

Cog 在项目的 `roles` 频道维护一个持久下拉框。选项、目标 Role ID、标题与描述来自项目配置。成员选择已拥有的 Role 时取消该 Role，选择未拥有的 Role 时添加该 Role。

### 自动 Reaction

每条规则包含频道 ID、一个或多个 Emoji、启用状态和 `include_bot_messages`。`mode: fixed` 按配置顺序添加全部 Emoji；`mode: random` 从无重复 Emoji 池中随机选择 `random_count` 个。规则默认可对 Bot 自己发布的消息生效，因此发布到 `exclusive-updates` 的日常贴也能获得所需 Reaction。`exclusive-updates` 规则有自己的功能开关。

### 日常贴

每个项目读取自己飞书 Base 的日常贴表。每天北京时间 `00:01` 读取一次；仅当读取、图片下载、Discord 发送或飞书状态写回失败时，才在 `00:06`、`00:16` 重试。首次成功后当晚不再读取。

Bot 重启时，只有在 `00:00-00:30` 北京时间允许补查一次。白天重启不读取也不发布。只有日期早于当天且状态为待发布的内容可发布。Discord 已发送但飞书写回失败时立即重试写回三次，绝不当晚重复发送。

### 社群日报

每个项目独立监听成员加入/离开事件，并按项目保存事件状态。北京时间 `23:59` 计算当日总人数、新增、离开和净增长，写入该项目自己的飞书多维表格。失败不会静默清空本地状态，日志应明确指出项目、日期和失败原因。

## 配置校验、权限和可观测性

启动前必须校验：

- 项目 slug、Guild ID 和 Token 环境变量引用唯一。
- 每个启用功能所需的频道、Role、飞书配置齐全且格式正确。
- Emoji 配置、Role 选项和管理员 Role 列表有效。
- 配置错误只阻止对应项目实例启动，不影响其他已配置项目。

日志统一携带 `[项目][功能]` 前缀。启动完成后记录已加载 Cog、Guild、命令同步和飞书配置校验结果；绝不记录 Token、App Secret 或服务端密钥。

手动 Embed 仅允许配置的管理 Role 使用。Reaction 缺少权限、频道不存在、Emoji 无效或飞书调用失败时，只记录对应项目的明确错误，不使其他 Cog 或其他 Bot 停止。

## 迁移和下线步骤

1. 在不改变线上入口的前提下，加入 Core、通用 Cogs、FortunePurple 配置和测试。
2. 通过不登录 Discord 的配置预检，验证 FortunePurple 的 Token 引用、Guild、频道、Role、飞书字段和功能开关；同时通过单元测试对照现有日常贴与日报行为。
3. Railway 启动入口切至新运行器，但 `ENABLED_PROJECTS` 首次仅包含 `fortunepurple`。同一 Token 不会同时运行旧、新实例，因此只会产生一次正常的 Discord 重连窗口。
4. 验收 Role 下拉框、管理员 Embed、Reaction、飞书日常贴、日报写入与定时任务注册。
5. 稳定运行后，删除旧 Cog、`dashboard/`、Supabase/Upstash 依赖、Vercel 部署和不再使用的 Railway Variables；保留切换前的已验证 Git 提交作为回滚点。
6. 此后新增项目时，仅添加 YAML、Railway 密钥和 `ENABLED_PROJECTS` 条目。

## 测试策略

- 配置：多项目隔离、重复 slug/Guild/Token 引用、缺失密钥和功能依赖校验。
- 运行器：多 Bot 初始化、单项目错误隔离、每项目命令同步与重连监督。
- 手动 Embed：管理员 Role 授权、频道白名单和发送失败。
- Role：持久组件 ID 隔离、添加、取消、不存在 Role。
- Reaction：多个频道、多个 Emoji、Bot 消息包含开关、权限与非法 Emoji。
- 日常贴：三次读取上限、成功后跳过、重启窗口、日期过滤、并发锁和状态写回失败不重复发送。
- 日报：事件计数、北京时间 `23:59`、飞书字段映射、按项目状态文件隔离和写入失败保留状态。

部署前运行 Python 全量测试与 FortunePurple 配置预检。切换后检查 Railway 日志中 FortunePurple 的 Cog 清单、Guild 同步、飞书连接和定时任务注册；确认稳定后才允许启用第二个项目。
