# Community Metrics Single-Date Design

## Goal

Remove the duplicated date display from the daily-only `FP-DC数据` Base table while preserving idempotent daily updates.

## Chosen Structure

- Keep the current primary text field, rename it from `记录` to `日期`, and store `YYYY/MM/DD` text.
- Delete the current secondary date field after its values have been represented in the primary field.
- Keep the seven integer metric fields unchanged.
- Final schema has eight fields: one date-key text field plus seven integer metric fields.

This is preferred over hiding the primary field, which Lark Base does not remove from the table structure, or retaining both fields with different labels, which still duplicates the same information.

## Bot Behavior

- Daily rollups continue at 23:59 Beijing time.
- The Bot uses `YYYY/MM/DD` as both the displayed primary value and idempotent upsert key.
- Base lookups compare the primary `日期` text field.
- Durable pending writes, retry behavior, cross-process locking, and deterministic `client_token` remain unchanged.

## Migration Safety

- A dedicated idempotent migration validates the exact approved app and table IDs.
- Before writes, all remote records must have either `日报 YYYY/MM/DD` or already-migrated `YYYY/MM/DD` primary values; all dates must be unique.
- Migration order is: normalize primary values, delete the secondary date field, then rename the primary field to `日期`.
- Rerunning after interruption continues from the observed state without repeating destructive operations.
- The migration does not modify any metric value or the legacy Sheet.
- Because old and new Bot payloads use different field names, run the migration and deploy the reviewed Bot together well before 23:59. If deployment fails, stop and repair before the scheduled rollup.

## Verification

- Exactly 39 existing records remain before the next scheduled rollup.
- Exactly eight fields remain.
- Every primary value matches `YYYY/MM/DD` and is unique.
- Railway reports the new deployment as `SUCCESS/RUNNING` with no startup errors.
