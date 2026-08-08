# Community Metrics Lark Base Migration Design

## Goal

Move all existing Discord daily and weekly community metrics from the current
Lark Sheet into the `FP-DC数据` table in Lark Base, then use that table for future
automatic rollups after the migrated data is reviewed.

## Scope

- Source spreadsheet token: `PA8usyjmshX40HtXaeTjkr4Apne`
- Source sheet ID: `e348a1`
- Target Base app token: `CeqtbxWt5azkkHs8OzpjZ9D1p2e`
- Target table ID: `tblMeRm8yocZPqUR` (`FP-DC数据`)
- Keep the source Sheet unchanged as a fallback.
- This first stage changes only the Base structure and migrates history. It does
  not switch the production Bot writer.

## Data Model

The target uses one table for both rollup types. The primary text field is
`记录`, with values such as `日报 2026/08/06` and `周报 2026/08/02`.

Common fields:

- `统计类型`: single select, `日报` or `周报`
- `日期`: date
- `当前总人数`: number
- `新增人数`: number
- `离开人数`: number
- `净增长`: number

Daily-only fields:

- `Gaming Alerts 新增订阅人数`
- `Exclusive Updates 新增订阅人数`
- `Lucky Drops 新增订阅人数`

Weekly-only fields:

- `本周贴文 Reaction 数`
- `Gaming Alerts 总订阅人数`
- `Exclusive Updates 总订阅人数`
- `Lucky Drops 总订阅人数`

The future writer identifies a record by `(统计类型, 日期)` and updates the
existing record when found. This keeps reruns idempotent.

## Views

View creation and configuration are deferred. This migration must not create,
rename, or otherwise modify any Base views. Views can be added after the data
migration has been reviewed without affecting the data model or records.

## Migration Rules

- Migrate every non-empty daily and weekly row present at execution time. The
  validated baseline is 38 daily rows and 5 weekly rows; newer rollups are
  included rather than rejected.
- Convert Lark/Excel serial dates to `YYYY/MM/DD` before writing date values.
- Convert `/` and empty source cells to empty Base fields, not zero.
- Keep negative growth values unchanged.
- Daily and weekly records on the same date remain separate records.
- Remove only the five blank placeholder records currently in `FP-DC数据`.
- Do not delete or edit any source Sheet rows.

## Verification

- Target record count exactly matches the normalized non-empty source rows.
- There are no duplicate `(统计类型, 日期)` pairs.
- There are at least 38 daily and 5 weekly records, including newer source rows.
- Spot-check source-to-target values for `2026/07/03`, `2026/08/02`, and
  `2026/08/06`.
- Re-read the complete Base table after writing and compare every migrated field
  with the normalized source data.

## Cutover

After the user reviews the migrated Base:

1. Replace the Sheet client in `community_metrics.py` with a Base client.
2. Preserve the current 23:59 Beijing daily and Sunday weekly schedules.
3. Add tests for record lookup, update/create behavior, field mapping, and Lark
   API failures.
4. Deploy the Bot change only after tests and a final migration recheck pass.
5. Keep the old Sheet read-only as a rollback reference.
