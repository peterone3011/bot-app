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
  if (!isRecord(input)) return "Campaign body must be an object"
  if (!nonEmptyString(input.name, 120)) return "Name is required (maximum 120 characters)"
  if (
    typeof input.winner_limit !== "number" ||
    !Number.isInteger(input.winner_limit) ||
    input.winner_limit < 1 ||
    input.winner_limit > 10000
  ) {
    return "Winner limit must be an integer between 1 and 10000"
  }
  if (!nonEmptyString(input.button_label, 80)) {
    return "Button label is required (maximum 80 characters)"
  }
  if (!nonEmptyString(input.modal_title, 45)) {
    return "Modal title is required (maximum 45 characters)"
  }
  if (!optionalString(input.embed_title, 256)) {
    return "Embed title must be at most 256 characters"
  }
  if (!optionalString(input.embed_description, 4000)) {
    return "Embed description must be at most 4000 characters"
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
    return "Color must be an integer between 0 and 16777215"
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
    return "Image URL must start with http:// or https://"
  }
  for (const field of ["discord_guild_id", "discord_channel_id"]) {
    const value = input[field]
    if (
      value !== null &&
      value !== undefined &&
      value !== "" &&
      (typeof value !== "string" || !/^\d+$/.test(value))
    ) {
      return `${field} must be a numeric Discord snowflake`
    }
  }
  for (const field of ["winner_message", "sold_out_message", "closed_message"]) {
    if (!nonEmptyString(input[field], 4000)) {
      return `${field} is required (maximum 4000 characters)`
    }
  }
  if (!(input.winner_message as string).includes("{code}")) {
    return "Winner message must include {code}"
  }
  if (
    input.ends_at !== null &&
    input.ends_at !== undefined &&
    (
      typeof input.ends_at !== "string" ||
      !Number.isFinite(Date.parse(input.ends_at))
    )
  ) {
    return "Activity end time is invalid"
  }

  const questions = input.questions
  if (!Array.isArray(questions) || questions.length < 1 || questions.length > 5) {
    return "Campaign must contain 1-5 questions"
  }

  const fieldKeys = new Set<string>()
  const positions = new Set<number>()
  let prefillCount = 0
  let participantKeyCount = 0

  for (let index = 0; index < questions.length; index += 1) {
    const rawQuestion = questions[index]
    if (!isRecord(rawQuestion)) return `Question ${index + 1} must be an object`
    const fieldKey = rawQuestion.field_key
    if (
      typeof fieldKey !== "string" ||
      !/^[a-z][a-z0-9_]{0,63}$/.test(fieldKey)
    ) {
      return `Question ${index + 1} has an invalid field key`
    }
    if (fieldKeys.has(fieldKey)) return "Question field keys must be unique"
    fieldKeys.add(fieldKey)

    const position = rawQuestion.position
    if (
      typeof position !== "number" ||
      !Number.isInteger(position) ||
      position < 1 ||
      position > 5 ||
      positions.has(position)
    ) {
      return "Question positions must be unique integers from 1 to 5"
    }
    positions.add(position)

    if (!nonEmptyString(rawQuestion.label, 45)) {
      return `Question ${index + 1} label is required (maximum 45 characters)`
    }
    if (!["short", "paragraph"].includes(String(rawQuestion.input_style))) {
      return `Question ${index + 1} input style is invalid`
    }
    if (!optionalString(rawQuestion.placeholder, 100)) {
      return `Question ${index + 1} placeholder is too long`
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
      return `Question ${index + 1} length limits are invalid`
    }
    if (rawQuestion.prefill_discord_username === true) prefillCount += 1
    if (rawQuestion.is_participant_key === true) {
      participantKeyCount += 1
      if (rawQuestion.required !== true) {
        return "The unique participant question must be required"
      }
    }
  }

  if (prefillCount > 1) {
    return "Only one question may prefill the Discord username"
  }
  if (participantKeyCount > 1) {
    return "Only one unique participant question is allowed"
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

export function validatePublishedPatch(
  campaign: ActivityCampaign,
  patch: Record<string, unknown>
): string | null {
  if (campaign.status === "draft") return null
  for (let index = 0; index < LOCKED_AFTER_PUBLISH.length; index += 1) {
    const field = LOCKED_AFTER_PUBLISH[index]
    if (!(field in patch)) continue
    if (field === "codes") {
      return `${field} is locked after publish`
    }
    const current = campaign[field as keyof ActivityCampaign]
    if (JSON.stringify(current) !== JSON.stringify(patch[field])) {
      return `${field} is locked after publish`
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
    throw new ActivityValidationError("Reward codes must not contain duplicates")
  }
  if (codes.some((code) => code.length > 200)) {
    throw new ActivityValidationError("Reward codes must be at most 200 characters")
  }
  if (expectedCount !== undefined && codes.length !== expectedCount) {
    throw new ActivityValidationError(
      `Publish requires exactly ${expectedCount} reward codes`
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
