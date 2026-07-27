alter table public.activity_campaigns
    add column if not exists ends_at timestamptz;

update public.activity_campaigns
   set status = 'closed',
       closed_at = coalesce(closed_at, now())
 where status = 'active'
   and ends_at is null;

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
           ends_at = case when p_campaign ? 'ends_at'
                          then nullif(p_campaign ->> 'ends_at', '')::timestamptz
                          else ends_at end,
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
    if v_campaign.ends_at is null or v_campaign.ends_at <= now() then
        return query select 'invalid_end_time'::text, null::text;
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

    if not found
       or v_campaign.status <> 'active'
       or v_campaign.ends_at is null
       or v_campaign.ends_at <= now() then
        return query select 'closed'::text, null::text;
        return;
    end if;

    select *
      into v_existing
      from public.activity_submissions
     where campaign_id = p_campaign_id
       and discord_user_id = p_discord_user_id;

    v_participant_key := nullif(
        lower(regexp_replace(btrim(coalesce(p_participant_key, '')), '\s+', '', 'g')),
        ''
    );

    if v_participant_key is not null and exists (
        select 1
          from public.activity_submissions s
         where s.campaign_id = p_campaign_id
           and s.participant_key_normalized = v_participant_key
           and (v_existing.id is null or s.id <> v_existing.id)
    ) then
        return query select 'participant_key_taken'::text, null::text;
        return;
    end if;

    if v_existing.id is not null then
        update public.activity_submissions
           set discord_username = p_discord_username,
               answers = coalesce(p_answers, '{}'::jsonb),
               participant_key_normalized = v_participant_key
         where id = v_existing.id;

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

revoke all on function public.save_activity_draft(uuid, jsonb, jsonb)
    from public, anon, authenticated;
revoke all on function public.activate_activity_campaign(uuid, bigint, text, text)
    from public, anon, authenticated;
revoke all on function public.claim_activity_reward(uuid, text, text, jsonb, text)
    from public, anon, authenticated;
grant execute on function public.save_activity_draft(uuid, jsonb, jsonb)
    to service_role;
grant execute on function public.activate_activity_campaign(uuid, bigint, text, text)
    to service_role;
grant execute on function public.claim_activity_reward(uuid, text, text, jsonb, text)
    to service_role;
