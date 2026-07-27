# Discord Reusable Activity System Design

## Scope

Build a Supabase-backed Discord activity system that administrators operate
from the existing Dashboard. A campaign publishes one Discord embed with a
persistent button. Players click the button, answer one to five text questions
in a Discord Modal, and receive an ephemeral result.

The first campaign awards twenty different codes to the first twenty valid
participants. The reusable system must also preserve all later sold-out
submissions for reporting.

## Data Model

### `activity_campaigns`

Stores lifecycle state, Discord message configuration, Modal configuration,
winner limit, and private response templates.

- State is `draft`, `active`, or `closed`.
- Discord channel and message IDs are stored as text to preserve snowflake
  precision.
- `discord_message_id` is unique when present.
- Published campaigns lock channel, questions, winner limit, and code pool.
- Active campaigns may still update public copy and private reply templates.
- Only draft campaigns may be deleted.

### `activity_questions`

Stores one to five ordered questions per campaign.

- Style is `short` or `paragraph`.
- A question may be required and may have a placeholder.
- At most one question may prefill the current Discord username.
- At most one question may be the unique participant key.

### `activity_codes`

Stores encrypted-at-rest-by-platform reward code values in import order.

- Position is unique within a campaign.
- Code value is unique within a campaign.
- Assignment is represented by `claimed_by_submission_id` and `claimed_at`.

### `activity_submissions`

Stores immutable Discord identity, user-provided answers, normalized participant
key, outcome, assigned code reference, and timestamps.

- A Discord user can submit once per campaign.
- A normalized participant key can be used once per campaign when present.
- Sold-out answers are retained.

## Atomic Claim RPC

`claim_activity_reward` receives campaign ID, Discord user identity, answers,
and normalized participant key.

Inside one transaction it:

1. Locks the campaign row.
2. Rejects non-active campaigns with `closed`.
3. Returns the existing submission result for the same Discord user.
4. Rejects a participant key already owned by another Discord user.
5. Inserts the submission.
6. Locks and assigns the first unclaimed code by position when the winner limit
   has not been reached.
7. Returns exactly one of:
   `winner`, `existing_winner`, `sold_out`, `existing_sold_out`,
   `participant_key_taken`, or `closed`.

Unique constraints are the final concurrency guard. Any database error rolls
back the complete operation and therefore cannot consume a code.

## Discord Runtime

The Bot registers one persistent `activity_join` button at startup. The button
callback resolves an active campaign from `interaction.message.id`, loads its
questions with a short timeout, and opens a dynamic Modal.

Discord username questions are prefilled from the current interaction user but
remain editable. Modal submission defers ephemerally before calling Supabase in
a worker thread. The RPC result selects the configured private reply. Duplicate
winners see their original code again. Database failures show a generic
ephemeral retry message.

## Dashboard

Add an authenticated Activity Management area with:

- Campaign list and create/copy actions.
- Detail view with Settings, Reward Codes, and Submissions tabs.
- Draft editing for Discord, Modal, questions, and reply templates.
- Exact code-pool validation before publish.
- Direct Discord publish and active-message update.
- Close operation that changes database state before disabling the Discord
  button.
- Search/filter submission table and UTF-8 CSV export.

All Dashboard and Bot access uses the Supabase service role. RLS blocks direct
client access.

## Rollout

Apply the repeatable migration before deploying code. Deploy Dashboard and Bot,
then exercise a temporary campaign with dummy codes in private `bot-commands`.
Close and delete the temporary campaign data after verification.

Create `FP Favorite Game Reward - Draft` with winner limit 20, the three
approved questions, and approved private replies. Do not add real codes, choose
a channel, or publish the formal campaign automatically.
