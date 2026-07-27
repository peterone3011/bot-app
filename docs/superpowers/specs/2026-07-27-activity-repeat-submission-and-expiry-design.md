# Activity Repeat Submission And Expiry Design

## Behavior

- A Discord user receives at most one reward code per campaign.
- A repeat submission updates the existing row's Discord username, answers, and normalized participant key.
- Reward code, outcome, winner order, and original `submitted_at` remain unchanged.
- A participant key already owned by another Discord user rejects the repeat update.
- Every published campaign must have a future end time.
- After the end time, clicking the Discord button returns the configured closed message and does not open the modal.
- The claim RPC also rejects expired campaigns so a modal opened before expiry cannot update or claim after expiry.

## Data And Dashboard

- Add nullable `ends_at timestamptz` so drafts can be saved before scheduling.
- Publication requires `ends_at > now()`.
- Dashboard edits the end time in Beijing time and stores UTC.
- End time is locked after publication.

## Verification

- Bot tests cover expired-button behavior.
- Dashboard tests cover end-time validation, locking, and publication rejection.
- Migration tests cover answer replacement, participant-key conflict exclusion, immutable submission time, and expiry enforcement.
