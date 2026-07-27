import { describe, expect, it } from "vitest"

import {
  ActivityValidationError,
  buildActivityDiscordBody,
  filterActivitySubmissions,
  parseRewardCodes,
  toActivityCsv,
  validateCampaignInput,
  validatePublishedPatch,
} from "@/lib/activities"
import type {
  ActivityCampaign,
  ActivityQuestion,
  ActivitySubmission,
} from "@/lib/types"


const questions: ActivityQuestion[] = [
  {
    id: "q1",
    campaign_id: "c1",
    field_key: "discord_username",
    position: 1,
    label: "Discord Username",
    input_style: "short",
    required: true,
    placeholder: "Your username",
    min_length: 1,
    max_length: 100,
    prefill_discord_username: true,
    is_participant_key: false,
  },
  {
    id: "q2",
    campaign_id: "c1",
    field_key: "fp_id",
    position: 2,
    label: "FortunePurple ID",
    input_style: "short",
    required: true,
    placeholder: "Your ID",
    min_length: 1,
    max_length: 100,
    prefill_discord_username: false,
    is_participant_key: true,
  },
  {
    id: "q3",
    campaign_id: "c1",
    field_key: "favorite_game",
    position: 3,
    label: "Favorite FP Game",
    input_style: "paragraph",
    required: true,
    placeholder: "Your favorite game",
    min_length: 1,
    max_length: 400,
    prefill_discord_username: false,
    is_participant_key: false,
  },
]

const campaign: ActivityCampaign = {
  id: "c1",
  name: "Test Campaign",
  status: "draft",
  winner_limit: 20,
  discord_guild_id: "1498581314495053834",
  discord_channel_id: "1519235126201024633",
  discord_message_id: null,
  embed_title: "Tell us your favorite game",
  embed_description: "Click below to participate.",
  image_url: null,
  color: 0xff9933,
  button_label: "Join Activity",
  modal_title: "FP Player Survey",
  winner_message: "Congratulations! **{code}**",
  sold_out_message: "All codes are gone.",
  closed_message: "This activity has ended.",
  ends_at: "2099-08-01T12:00:00.000Z",
  created_at: "2026-07-27T00:00:00Z",
  updated_at: "2026-07-27T00:00:00Z",
  published_at: null,
  closed_at: null,
  questions,
  code_count: 20,
  submission_count: 0,
  winner_count: 0,
}


describe("validateCampaignInput", () => {
  it("accepts one to five valid questions", () => {
    for (const count of [1, 5]) {
      const input = {
        ...campaign,
        questions: Array.from({ length: count }, (_, index) => ({
          ...questions[0],
          id: `q${index}`,
          field_key: `field_${index}`,
          position: index + 1,
          prefill_discord_username: index === 0,
        })),
      }
      expect(validateCampaignInput(input)).toBeNull()
    }
  })

  it("rejects zero or more than five questions", () => {
    expect(validateCampaignInput({ ...campaign, questions: [] })).toMatch(/1-5/)
    expect(
      validateCampaignInput({
        ...campaign,
        questions: Array.from({ length: 6 }, (_, index) => ({
          ...questions[0],
          id: `q${index}`,
          field_key: `field_${index}`,
          position: index + 1,
          prefill_discord_username: index === 0,
        })),
      })
    ).toMatch(/1-5/)
  })

  it("rejects duplicate field keys and multiple participant keys", () => {
    expect(
      validateCampaignInput({
        ...campaign,
        questions: [
          { ...questions[0], field_key: "same" },
          {
            ...questions[1],
            field_key: "same",
            is_participant_key: true,
          },
        ],
      })
    ).toMatch(/field key/i)

    expect(
      validateCampaignInput({
        ...campaign,
        questions: questions.map((question) => ({
          ...question,
          is_participant_key: true,
        })),
      })
    ).toMatch(/unique participant/i)
  })

  it("rejects non-numeric Discord snowflakes", () => {
    expect(
      validateCampaignInput({ ...campaign, discord_channel_id: "channel" })
    ).toMatch(/snowflake/i)
    expect(
      validateCampaignInput({ ...campaign, discord_guild_id: "guild" })
    ).toMatch(/snowflake/i)
  })

  it("rejects an invalid activity end time when supplied", () => {
    expect(
      validateCampaignInput({ ...campaign, ends_at: "not-a-date" })
    ).toMatch(/end time/i)
  })
})


describe("reward code parsing", () => {
  it("preserves import order and removes blank lines", () => {
    expect(parseRewardCodes(" CODE-2 \n\nCODE-1\r\n")).toEqual([
      "CODE-2",
      "CODE-1",
    ])
  })

  it("rejects duplicate codes and validates the exact publish count", () => {
    expect(() => parseRewardCodes("A\nA")).toThrow(ActivityValidationError)
    expect(() => parseRewardCodes("A\nB", 20)).toThrow(/exactly 20/)
    expect(parseRewardCodes(Array.from({ length: 20 }, (_, i) => `C${i}`).join("\n"), 20))
      .toHaveLength(20)
  })
})


describe("published campaign behavior", () => {
  it("locks channel, end time, questions, winner limit, modal title, and code pool", () => {
    const active = { ...campaign, status: "active" as const }
    expect(validatePublishedPatch(active, { embed_title: "Updated" })).toBeNull()
    expect(validatePublishedPatch(active, { winner_message: "New {code}" })).toBeNull()
    expect(
      validatePublishedPatch(active, { discord_channel_id: "999" })
    ).toMatch(/locked/i)
    expect(validatePublishedPatch(active, { winner_limit: 30 })).toMatch(/locked/i)
    expect(validatePublishedPatch(active, { modal_title: "Changed" })).toMatch(/locked/i)
    expect(
      validatePublishedPatch(active, { ends_at: "2099-08-02T12:00:00.000Z" })
    ).toMatch(/locked/i)
    expect(validatePublishedPatch(active, { questions: [] })).toMatch(/locked/i)
    expect(validatePublishedPatch(active, { codes: ["X"] })).toMatch(/locked/i)
  })

  it("allows unchanged locked fields in a full active-campaign save", () => {
    const active = { ...campaign, status: "active" as const }
    expect(
      validatePublishedPatch(active, {
        ...active,
        embed_title: "Updated public title",
      })
    ).toBeNull()
  })
})


describe("Discord message payload", () => {
  it("uses the persistent primary activity button", () => {
    expect(buildActivityDiscordBody(campaign)).toEqual({
      embeds: [
        {
          title: "Tell us your favorite game",
          description: "Click below to participate.",
          color: 0xff9933,
        },
      ],
      components: [
        {
          type: 1,
          components: [
            {
              type: 2,
              style: 1,
              label: "Join Activity",
              custom_id: "activity_join",
              disabled: false,
            },
          ],
        },
      ],
    })
  })

  it("can disable the public button when closing", () => {
    const body = buildActivityDiscordBody(campaign, true)
    expect(body.components[0].components[0].disabled).toBe(true)
  })
})


describe("submission filtering and CSV", () => {
  const submissions: ActivitySubmission[] = [
    {
      id: "s1",
      campaign_id: "c1",
      discord_user_id: "100",
      discord_username: "Alice",
      answers: { fp_id: "FP-1", favorite_game: "Lucky Penny" },
      participant_key_normalized: "fp-1",
      outcome: "winner",
      reward_code: "CODE-1",
      submitted_at: "2026-07-27T01:00:00Z",
    },
    {
      id: "s2",
      campaign_id: "c1",
      discord_user_id: "200",
      discord_username: "Bob",
      answers: { fp_id: "FP-2", favorite_game: "=IMPORTXML()" },
      participant_key_normalized: "fp-2",
      outcome: "sold_out",
      reward_code: null,
      submitted_at: "2026-07-27T02:00:00Z",
    },
  ]

  it("searches Discord and FP ID and filters by outcome", () => {
    expect(filterActivitySubmissions(submissions, "alice", "all")).toHaveLength(1)
    expect(filterActivitySubmissions(submissions, "FP-2", "all")).toHaveLength(1)
    expect(filterActivitySubmissions(submissions, "", "winner")).toEqual([
      submissions[0],
    ])
  })

  it("exports UTF-8 BOM CSV with quoting and formula hardening", () => {
    const csv = toActivityCsv(submissions, questions)
    expect(csv.startsWith("\uFEFF")).toBe(true)
    expect(csv).toContain('"Discord Username"')
    expect(csv).toContain('"Favorite FP Game"')
    expect(csv).toContain("\"'=IMPORTXML()\"")
    expect(csv).toContain('"CODE-1"')
  })
})
