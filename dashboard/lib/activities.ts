import type {
  ActivityCampaign,
  ActivityQuestion,
  ActivitySubmission,
  ActivitySubmissionOutcome,
} from "@/lib/types"


export class ActivityValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "ActivityValidationError"
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown, maxLength: number): boolean {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    value.length <= maxLength
  )
}

function optionalString(value: unknown, maxLength: number): boolean {
  return value === null || value === undefined ||
    (typeof value === "string" && value.length <= maxLength)
}

export function validateCampaignInput(input: unknown): string | null {
  if (!isRecord(input)) return "活动数据格式无效"
  if (!nonEmptyString(input.name, 120)) return "请输入活动名称（最多 120 个字符）"
  if (
    typeof input.winner_limit !== "number" ||
    !Number.isInteger(input.winner_limit) ||
    input.winner_limit < 1 ||
    input.winner_limit > 10000
  ) {
    return "中奖人数必须是 1–10000 之间的整数"
  }
  if (!nonEmptyString(input.button_label, 80)) {
    return "请输入按钮文字（最多 80 个字符）"
  }
  if (!nonEmptyString(input.modal_title, 45)) {
    return "请输入弹窗标题（最多 45 个字符）"
  }
  if (!optionalString(input.embed_title, 256)) {
    return "消息标题最多 256 个字符"
  }
  if (!optionalString(input.embed_description, 4000)) {
    return "消息正文最多 4000 个字符"
  }
  if (
    input.color !== null &&
    input.color !== undefined &&
    (
      typeof input.color !== "number" ||
      !Number.isInteger(input.color) ||
      input.color < 0 ||
      input.color > 0xffffff
    )
  ) {
    return "消息颜色值无效"
  }
  if (
    input.image_url !== null &&
    input.image_url !== undefined &&
    input.image_url !== "" &&
    (
      typeof input.image_url !== "string" ||
      !/^https?:\/\/\S+$/i.test(input.image_url)
    )
  ) {
    return "图片 URL 必须以 http:// 或 https:// 开头"
  }
  for (const field of ["discord_guild_id", "discord_channel_id"]) {
    const value = input[field]
    if (
      value !== null &&
      value !== undefined &&
      value !== "" &&
      (typeof value !== "string" || !/^\d+$/.test(value))
    ) {
      return `${field === "discord_channel_id" ? "Discord 频道 ID" : "Discord 服务器 ID"}必须为数字`
    }
  }
  const replyLabels: Record<string, string> = {
    winner_message: "中奖回复",
    sold_out_message: "福利码发完回复",
    closed_message: "活动结束回复",
  }
  for (const field of ["winner_message", "sold_out_message", "closed_message"]) {
    if (!nonEmptyString(input[field], 4000)) {
      return `${replyLabels[field]}不能为空（最多 4000 个字符）`
    }
  }
  if (!(input.winner_message as string).includes("{code}")) {
    return "中奖回复必须包含 {code}"
  }
  if (
    input.ends_at !== null &&
    input.ends_at !== undefined &&
    (
      typeof input.ends_at !== "string" ||
      !Number.isFinite(Date.parse(input.ends_at))
    )
  ) {
    return "活动结束时间无效"
  }

  const questions = input.questions
  if (!Array.isArray(questions) || questions.length < 1 || questions.length > 5) {
    return "活动必须包含 1–5 个问题"
  }

  const fieldKeys = new Set<string>()
  const positions = new Set<number>()
  let prefillCount = 0
  let participantKeyCount = 0

  for (let index = 0; index < questions.length; index += 1) {
    const rawQuestion = questions[index]
    if (!isRecord(rawQuestion)) return `第 ${index + 1} 个问题格式无效`
    const fieldKey = rawQuestion.field_key
    if (
      typeof fieldKey !== "string" ||
      !/^[a-z][a-z0-9_]{0,63}$/.test(fieldKey)
    ) {
      return `第 ${index + 1} 个问题的字段标识无效`
    }
    if (fieldKeys.has(fieldKey)) return "每个问题的字段标识必须唯一"
    fieldKeys.add(fieldKey)

    const position = rawQuestion.position
    if (
      typeof position !== "number" ||
      !Number.isInteger(position) ||
      position < 1 ||
      position > 5 ||
      positions.has(position)
    ) {
      return "问题排序必须是 1–5 之间且不能重复的整数"
    }
    positions.add(position)

    if (!nonEmptyString(rawQuestion.label, 45)) {
      return `第 ${index + 1} 个问题的标题不能为空（最多 45 个字符）`
    }
    if (!["short", "paragraph"].includes(String(rawQuestion.input_style))) {
      return `第 ${index + 1} 个问题的输入框类型无效`
    }
    if (!optionalString(rawQuestion.placeholder, 100)) {
      return `第 ${index + 1} 个问题的占位提示过长`
    }
    const minLength = rawQuestion.min_length
    const maxLength = rawQuestion.max_length
    if (
      typeof minLength !== "number" ||
      !Number.isInteger(minLength) ||
      minLength < 0 ||
      minLength > 4000 ||
      typeof maxLength !== "number" ||
      !Number.isInteger(maxLength) ||
      maxLength < 1 ||
      maxLength > 4000 ||
      minLength > maxLength
    ) {
      return `第 ${index + 1} 个问题的长度限制无效`
    }
    if (rawQuestion.prefill_discord_username === true) prefillCount += 1
    if (rawQuestion.is_participant_key === true) {
      participantKeyCount += 1
      if (rawQuestion.required !== true) {
        return "唯一参与者 ID 问题必须设为必填"
      }
    }
  }

  if (prefillCount > 1) {
    return "只能有一个问题自动填入 Discord 用户名"
  }
  if (participantKeyCount > 1) {
    return "只能设置一个唯一参与者 ID 问题"
  }
  return null
}

const LOCKED_AFTER_PUBLISH = [
  "discord_guild_id",
  "discord_channel_id",
  "winner_limit",
  "ends_at",
  "modal_title",
  "questions",
  "codes",
] as const

const lockedFieldLabels: Record<(typeof LOCKED_AFTER_PUBLISH)[number], string> = {
  discord_guild_id: "Discord 服务器",
  discord_channel_id: "Discord 频道",
  winner_limit: "中奖人数",
  ends_at: "活动结束时间",
  modal_title: "弹窗标题",
  questions: "玩家填写问题",
  codes: "福利码",
}

export function validatePublishedPatch(
  campaign: ActivityCampaign,
  patch: Record<string, unknown>
): string | null {
  if (campaign.status === "draft") return null
  for (let index = 0; index < LOCKED_AFTER_PUBLISH.length; index += 1) {
    const field = LOCKED_AFTER_PUBLISH[index]
    if (!(field in patch)) continue
    if (field === "codes") {
      return `${lockedFieldLabels[field]}发布后不可修改`
    }
    const current = campaign[field as keyof ActivityCampaign]
    if (JSON.stringify(current) !== JSON.stringify(patch[field])) {
      return `${lockedFieldLabels[field]}发布后不可修改`
    }
  }
  return null
}

export function parseRewardCodes(raw: string, expectedCount?: number): string[] {
  const codes = raw
    .split(/\r?\n/)
    .map((code) => code.trim())
    .filter(Boolean)
  if (new Set(codes).size !== codes.length) {
    throw new ActivityValidationError("福利码不能重复")
  }
  if (codes.some((code) => code.length > 200)) {
    throw new ActivityValidationError("每个福利码最多 200 个字符")
  }
  if (expectedCount !== undefined && codes.length !== expectedCount) {
    throw new ActivityValidationError(
      `发布前必须正好导入 ${expectedCount} 个福利码`
    )
  }
  return codes
}

type DiscordButton = {
  type: 2
  style: 1
  label: string
  custom_id: "activity_join"
  disabled: boolean
}

export type ActivityDiscordBody = {
  embeds: Array<Record<string, unknown>>
  components: Array<{ type: 1; components: DiscordButton[] }>
}

export function buildActivityDiscordBody(
  campaign: Pick<
    ActivityCampaign,
    | "embed_title"
    | "embed_description"
    | "image_url"
    | "color"
    | "button_label"
  >,
  disabled = false
): ActivityDiscordBody {
  const embed: Record<string, unknown> = {}
  if (campaign.embed_title) embed.title = campaign.embed_title
  if (campaign.embed_description) embed.description = campaign.embed_description
  if (campaign.image_url) embed.image = { url: campaign.image_url }
  if (campaign.color !== null && campaign.color !== undefined) {
    embed.color = campaign.color
  }
  return {
    embeds: [embed],
    components: [
      {
        type: 1,
        components: [
          {
            type: 2,
            style: 1,
            label: campaign.button_label,
            custom_id: "activity_join",
            disabled,
          },
        ],
      },
    ],
  }
}

export function filterActivitySubmissions(
  submissions: ActivitySubmission[],
  search: string,
  outcome: ActivitySubmissionOutcome | "all"
): ActivitySubmission[] {
  const term = search.trim().toLocaleLowerCase()
  return submissions.filter((submission) => {
    if (outcome !== "all" && submission.outcome !== outcome) return false
    if (!term) return true
    const values = [
      submission.discord_user_id,
      submission.discord_username,
      submission.participant_key_normalized ?? "",
      ...Object.values(submission.answers),
    ]
    return values.some((value) => value.toLocaleLowerCase().includes(term))
  })
}

function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? "" : String(value)
  if (/^[=+\-@]/.test(text.trimStart())) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export function toActivityCsv(
  submissions: ActivitySubmission[],
  questions: ActivityQuestion[]
): string {
  const orderedQuestions = [...questions].sort((a, b) => a.position - b.position)
  const headers = [
    "Submitted At",
    "Discord User ID",
    "Discord Username",
    "Outcome",
    "Reward Code",
    ...orderedQuestions.map((question) => question.label),
  ]
  const rows = submissions.map((submission) => [
    submission.submitted_at,
    submission.discord_user_id,
    submission.discord_username,
    submission.outcome,
    submission.reward_code ?? "",
    ...orderedQuestions.map(
      (question) => submission.answers[question.field_key] ?? ""
    ),
  ])
  return `\uFEFF${[headers, ...rows]
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n")}`
}
