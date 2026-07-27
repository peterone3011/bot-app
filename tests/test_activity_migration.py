from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260727_activity_campaigns.sql"
REPEAT_AND_EXPIRY_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260727201000_activity_repeat_submission_and_expiry.sql"
)


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_activity_migration_defines_all_tables_and_rls():
    sql = migration_sql()
    for table in (
        "activity_campaigns",
        "activity_questions",
        "activity_codes",
        "activity_submissions",
    ):
        assert f"create table if not exists public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql


def test_activity_migration_enforces_campaign_uniqueness():
    sql = migration_sql()
    assert "activity_submissions_campaign_discord_user_key" in sql
    assert "activity_submissions_campaign_participant_key_key" in sql
    assert "activity_codes_campaign_position_key" in sql
    assert "activity_codes_campaign_code_key" in sql
    assert "activity_campaigns_discord_message_id_key" in sql
    assert "activity_submissions_campaign_reward_code_fkey" in sql
    assert "activity_codes_campaign_claimed_submission_fkey" in sql
    assert "claimed_by_submission_id" in sql
    assert "claimed_at" in sql
    assert "activity_codes_claimed_submission_key" in sql
    assert "activity_validate_claim_pair" in sql
    assert "activity_codes_validate_claim_pair" in sql
    assert "activity_submissions_validate_claim_pair" in sql
    assert "claimed activity code cannot be reassigned or cleared" in sql
    assert "winning activity submission cannot be downgraded or reassigned" in sql


def test_claim_rpc_has_required_outcomes_and_locking():
    sql = migration_sql()
    assert "create or replace function public.claim_activity_reward" in sql
    for outcome in (
        "winner",
        "existing_winner",
        "sold_out",
        "existing_sold_out",
        "participant_key_taken",
        "closed",
    ):
        assert f"'{outcome}'" in sql
    assert "for update" in sql
    assert "order by position" in sql


def test_repeat_submission_and_expiry_migration_updates_answers_and_blocks_expired_claims():
    sql = REPEAT_AND_EXPIRY_MIGRATION.read_text(encoding="utf-8").lower()
    assert "add column if not exists ends_at timestamptz" in sql
    assert "where status = 'active'" in sql
    assert "and ends_at is null" in sql
    assert "v_campaign.ends_at <= now()" in sql
    assert "discord_username = p_discord_username" in sql
    assert "answers = coalesce(p_answers, '{}'::jsonb)" in sql
    assert "participant_key_normalized = v_participant_key" in sql
    assert "s.id <> v_existing.id" in sql
    assert "submitted_at =" not in sql
    assert "invalid_end_time" in sql


def test_dashboard_mutations_use_locking_database_rpcs():
    sql = migration_sql()
    for function_name in (
        "save_activity_draft",
        "replace_activity_codes",
        "activate_activity_campaign",
    ):
        assert f"create or replace function public.{function_name}" in sql
    assert "activity_locked" in sql
    assert "invalid_code_count" in sql
    assert "p_questions is null" in sql
    assert "p_expected_revision bigint" in sql
    assert "stale_draft" in sql
    assert "new.revision = old.revision + 1" in sql


def test_sql_integration_covers_the_full_campaign_lifecycle():
    integration_sql = (
        ROOT / "tests" / "sql" / "activity_campaigns_integration.sql"
    ).read_text(encoding="utf-8").lower()
    for function_name in (
        "save_activity_draft",
        "replace_activity_codes",
        "activate_activity_campaign",
        "claim_activity_reward",
    ):
        assert f"public.{function_name}(" in integration_sql
    assert "activity_locked" in integration_sql
    assert "stale_draft" in integration_sql
    assert "foreach v_function" in integration_sql
    assert "client roles must not execute activity rpcs" in integration_sql


def test_activity_migration_seeds_unpublished_formal_draft():
    sql = migration_sql()
    assert "fp favorite game reward - draft" in sql
    assert "discord username" in sql
    assert "fortunepurple id" in sql
    assert "favorite fp game" in sql
    assert "congratulations! you’re one of our first participants." in sql
    assert "sorry, all reward codes have been claimed." in sql
    assert "this activity has ended." in sql


def test_activity_migration_denies_client_privileges():
    sql = migration_sql()
    assert "revoke all on function public.claim_activity_reward" in sql
    assert "from public, anon, authenticated" in sql
    integration_sql = (
        ROOT / "tests" / "sql" / "activity_campaigns_integration.sql"
    ).read_text(encoding="utf-8").lower()
    assert "array['anon', 'authenticated']" in integration_sql
    assert "has_table_privilege(v_role, v_table, v_privilege)" in integration_sql
    assert "and not relrowsecurity" in integration_sql
    assert "has_function_privilege(" in integration_sql
    assert "'truncate', 'references', 'trigger'" in integration_sql
