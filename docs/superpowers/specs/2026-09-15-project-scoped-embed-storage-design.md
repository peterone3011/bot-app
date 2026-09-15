# Project-Scoped Embed Storage Design

## Goal

Make the interactive Discord Embed builder reusable by any configured project
without sharing FortunePurple's Supabase `messages` table or requiring a
database for new projects.

## Decision

Each project stores its Embed builder records in its existing Railway volume
directory:

`/data/<project-slug>/embed-messages.json`

The file contains only that project's draft, scheduled, and published Embed
records. All reads and writes go through a project-scoped repository object.

## Scope

- Preserve the current `/embed`, `/edit-embed`, and message-context `Edit
  Embed` workflows.
- Preserve drafts, scheduled sends, published records, labels, embeds, link
  buttons, and Beijing-time scheduling behavior.
- Keep one project from reading or modifying another project's Embed records.
- On FortunePurple's first start, import its existing Supabase `messages`
  records into the project file once.
- Stop normal Embed-builder reads and writes to Supabase after the migration.
- Do not migrate Big Win, activity, dashboard, role, or community-metrics
  data.

## Storage Contract

`EmbedMessageStore` owns one JSON file and exposes async methods:

- `list() -> list[dict[str, Any]]`
- `get(message_id: str) -> dict[str, Any] | None`
- `upsert(message: dict[str, Any]) -> None`
- `delete(message_id: str) -> None`
- `ensure_migrated(importer: Callable[[], Awaitable[list[dict[str, Any]]]]) -> None`

Records keep the legacy message schema, so the builder UI does not need to
change its visible behavior.

Writes are serialized per store with an async lock and saved through a
temporary file followed by `replace()`. A valid old file remains intact if a
write fails before replacement.

## Migration

Only the `fortunepurple` project is configured with an optional legacy import
source. On first Embed-builder startup:

1. Create the project state directory.
2. If the JSON file already exists, do nothing.
3. Read the legacy Supabase records once.
4. Validate that every record has a string `id` and discard malformed records
   with a log entry.
5. Persist the valid records into the project JSON file, including an empty
   list when no records exist.

Once the file exists, Supabase is never consulted for normal builder work or
subsequent restarts. New projects create an empty file and never require
Supabase credentials.

## Runtime Integration

`ProjectRuntime` supplies a project-scoped `EmbedMessageStore`. The shared
Embed Cog receives that store rather than importing the legacy `cogs.db`
module. The runner installs the shared Cog for every project with
`manual_embed: true`.

The existing JSON state remains on the Railway volume across deploys. The Bot
uses its existing project-specific Guild command sync, so `/embed` and the
context menu remain isolated to the configured Guild.

## Failure Handling

- A malformed or unreadable JSON file prevents the builder from mutating data
  and logs the project-scoped error; it does not overwrite the file.
- A legacy import failure leaves no JSON file, so the next restart retries the
  import without losing Supabase records.
- A scheduled-send failure leaves the record scheduled for the next loop,
  matching the old behavior.
- Builder storage errors return a private retry message where an interaction
  can be answered safely.

## Verification

- Unit tests cover project-path isolation, atomic write behavior, corrupted
  state rejection, and one-time migration.
- Embed Cog tests cover draft creation, update, schedule, publish, and edit
  using the project store.
- A runner test confirms two projects receive different stores.
- FortunePurple migration is exercised against a fake legacy importer.
- Full Python test suite must pass before deployment.

## Out of Scope

- A web dashboard for Embed management.
- Automatic deletion of the legacy Supabase table.
- Migrating non-Embed legacy tables.
- Changing the public Discord Embed editor interface.
