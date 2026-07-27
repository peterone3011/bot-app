# Activity Dashboard Chinese Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Dashboard 活动管理功能的内部界面和管理提示完整中文化，同时保持所有 Discord 玩家侧内容为英文。

**Architecture:** 直接替换活动管理 React 组件与领域校验中的固定管理文案，并用展示映射翻译数据库状态值，不改变数据库枚举和 API 数据结构。玩家侧字段值和默认模板继续保存、编辑和发送英文原文。

**Tech Stack:** Next.js 14、React、TypeScript、Vitest、Testing Library

## Global Constraints

- 不修改数据库结构、Bot 行为、RPC 或活动数据。
- Discord Embed、按钮、Modal、问题和 ephemeral 回复的默认值保持英文。
- 状态和提交结果只在展示层翻译，底层值保持 `draft | active | closed` 和 `winner | sold_out`。
- CSV 数据契约保持不变。
- 不引入国际化依赖。

---

### Task 1: 锁定中英文边界

**Files:**
- Modify: `dashboard/__tests__/activity-list.test.tsx`
- Modify: `dashboard/__tests__/activity-editor.test.tsx`
- Modify: `dashboard/__tests__/activities-domain.test.ts`
- Modify: `dashboard/__tests__/activity-code-pool.test.tsx`
- Modify: `dashboard/__tests__/activity-submissions.test.tsx`

**Interfaces:**
- Consumes: 现有活动组件 props 和 `validateCampaignInput`。
- Produces: 管理文案必须为中文、玩家默认文案必须保持英文的回归测试。

- [ ] **Step 1: 为活动列表和详情页写中文断言**

断言页面包含“活动管理”“创建草稿”“草稿”“福利码”“提交记录”，且不再渲染对应英文管理标签。

- [ ] **Step 2: 为配置页写中英文边界断言**

断言“活动名称”“中奖人数”“活动结束时间（北京时间）”“发布活动”等管理标签为中文，同时输入框中的 `Join Activity`、`Activity Entry` 和英文玩家回复原样保留。

- [ ] **Step 3: 为校验、码池和提交记录写中文断言**

断言重复福利码、缺少结束时间、加载失败、导入结果、筛选项和空状态均使用中文。

- [ ] **Step 4: 运行定向测试并确认失败**

Run: `npm.cmd test -- activity-list activity-editor activities-domain activity-code-pool activity-submissions`

Expected: 现有英文管理文案导致断言失败，玩家侧英文保留断言通过。

---

### Task 2: 中文化活动管理展示层

**Files:**
- Modify: `dashboard/components/sidebar.tsx`
- Modify: `dashboard/app/dashboard/activities/page.tsx`
- Modify: `dashboard/app/dashboard/activities/[id]/page.tsx`
- Modify: `dashboard/components/activity-list.tsx`
- Modify: `dashboard/components/activity-editor.tsx`
- Modify: `dashboard/components/activity-code-pool.tsx`
- Modify: `dashboard/components/activity-submissions.tsx`
- Modify: `dashboard/components/channel-select.tsx`

**Interfaces:**
- Consumes: `ActivityCampaign.status`、`ActivitySubmission.outcome` 原始枚举。
- Produces: `activityStatusLabels` 与 `submissionOutcomeLabels` 展示映射，或组件内等价的只读映射。

- [ ] **Step 1: 中文化导航、页面标题和列表**

将 Activity Management、Create Draft、No activities、codes、submissions 和状态标签替换为中文显示；保留活动名称原文。

- [ ] **Step 2: 中文化配置页管理控件**

替换页签、按钮、确认框、字段标签、问题配置选项和管理反馈；对 Embed、按钮、Modal、问题和私密回复字段增加“对玩家展示”的中文说明，但不修改字段值。

- [ ] **Step 3: 中文化福利码和提交记录**

替换导入、加载、搜索、筛选、表头、导出和空状态文案；提交结果使用中文映射，底层筛选值保持不变。

- [ ] **Step 4: 修复频道选择器乱码**

将加载、失败和占位符文本修复为有效中文，频道名称和分类名称保持 Discord 原文。

- [ ] **Step 5: 运行组件定向测试**

Run: `npm.cmd test -- activity-list activity-editor activity-code-pool activity-submissions`

Expected: 全部通过。

---

### Task 3: 中文化校验与完成验证

**Files:**
- Modify: `dashboard/lib/activities.ts`
- Modify: `dashboard/app/api/activities/route.ts`
- Modify: `dashboard/app/api/activities/[id]/route.ts`
- Modify: `dashboard/app/api/activities/[id]/publish/route.ts`
- Modify: `dashboard/app/api/activities/[id]/codes/route.ts`
- Modify: `dashboard/__tests__/activities-api.test.ts`

**Interfaces:**
- Consumes: 现有 API 状态码和错误分支。
- Produces: Dashboard 可直接展示的中文管理错误；成功响应结构不变。

- [ ] **Step 1: 中文化领域校验信息**

将活动名称、人数、结束时间、Discord 字段、问题和福利码校验错误改为中文，保留 `{code}` 等技术占位符原样。

- [ ] **Step 2: 中文化活动 API 管理错误**

替换仅返回给 Dashboard 管理员的创建、保存、发布、关闭、删除和码池错误文本；不修改 Discord Bot 回复。

- [ ] **Step 3: 运行 Dashboard 全量测试**

Run: `npm.cmd test`

Expected: 13 个测试文件全部通过。

- [ ] **Step 4: 运行生产构建**

Run: `Get-Content .env.verify | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim('"'), 'Process') } }; npm.cmd run build`

Expected: Next.js 编译、类型检查和静态页面生成全部成功。

- [ ] **Step 5: 检查差异并提交**

Run: `git diff --check`

Expected: 无空白错误。

Commit: `feat: localize activity dashboard in Chinese`
