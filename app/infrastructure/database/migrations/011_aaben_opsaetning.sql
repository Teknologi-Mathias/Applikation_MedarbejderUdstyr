-- IN-BASE 011: Alle brugere ændrer skabeloner og organisation
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 010.
--
-- Før kunne kun administratorer ændre opsætning (002/003). Nu kan alle
-- medlemmer ændre:
--   * arbejdsgangsskabeloner – dog kun for moduler, de har adgang til (010),
--   * mailskabeloner, påmindelsesregler og områder,
--   * Organisation i app_settings (ansvarlige, stillestaaende_dage, naermer_sig_dage).
--
-- Stadig kun administratorer: brugere og roller, moduladgang, backup og
-- slettepolitik (app_settings opbevaring_maaneder, backup_antal, backup_mappe)
-- samt permanent sletning.

-- ---------- Mailskabeloner, påmindelser og områder: alle medlemmer ----------

do $$
declare t text;
begin
    foreach t in array array['areas', 'message_templates', 'notification_rules']
    loop
        execute format('drop policy if exists %I on public.%I', t || '_admin_insert', t);
        execute format('drop policy if exists %I on public.%I', t || '_admin_update', t);
        execute format('create policy %I on public.%I for insert to authenticated '
                       'with check ((select public.inbase_is_member()))', t || '_member_insert', t);
        execute format('create policy %I on public.%I for update to authenticated '
                       'using ((select public.inbase_is_member())) '
                       'with check ((select public.inbase_is_member()))', t || '_member_update', t);
    end loop;
end $$;

-- ---------- app_settings: Organisation for alle, resten for administratorer --
-- Administratorpolitikkerne fra 002 bevares; politikkerne lægges sammen (OR).

drop policy if exists app_settings_member_insert on public.app_settings;
drop policy if exists app_settings_member_update on public.app_settings;
create policy app_settings_member_insert on public.app_settings for insert to authenticated
    with check ((select public.inbase_is_member())
                and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage'));
create policy app_settings_member_update on public.app_settings for update to authenticated
    using ((select public.inbase_is_member())
           and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage'))
    with check ((select public.inbase_is_member())
                and key in ('ansvarlige', 'stillestaaende_dage', 'naermer_sig_dage'));

-- ---------- Arbejdsgangsskabeloner: medlemmer med modulet --------------------

create or replace function public.inbase_save_workflow_template(p_template jsonb)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_id     uuid := (p_template->>'id')::uuid;
    v_fields jsonb;
begin
    if v_id is null then
        raise exception 'Skabelonen mangler id.' using errcode = 'IB422';
    end if;
    -- Både den nye og (ved ændring) den gemte proces skal være et af brugerens moduler.
    if not public.inbase_is_member()
       or not public.inbase_has_module(p_template->>'process')
       or exists (select 1 from public.workflow_templates
                  where id = v_id and not public.inbase_has_module(process)) then
        raise exception 'Du har ikke adgang til at ændre skabeloner i dette modul.'
            using errcode = 'IB403';
    end if;
    v_fields := (p_template - 'tasks' - 'versions' - 'updated_at' - 'updated_by')
                || jsonb_build_object('updated_by', public.inbase_current_username(),
                                      'updated_at', now());
    if exists (select 1 from public.workflow_templates where id = v_id) then
        perform public.inbase_write_row('public.workflow_templates', v_fields - 'id', v_id);
    else
        perform public.inbase_write_row('public.workflow_templates', v_fields);
    end if;

    delete from public.workflow_template_tasks where template_id = v_id;
    perform public.inbase_insert_rows('public.workflow_template_tasks', (
        select coalesce(jsonb_agg((x - 'id') || jsonb_build_object('template_id', v_id,
                                                                    'sort_order', n - 1)
                                  order by n), '[]'::jsonb)
        from jsonb_array_elements(coalesce(p_template->'tasks', '[]'::jsonb))
             with ordinality as t(x, n)));

    delete from public.workflow_template_versions
    where template_id = v_id
      and version not in (select (v->>'version')::int from jsonb_array_elements(
                              coalesce(p_template->'versions', '[]'::jsonb)) v);
    insert into public.workflow_template_versions (template_id, version, snapshot)
    select v_id, (v->>'version')::int, v->'snapshot'
    from jsonb_array_elements(coalesce(p_template->'versions', '[]'::jsonb)) v
    on conflict (template_id, version) do nothing;
end;
$$;
