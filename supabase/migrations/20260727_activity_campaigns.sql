begin;

create extension if not exists pgcrypto;

create table if not exists public.activity_campaigns (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(name) between 1 and 120),
    status text not null default 'draft'
        check (status in ('draft', 'active', 'closed')),
    winner_limit integer not null default 20
        check (winner_limit between 1 and 10000),
    discord_guild_id text,
    discord_channel_id text,
    discord_message_id text,
    embed_title text check (embed_title is null or char_length(embed_title) <= 256),
    embed_description text
        check (embed_description is null or char_length(embed_description) <= 4000),
    image_url text,
    color integer check (color is null or color between 0 and 16777215),
    button_label text not null default 'Join Activity'
        check (char_length(button_label) between 1 and 80),
    modal_title text not null default 'Activity Entry'
        check (char_length(modal_title) between 1 and 45),
    winner_message text not null,
    sold_out_message text not null,
    closed_message text not null,
    revision bigint not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    published_at timestamptz,
    closed_at timestamptz,
    constraint activity_campaigns_discord_message_id_key
        unique (discord_message_id),
    constraint activity_campaigns_active_discord_fields_check check (
        status = 'draft'
        or (
            discord_guild_id is not null
            and discord_channel_id is not null
            and discord_message_id is not null
        )
    )
);

alter table public.activity_campaigns
    add column if not exists revision bigint not null default 0;

create table if not exists public.activity_questions (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.activity_campaigns(id) on delete cascade,
    field_key text not null check (field_key ~ '^[a-z][a-z0-9_]{0,63}$'),
    position integer not null check (position between 1 and 5),
    label text not null check (char_length(label) between 1 and 45),
    input_style text not null default 'short'
        check (input_style in ('short', 'paragraph')),
    required boolean not null default true,
    placeholder text check (placeholder is null or char_length(placeholder) <= 100),
    min_length integer not null default 0 check (min_length between 0 and 4000),
    max_length integer not null default 100
        check (max_length between 1 and 4000),
    prefill_discord_username boolean not null default false,
    is_participant_key boolean not null default false,
    created_at timestamptz not null default now(),
    constraint activity_questions_campaign_position_key
        unique (campaign_id, position),
    constraint activity_questions_campaign_field_key_key
        unique (campaign_id, field_key),
    constraint activity_questions_length_check check (min_length <= max_length)
);

create unique index if not exists activity_questions_one_prefill_per_campaign
    on public.activity_questions (campaign_id)
    where prefill_discord_username;

create unique index if not exists activity_questions_one_participant_key_per_campaign
    on public.activity_questions (campaign_id)
    where is_participant_key;

create table if not exists public.activity_codes (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.activity_campaigns(id) on delete cascade,
    position integer not null check (position > 0),
    code text not null check (char_length(btrim(code)) between 1 and 200),
    claimed_by_submission_id uuid,
    claimed_at timestamptz,
    created_at timestamptz not null default now(),
    constraint activity_codes_campaign_position_key
        unique (campaign_id, position),
    constraint activity_codes_campaign_code_key
        unique (campaign_id, code),
    constraint activity_codes_campaign_id_id_key unique (campaign_id, id),
    constraint activity_codes_claimed_submission_key
        unique (claimed_by_submission_id),
    constraint activity_codes_claim_state_check check (
        (claimed_by_submission_id is null and claimed_at is null)
        or (claimed_by_submission_id is not null and claimed_at is not null)
    )
);

create table if not exists public.activity_submissions (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.activity_campaigns(id) on delete cascade,
    discord_user_id text not null check (discord_user_id ~ '^[0-9]+$'),
    discord_username text not null check (char_length(discord_username) between 1 and 100),
    answers jsonb not null check (jsonb_typeof(answers) = 'object'),
    participant_key_normalized text,
    outcome text not null check (outcome in ('winner', 'sold_out')),
    reward_code_id uuid,
    submitted_at timestamptz not null default now(),
    constraint activity_submissions_campaign_discord_user_key
        unique (campaign_id, discord_user_id),
    constraint activity_submissions_campaign_id_id_key unique (campaign_id, id),
    constraint activity_submissions_reward_code_key unique (reward_code_id),
    constraint activity_submissions_campaign_reward_code_fkey
        foreign key (campaign_id, reward_code_id)
        references public.activity_codes(campaign_id, id)
        on delete cascade,
    constraint activity_submissions_reward_outcome_check check (
        (outcome = 'winner' and reward_code_id is not null)
        or (outcome = 'sold_out' and reward_code_id is null)
    )
);

do $$
begin
    if not exists (
        select 1
          from pg_constraint
         where conname = 'activity_codes_campaign_claimed_submission_fkey'
           and conrelid = 'public.activity_codes'::regclass
    ) then
        alter table public.activity_codes
            add constraint activity_codes_campaign_claimed_submission_fkey
            foreign key (campaign_id, claimed_by_submission_id)
            references public.activity_submissions(campaign_id, id)
            on delete cascade;
    end if;
end;
$$;

create unique index if not exists activity_submissions_campaign_participant_key_key
    on public.activity_submissions (campaign_id, participant_key_normalized)
    where participant_key_normalized is not null;

create index if not exists activity_questions_campaign_order_idx
    on public.activity_questions (campaign_id, position);

create index if not exists activity_codes_campaign_order_idx
    on public.activity_codes (campaign_id, position);

create index if not exists activity_submissions_campaign_time_idx
    on public.activity_submissions (campaign_id, submitted_at desc);

create or replace function public.activity_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = clock_timestamp();
    new.revision = old.revision + 1;
    return new;
end;
$$;

drop trigger if exists activity_campaigns_set_updated_at on public.activity_campaigns;
create trigger activity_campaigns_set_updated_at
before update on public.activity_campaigns
for each row execute function public.activity_set_updated_at();

create or replace function public.activity_validate_claim_pair()
returns trigger
language plpgsql
as $$
begin
    if tg_table_name = 'activity_codes' then
        if tg_op = 'UPDATE'
           and old.claimed_by_submission_id is not null
           and (
               new.claimed_by_submission_id is distinct from old.claimed_by_submission_id
               or new.claimed_at is distinct from old.claimed_at
           ) then
            raise exception 'claimed activity code cannot be reassigned or cleared';
        end if;
        if new.claimed_by_submission_id is null then
            return new;
        end if;
        if not exists (
            select 1
              from public.activity_submissions s
             where s.id = new.claimed_by_submission_id
               and s.campaign_id = new.campaign_id
               and s.reward_code_id = new.id
               and s.outcome = 'winner'
        ) then
            raise exception 'activity code and submission claim references must match';
        end if;
    else
        if tg_op = 'UPDATE'
           and old.outcome = 'winner'
           and (
               new.outcome <> 'winner'
               or new.reward_code_id is distinct from old.reward_code_id
           ) then
            raise exception 'winning activity submission cannot be downgraded or reassigned';
        end if;
        if new.outcome = 'sold_out' then
            return new;
        end if;
        if not exists (
            select 1
              from public.activity_codes c
             where c.id = new.reward_code_id
               and c.campaign_id = new.campaign_id
               and c.claimed_by_submission_id = new.id
               and c.claimed_at is not null
        ) then
            raise exception 'activity submission and code claim references must match';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists activity_codes_validate_claim_pair
    on public.activity_codes;
create constraint trigger activity_codes_validate_claim_pair
after insert or update on public.activity_codes
deferrable initially deferred
for each row execute function public.activity_validate_claim_pair();

drop trigger if exists activity_submissions_validate_claim_pair
    on public.activity_submissions;
create constraint trigger activity_submissions_validate_claim_pair
after insert or update on public.activity_submissions
deferrable initially deferred
for each row execute function public.activity_validate_claim_pair();

alter table public.activity_campaigns enable row level security;
alter table public.activity_questions enable row level security;
alter table public.activity_codes enable row level security;
alter table public.activity_submissions enable row level security;

revoke all on public.activity_campaigns from anon, authenticated;
revoke all on public.activity_questions from anon, authenticated;
revoke all on public.activity_codes from anon, authenticated;
revoke all on public.activity_submissions from anon, authenticated;

grant all on public.activity_campaigns to service_role;
grant all on public.activity_questions to service_role;
grant all on public.activity_codes to service_role;
grant all on public.activity_submissions to service_role;

create or replace function public.save_activity_draft(
    p_campaign_id uuid,
    p_campaign jsonb,
    p_questions jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_campaign public.activity_campaigns%rowtype;
    v_question_count integer;
    v_result jsonb;
begin
    select *
      into v_campaign
      from public.activity_campaigns
     where id = p_campaign_id
     for update;

    if not found then
        raise exception 'activity_not_found';
    end if;
    if v_campaign.status <> 'draft' then
        raise exception 'activity_locked';
    end if;
    if p_questions is null or jsonb_typeof(p_questions) <> 'array' then
        raise exception 'invalid_questions';
    end if;

    v_question_count := jsonb_array_length(p_questions);
    if v_question_count < 1 or v_question_count > 5 then
        raise exception 'invalid_questions';
    end if;

    update public.activity_campaigns
       set name = case when p_campaign ? 'name'
                       then p_campaign ->> 'name' else name end,
           winner_limit = case when p_campaign ? 'winner_limit'
                               then (p_campaign ->> 'winner_limit')::integer
                               else winner_limit end,
           discord_channel_id = case when p_campaign ? 'discord_channel_id'
                                     then nullif(p_campaign ->> 'discord_channel_id', '')
                                     else discord_channel_id end,
           embed_title = case when p_campaign ? 'embed_title'
                              then nullif(p_campaign ->> 'embed_title', '')
                              else embed_title end,
           embed_description = case when p_campaign ? 'embed_description'
                                    then nullif(p_campaign ->> 'embed_description', '')
                                    else embed_description end,
           image_url = case when p_campaign ? 'image_url'
                            then nullif(p_campaign ->> 'image_url', '')
                            else image_url end,
           color = case when p_campaign ? 'color'
                        then (p_campaign ->> 'color')::integer else color end,
           button_label = case when p_campaign ? 'button_label'
                               then p_campaign ->> 'button_label'
                               else button_label end,
           modal_title = case when p_campaign ? 'modal_title'
                              then p_campaign ->> 'modal_title'
                              else modal_title end,
           winner_message = case when p_campaign ? 'winner_message'
                                 then p_campaign ->> 'winner_message'
                                 else winner_message end,
           sold_out_message = case when p_campaign ? 'sold_out_message'
                                   then p_campaign ->> 'sold_out_message'
                                   else sold_out_message end,
           closed_message = case when p_campaign ? 'closed_message'
                                 then p_campaign ->> 'closed_message'
                                 else closed_message end
     where id = p_campaign_id;

    delete from public.activity_questions
     where campaign_id = p_campaign_id;

    insert into public.activity_questions (
        campaign_id,
        field_key,
        position,
        label,
        input_style,
        required,
        placeholder,
        min_length,
        max_length,
        prefill_discord_username,
        is_participant_key
    )
    select
        p_campaign_id,
        question ->> 'field_key',
        ordinality::integer,
        question ->> 'label',
        coalesce(question ->> 'input_style', 'short'),
        coalesce((question ->> 'required')::boolean, true),
        nullif(question ->> 'placeholder', ''),
        coalesce((question ->> 'min_length')::integer, 0),
        coalesce((question ->> 'max_length')::integer, 100),
        coalesce((question ->> 'prefill_discord_username')::boolean, false),
        coalesce((question ->> 'is_participant_key')::boolean, false)
      from jsonb_array_elements(p_questions)
           with ordinality as items(question, ordinality);

    select to_jsonb(c) || jsonb_build_object(
        'questions',
        coalesce(
            (
                select jsonb_agg(to_jsonb(q) order by q.position)
                  from public.activity_questions q
                 where q.campaign_id = p_campaign_id
            ),
            '[]'::jsonb
        )
    )
      into v_result
      from public.activity_campaigns c
     where c.id = p_campaign_id;

    return v_result;
end;
$$;

create or replace function public.replace_activity_codes(
    p_campaign_id uuid,
    p_codes text[]
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_campaign public.activity_campaigns%rowtype;
    v_count integer;
begin
    select *
      into v_campaign
      from public.activity_campaigns
     where id = p_campaign_id
     for update;

    if not found then
        raise exception 'activity_not_found';
    end if;
    if v_campaign.status <> 'draft' then
        raise exception 'activity_locked';
    end if;

    delete from public.activity_codes
     where campaign_id = p_campaign_id;

    insert into public.activity_codes (campaign_id, position, code)
    select p_campaign_id, ordinality::integer, btrim(code)
      from unnest(coalesce(p_codes, array[]::text[]))
           with ordinality as items(code, ordinality);

    update public.activity_campaigns
       set updated_at = updated_at
     where id = p_campaign_id;

    v_count := coalesce(array_length(p_codes, 1), 0);
    return v_count;
end;
$$;

drop function if exists public.activate_activity_campaign(uuid, text, text);

create or replace function public.activate_activity_campaign(
    p_campaign_id uuid,
    p_expected_revision bigint,
    p_discord_guild_id text,
    p_discord_message_id text
)
returns table (outcome text, existing_message_id text)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_campaign public.activity_campaigns%rowtype;
    v_question_count integer;
    v_code_count integer;
begin
    select *
      into v_campaign
      from public.activity_campaigns
     where id = p_campaign_id
     for update;

    if not found then
        return query select 'not_found'::text, null::text;
        return;
    end if;
    if v_campaign.status = 'active' then
        return query
        select 'already_active'::text, v_campaign.discord_message_id;
        return;
    end if;
    if v_campaign.status <> 'draft' then
        return query
        select 'closed'::text, v_campaign.discord_message_id;
        return;
    end if;
    if p_expected_revision is null
       or v_campaign.revision <> p_expected_revision then
        return query select 'stale_draft'::text, null::text;
        return;
    end if;

    select count(*)
      into v_question_count
      from public.activity_questions
     where campaign_id = p_campaign_id;
    if v_question_count < 1 or v_question_count > 5 then
        return query select 'invalid_questions'::text, null::text;
        return;
    end if;

    select count(*)
      into v_code_count
      from public.activity_codes
     where campaign_id = p_campaign_id;
    if v_code_count <> v_campaign.winner_limit then
        return query select 'invalid_code_count'::text, null::text;
        return;
    end if;

    update public.activity_campaigns
       set status = 'active',
           discord_guild_id = p_discord_guild_id,
           discord_message_id = p_discord_message_id,
           published_at = now(),
           closed_at = null
     where id = p_campaign_id;

    return query select 'activated'::text, p_discord_message_id;
end;
$$;

revoke all on function public.save_activity_draft(uuid, jsonb, jsonb)
    from public, anon, authenticated;
revoke all on function public.replace_activity_codes(uuid, text[])
    from public, anon, authenticated;
revoke all on function public.activate_activity_campaign(uuid, bigint, text, text)
    from public, anon, authenticated;
grant execute on function public.save_activity_draft(uuid, jsonb, jsonb)
    to service_role;
grant execute on function public.replace_activity_codes(uuid, text[])
    to service_role;
grant execute on function public.activate_activity_campaign(uuid, bigint, text, text)
    to service_role;

create or replace function public.claim_activity_reward(
    p_campaign_id uuid,
    p_discord_user_id text,
    p_discord_username text,
    p_answers jsonb,
    p_participant_key text default null
)
returns table (outcome text, reward_code text)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_campaign public.activity_campaigns%rowtype;
    v_existing public.activity_submissions%rowtype;
    v_code public.activity_codes%rowtype;
    v_participant_key text;
    v_winner_count integer;
    v_submission_id uuid;
begin
    select *
      into v_campaign
      from public.activity_campaigns
     where id = p_campaign_id
     for update;

    if not found or v_campaign.status <> 'active' then
        return query select 'closed'::text, null::text;
        return;
    end if;

    select *
      into v_existing
      from public.activity_submissions
     where campaign_id = p_campaign_id
       and discord_user_id = p_discord_user_id;

    if found then
        if v_existing.outcome = 'winner' then
            return query
            select 'existing_winner'::text, c.code
              from public.activity_codes c
             where c.id = v_existing.reward_code_id;
        else
            return query select 'existing_sold_out'::text, null::text;
        end if;
        return;
    end if;

    v_participant_key := nullif(
        lower(regexp_replace(btrim(coalesce(p_participant_key, '')), '\s+', '', 'g')),
        ''
    );

    if v_participant_key is not null and exists (
        select 1
          from public.activity_submissions
         where campaign_id = p_campaign_id
           and participant_key_normalized = v_participant_key
    ) then
        return query select 'participant_key_taken'::text, null::text;
        return;
    end if;

    select count(*)
      into v_winner_count
      from public.activity_submissions
     where campaign_id = p_campaign_id
       and activity_submissions.outcome = 'winner';

    if v_winner_count < v_campaign.winner_limit then
        select c.*
          into v_code
          from public.activity_codes c
         where c.campaign_id = p_campaign_id
           and c.claimed_by_submission_id is null
         order by position
         for update of c skip locked
         limit 1;
    end if;

    if v_code.id is not null then
        v_submission_id := gen_random_uuid();
        insert into public.activity_submissions (
            id,
            campaign_id,
            discord_user_id,
            discord_username,
            answers,
            participant_key_normalized,
            outcome,
            reward_code_id
        ) values (
            v_submission_id,
            p_campaign_id,
            p_discord_user_id,
            p_discord_username,
            coalesce(p_answers, '{}'::jsonb),
            v_participant_key,
            'winner',
            v_code.id
        );

        update public.activity_codes
           set claimed_by_submission_id = v_submission_id,
               claimed_at = now()
         where id = v_code.id;

        return query select 'winner'::text, v_code.code;
    else
        insert into public.activity_submissions (
            campaign_id,
            discord_user_id,
            discord_username,
            answers,
            participant_key_normalized,
            outcome
        ) values (
            p_campaign_id,
            p_discord_user_id,
            p_discord_username,
            coalesce(p_answers, '{}'::jsonb),
            v_participant_key,
            'sold_out'
        );

        return query select 'sold_out'::text, null::text;
    end if;
end;
$$;

revoke all on function public.claim_activity_reward(uuid, text, text, jsonb, text)
    from public, anon, authenticated;
grant execute on function public.claim_activity_reward(uuid, text, text, jsonb, text)
    to service_role;

insert into public.activity_campaigns (
    id,
    name,
    status,
    winner_limit,
    embed_title,
    embed_description,
    image_url,
    color,
    button_label,
    modal_title,
    winner_message,
    sold_out_message,
    closed_message
) values (
    'f0000000-0000-4000-8000-000000000001',
    'FP Favorite Game Reward - Draft',
    'draft',
    20,
    null,
    null,
    null,
    16750899,
    'Join Activity',
    'FP Player Survey',
    E'Congratulations! You’re one of our first participants.\nYour reward code: **{code}**',
    'Sorry, all reward codes have been claimed. Please keep following our server—more events are coming soon!',
    'This activity has ended. Please stay tuned for more events.'
)
on conflict (id) do nothing;

insert into public.activity_questions (
    id,
    campaign_id,
    field_key,
    position,
    label,
    input_style,
    required,
    placeholder,
    min_length,
    max_length,
    prefill_discord_username,
    is_participant_key
) values
(
    'f0000000-0000-4000-8000-000000000011',
    'f0000000-0000-4000-8000-000000000001',
    'discord_username',
    1,
    'Discord Username',
    'short',
    true,
    'Your Discord username',
    1,
    100,
    true,
    false
),
(
    'f0000000-0000-4000-8000-000000000012',
    'f0000000-0000-4000-8000-000000000001',
    'fp_id',
    2,
    'FortunePurple ID',
    'short',
    true,
    'Your FortunePurple ID',
    1,
    100,
    false,
    true
),
(
    'f0000000-0000-4000-8000-000000000013',
    'f0000000-0000-4000-8000-000000000001',
    'favorite_game',
    3,
    'Favorite FP Game',
    'short',
    true,
    'Which FortunePurple game is your favorite?',
    1,
    200,
    false,
    false
)
on conflict (id) do nothing;

commit;
