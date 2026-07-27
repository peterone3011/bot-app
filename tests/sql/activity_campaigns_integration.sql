\set ON_ERROR_STOP on

begin;

do $$
declare
    v_campaign_id uuid := gen_random_uuid();
    v_outcome text;
    v_code text;
    v_existing_message_id text;
    v_index integer;
    v_role text;
    v_table text;
    v_privilege text;
    v_function text;
    v_question_count integer;
    v_revision bigint;
begin
    foreach v_role in array array['anon', 'authenticated'] loop
        foreach v_table in array array[
            'public.activity_campaigns',
            'public.activity_questions',
            'public.activity_codes',
            'public.activity_submissions'
        ] loop
            foreach v_privilege in array array[
                'select', 'insert', 'update', 'delete',
                'truncate', 'references', 'trigger'
            ] loop
                if has_table_privilege(v_role, v_table, v_privilege) then
                    raise exception 'client role % unexpectedly has % on %',
                        v_role, v_privilege, v_table;
                end if;
            end loop;
        end loop;
    end loop;
    if not has_table_privilege(
        'service_role', 'public.activity_codes', 'select'
    ) then
        raise exception 'service_role must read reward codes';
    end if;
    foreach v_role in array array['anon', 'authenticated'] loop
        foreach v_function in array array[
            'public.claim_activity_reward(uuid,text,text,jsonb,text)',
            'public.save_activity_draft(uuid,jsonb,jsonb)',
            'public.replace_activity_codes(uuid,text[])',
            'public.activate_activity_campaign(uuid,bigint,text,text)'
        ] loop
            if has_function_privilege(v_role, v_function, 'execute') then
                raise exception 'client roles must not execute activity RPCs';
            end if;
        end loop;
    end loop;
    if not has_function_privilege(
        'service_role',
        'public.claim_activity_reward(uuid,text,text,jsonb,text)',
        'execute'
    ) then
        raise exception 'service_role must execute the claim RPC';
    end if;
    if not has_function_privilege(
        'service_role',
        'public.save_activity_draft(uuid,jsonb,jsonb)',
        'execute'
    ) or not has_function_privilege(
        'service_role',
        'public.replace_activity_codes(uuid,text[])',
        'execute'
    ) or not has_function_privilege(
        'service_role',
        'public.activate_activity_campaign(uuid,bigint,text,text)',
        'execute'
    ) then
        raise exception 'service_role must execute dashboard activity RPCs';
    end if;
    if exists (
        select 1
          from pg_class
         where oid in (
             'public.activity_campaigns'::regclass,
             'public.activity_questions'::regclass,
             'public.activity_codes'::regclass,
             'public.activity_submissions'::regclass
         )
           and not relrowsecurity
    ) then
        raise exception 'RLS must be enabled on every activity table';
    end if;

    insert into public.activity_campaigns (
        id,
        name,
        winner_limit,
        discord_channel_id,
        winner_message,
        sold_out_message,
        closed_message
    ) values (
        v_campaign_id,
        'Activity integration test',
        20,
        '2',
        'Winner {code}',
        'Sold out',
        'Closed'
    );

    perform public.save_activity_draft(
        v_campaign_id,
        jsonb_build_object(
            'name', 'Activity integration test saved',
            'winner_limit', 20,
            'discord_channel_id', '2',
            'button_label', 'Join',
            'modal_title', 'Test activity',
            'winner_message', 'Winner {code}',
            'sold_out_message', 'Sold out',
            'closed_message', 'Closed'
        ),
        jsonb_build_array(
            jsonb_build_object(
                'field_key', 'fp_id',
                'label', 'FortunePurple ID',
                'input_style', 'short',
                'required', true,
                'min_length', 1,
                'max_length', 100,
                'is_participant_key', true
            )
        )
    );

    begin
        perform public.save_activity_draft(
            v_campaign_id, '{}'::jsonb, null
        );
        raise exception 'expected invalid_questions for null input';
    exception
        when others then
            if sqlerrm not like '%invalid_questions%' then
                raise;
            end if;
    end;
    select count(*)
      into v_question_count
      from public.activity_questions
     where campaign_id = v_campaign_id;
    if v_question_count <> 1 then
        raise exception 'null question input changed the saved questions';
    end if;

    perform public.replace_activity_codes(
        v_campaign_id,
        array(
            select 'ORDERED-' || item
              from generate_series(1, 20) as item
        )
    );

    select revision
      into v_revision
      from public.activity_campaigns
     where id = v_campaign_id;
    select result.outcome, result.existing_message_id
      into v_outcome, v_existing_message_id
      from public.activate_activity_campaign(
          v_campaign_id, v_revision + 1, '1', 'stale-message'
      ) result;
    if v_outcome <> 'stale_draft' then
        raise exception 'stale draft activation was not rejected: %', v_outcome;
    end if;

    select result.outcome, result.existing_message_id
      into v_outcome, v_existing_message_id
      from public.activate_activity_campaign(
          v_campaign_id, v_revision, '1', '3'
      ) result;
    if v_outcome <> 'activated' or v_existing_message_id <> '3' then
        raise exception 'activity activation failed: %, %',
            v_outcome, v_existing_message_id;
    end if;

    begin
        perform public.replace_activity_codes(
            v_campaign_id, array['MUST-NOT-REPLACE']
        );
        raise exception 'expected activity_locked after activation';
    exception
        when others then
            if sqlerrm not like '%activity_locked%' then
                raise;
            end if;
    end;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1001', 'first', '{"fp_id":"Alpha"}', ' Alpha '
      ) r;
    if v_outcome <> 'winner' or v_code <> 'ORDERED-1' then
        raise exception 'first ordered claim failed: %, %', v_outcome, v_code;
    end if;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1001', 'first-again', '{"fp_id":"Changed"}', 'Changed'
      ) r;
    if v_outcome <> 'existing_winner' or v_code <> 'ORDERED-1' then
        raise exception 'duplicate winner recovery failed: %, %', v_outcome, v_code;
    end if;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1002', 'conflict', '{"fp_id":"alpha"}', 'a l p h a'
      ) r;
    if v_outcome <> 'participant_key_taken' or v_code is not null then
        raise exception 'participant key conflict failed: %, %', v_outcome, v_code;
    end if;

    for v_index in 2..20 loop
        select r.outcome, r.reward_code
          into v_outcome, v_code
          from public.claim_activity_reward(
              v_campaign_id,
              (1000 + v_index)::text,
              'player-' || v_index,
              jsonb_build_object('fp_id', 'Player-' || v_index),
              'Player-' || v_index
          ) r;
        if v_outcome <> 'winner' or v_code <> ('ORDERED-' || v_index) then
            raise exception 'ordered claim % failed: %, %', v_index, v_outcome, v_code;
        end if;
    end loop;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1021', 'late', '{"fp_id":"Gamma"}', 'Gamma'
      ) r;
    if v_outcome <> 'sold_out' or v_code is not null then
        raise exception 'sold-out claim failed: %, %', v_outcome, v_code;
    end if;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1021', 'late-again', '{"fp_id":"Gamma"}', 'Gamma'
      ) r;
    if v_outcome <> 'existing_sold_out' or v_code is not null then
        raise exception 'duplicate sold-out recovery failed: %, %', v_outcome, v_code;
    end if;

    update public.activity_campaigns
       set status = 'closed', closed_at = now()
     where id = v_campaign_id;

    select r.outcome, r.reward_code
      into v_outcome, v_code
      from public.claim_activity_reward(
          v_campaign_id, '1005', 'closed', '{"fp_id":"Delta"}', 'Delta'
      ) r;
    if v_outcome <> 'closed' or v_code is not null then
        raise exception 'closed outcome failed: %, %', v_outcome, v_code;
    end if;
end;
$$;

rollback;
