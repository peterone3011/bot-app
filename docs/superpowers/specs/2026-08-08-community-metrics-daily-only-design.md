# Community Metrics Daily-Only Design

## Goal

Simplify the `FP-DC数据` Lark Base table so it contains only daily community metrics. Remove weekly records and fields instead of mixing two reporting grains in one table.

## Lark Base Changes

- Keep all 39 migrated daily records.
- Delete the 5 existing weekly records whose `记录` value starts with `周报 `.
- Delete these fields:
  - `统计类型`
  - `本周贴文 Reaction 数`
  - `Gaming Alerts 总订阅人数`
  - `Exclusive Updates 总订阅人数`
  - `Lucky Drops 总订阅人数`
- Keep these fields:
  - `记录`
  - `日期`
  - `当前总人数`
  - `新增人数`
  - `离开人数`
  - `净增长`
  - `Gaming Alerts 新增订阅人数`
  - `Exclusive Updates 新增订阅人数`
  - `Lucky Drops 新增订阅人数`
- Configure every retained numeric metric field as an integer number field. `日期` remains a date field and `记录` remains the primary text field.

## Bot Changes

- Keep the daily rollup schedule at 23:59 Beijing time.
- Remove the weekly rollup task and weekly reaction/member-total calculation path.
- Daily upserts send only the nine retained fields and continue to use `日报 YYYY/MM/DD` as the idempotent key.
- Preserve write-ahead pending storage, retries, cross-process locking, and deterministic Lark `client_token` behavior.
- Do not read from or write to the legacy Lark Sheet.

## Rollout

1. Add tests proving no weekly task or weekly-only fields remain.
2. Update and verify the Bot code locally.
3. Use a repeatable cleanup script to delete weekly records, delete obsolete fields, and set retained numeric field formatting to integer.
4. Run the cleanup against the production Base and verify 39 daily records and 9 fields remain.
5. Deploy the Bot once and verify Railway startup logs.

The cleanup script must fail before destructive changes if the target app/table differs from the approved IDs or if unexpected record types are present. Existing daily records and the legacy Sheet remain untouched.
