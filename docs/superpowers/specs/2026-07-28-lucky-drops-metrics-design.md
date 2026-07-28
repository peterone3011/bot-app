# Lucky Drops Community Metrics Design

## Goal

Add Lucky Drops role subscription metrics to the existing Discord community
daily and weekly rollups without changing their schedule, existing metric
definitions, or Lark API call pattern.

## Data Layout

- Daily data remains in columns A:H.
- Column H records unique members who subscribed to Lucky Drops during that
  Beijing calendar day.
- Weekly data remains anchored at column I and expands through column Q.
- Column Q records the current number of members holding the Lucky Drops role
  when the Sunday 23:59 Beijing-time rollup runs.
- Existing columns A:G and I:P retain their current meanings and positions.

## Data Flow

The existing role selector already records a generic `role_subscribe` event
with the Discord member ID and exact role name whenever a role is added.
Daily Lucky Drops subscriptions will therefore use the same event log and
unique-member counting logic as Gaming Alerts and Exclusive Updates.

For the weekly snapshot, the bot will find the Lucky Drops guild role using
the same case-insensitive partial-name matching used by the other subscription
roles and write its current member count.

## Configuration

Add `METRICS_LUCKY_DROPS_ROLE_NAME`, defaulting to `Lucky Drops`, so the role
can be renamed through deployment configuration without a code change.

## Reliability

- No new scheduled tasks or Lark requests are introduced.
- A missing Lucky Drops role produces a weekly count of zero, matching the
  existing behavior for missing subscription roles.
- Existing daily and weekly rows continue to be updated by date rather than
  duplicated.

## Verification

Tests will cover:

- Unique daily Lucky Drops subscriptions.
- The expanded daily and weekly sheet ranges.
- Weekly Lucky Drops member totals.
- Preservation of existing metric ordering.
