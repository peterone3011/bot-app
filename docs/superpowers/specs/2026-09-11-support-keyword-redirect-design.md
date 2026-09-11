# Financial Support Keyword Redirect Design

## Goal

Add a Discord auto-reply that directs financial product issues to the official live support channel. The feature must remain isolated from daily publishing, community metrics, activities, and other existing bot workflows.

## Scope

The bot listens only in these Discord channels:

- `1546766591096787026`
- `1546766625209065492`
- `1546766642820677652`

The support destination is Discord channel `1509148079566225480`.

The feature covers deposit, withdrawal, cash-out, redemption, payment, refund, and missing-funds issues. It does not cover login, account verification, game errors, product questions unrelated to money, or Discord community activity rewards.

## Architecture

Create an independent `cogs/support_redirect.py` Cog and load it from `bot.py`. The Cog owns message normalization, financial-issue matching, cooldown state, Embed construction, and reply delivery.

Configuration is supplied through Railway environment variables:

- `SUPPORT_REDIRECT_ENABLED`
- `SUPPORT_TRIGGER_CHANNEL_IDS`, a comma-separated channel ID list
- `SUPPORT_CHANNEL_ID`
- `SUPPORT_REDIRECT_COOLDOWN_SECONDS`, defaulting to `600`

Missing or invalid configuration disables the Cog's replies and produces a clear startup log. It must not stop the bot from loading other Cogs.

## Matching Rules

Normalize incoming content by applying case-insensitive matching, replacing punctuation and separators with spaces, and collapsing repeated whitespace.

Explicit financial terms can trigger directly:

- `withdraw`, including `withdrawal`
- `cash out` and `cashout`
- `redemption` and `redeem sc`
- `deposit`
- `refund`

Ambiguous status words never trigger alone. They trigger only when combined with financial context. Supported examples include:

- `withdrawal pending`, `cashout failed`, `refund not received`
- `payment issue`, `payment failed`, `payment declined`
- `deposit missing`, `deposit not received`
- `money missing`, `funds not received`
- `charged twice`, `duplicate charge`, `wrong amount charged`

Words such as `pending`, `missing`, `failed`, `reward`, `bonus`, and `game` do not trigger by themselves. `bonus missing` and `reward missing` are deliberately excluded to avoid redirecting Discord community reward questions.

Messages from bots, direct messages, and channels outside the configured allowlist are ignored.

## Reply Behavior

Reply to the triggering message without mentioning its author. Use a Discord red Embed with no role, user, or everyone mentions.

Title:

`⚠️ Discord cannot handle order-related issues`

Description:

```text
For any deposit, withdrawal, or refund issues, please contact our live support in <#1509148079566225480>.

Please fill out the form to start a chat with our support team and describe your issue clearly.
```

The support channel mention remains clickable. The copy does not claim that support uses a queue or promise a response time.

## Cooldown

Use an in-memory cooldown keyed by guild, channel, and Discord user. The same user can receive at most one redirect per monitored channel every 10 minutes. Other users are unaffected.

Record the cooldown only after Discord accepts the reply. Expired entries are removed opportunistically. A bot restart clears cooldown state, which is acceptable for this feature.

## Error Handling

Discord permission, deletion race, and network failures are logged with channel, message, and user IDs. Errors are contained inside the Cog and must not interrupt other message listeners. The original player message is never edited or deleted.

## Tests

Unit tests cover:

- explicit financial terms and capitalization
- spaces, hyphens, punctuation, and repeated whitespace
- contextual status phrases
- ambiguous words that must not trigger alone
- excluded reward and bonus phrases
- channel allowlisting and bot-message filtering
- successful Embed content and clickable support channel reference
- per-user, per-channel cooldown behavior
- send failure behavior and cooldown assignment only after success

Run the full Python test suite before deployment. Configure Railway variables before pushing so the auto-deploy never starts with partial configuration. After deployment, verify the new commit status, bot login, startup configuration log, and absence of new error logs.
