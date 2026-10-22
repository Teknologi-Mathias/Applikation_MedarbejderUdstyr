-- IN-BASE 003: beskyttede databasefunktioner (kaldes via Supabase RPC)
--
-- Alle skrivninger af sager og arbejdsgangsskabeloner går gennem disse
-- funktioner. De kører som SECURITY DEFINER med tom search_path, tjekker selv
-- brugerens profil/rolle og er kun eksekverbare for de roller, der er nævnt.
--
-- Fejlkoder (oversættes i app/repositories/supabase/klient.py):
--   IB403  ingen adgang              -> DataFejl
--   IB409  versionskonflikt          -> KonfliktFejl
--   IB422  ugyldige data             -> ValideringsFejl

-- ---------- Interne hjælpere (ikke tilgængelige for klienten) --------------
--
-- Kolonnelisten udledes af tabellens egne kolonner ∩ nøglerne i JSON'en.
-- Derfor kræver et nyt felt kun "alter table ... add column" + én linje i
-- app/repositories/supabase/mapping.py – ikke en ny udgave af funktionerne.

create or replace function public.inbase_columns(p_table regclass, p_keys jsonb)
returns text language sql stable set search_path = '' as $$
    select string_agg(quote_ident(a.attname), ', ' order by a.attnum)
    from pg_catalog.pg_attribute a
    where a.attrelid = p_table and a.attnum > 0 and not a.attisdropped
      and p_keys ? a.attname::text;
$$;

create or replace function public.inbase_write_row(
    p_table regclass, p_fields jsonb, p_update_id uuid default null)
returns void language plpgsql set search_path = '' as $$
declare v_cols text := public.inbase_columns(p_table, p_fields);
begin
    if v_cols is null then
        return;
    end if;
    if p_update_id is null then
        execute format('insert into %s (%s) select %s from jsonb_populate_record(null::%s, $1)',
                       p_table, v_cols, v_cols, p_table) using p_fields;
    else
        execute format('update %s set (%s) = (select %s from jsonb_populate_record(null::%s, $1)) '
                       'where id = $2', p_table, v_cols, v_cols, p_table)
            using p_fields, p_update_id;
    end if;
end;
$$;

create or replace function public.inbase_insert_rows(p_table regclass, p_rows jsonb)
returns void language plpgsql set search_path = '' as $$
declare
    v_keys jsonb;
    v_cols text;
begin
    if p_rows is null or jsonb_array_length(p_rows) = 0 then
        return;
    end if;
    select jsonb_object_agg(k, true) into v_keys
    from (select distinct jsonb_object_keys(r) as k from jsonb_array_elements(p_rows) r) s;
    v_cols := public.inbase_columns(p_table, v_keys);
    execute format('insert into %s (%s) select %s from jsonb_populate_recordset(null::%s, $1)',
                   p_table, v_cols, v_cols, p_table) using p_rows;
end;
$$;

revoke execute on function public.inbase_columns(regclass, jsonb)          from public, anon, authenticated;
revoke execute on function public.inbase_write_row(regclass, jsonb, uuid)   from public, anon, authenticated;
revoke execute on function public.inbase_insert_rows(regclass, jsonb)      from public, anon, authenticated;

-- ---------- Gem en sag (atomisk, med optimistisk låsning) --------------------
--
-- p_case = {
--   "case":      {kolonner i lifecycle_cases},
--   "person":    {"id", "full_name", "email"},
--   "employment":{"payroll_number", "position_code", "area_name", datoer ...},
--   "tasks_upsert": [...], "tasks_delete": [id, ...], "tasks_replace": bool,
--   "reminders_upsert": [...], "reminders_delete": [...], "reminders_replace": bool,
--   "events": [hændelser; kun dem efter den gemte tidslinjes slutning indsættes]
-- }
-- p_expected_version = versionen sagen blev hentet med (0 = ny sag).
-- Kun den ene sag og dens egne rækker berøres.

create or replace function public.inbase_save_case(p_case jsonb, p_expected_version integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
    v_user      text := public.inbase_current_username();
    v_fields    jsonb := coalesce(p_case->'case', '{}'::jsonb);
    v_id        uuid := (v_fields->>'id')::uuid;
    v_process   text := v_fields->>'process';
    v_person    jsonb := coalesce(p_case->'person', '{}'::jsonb);
    v_person_id uuid := (v_person->>'id')::uuid;
    v_emp       jsonb := coalesce(p_case->'employment', '{}'::jsonb);
    v_old       public.lifecycle_cases%rowtype;
    v_found     boolean;
    v_emp_id    uuid;
    v_position  uuid;
    v_area      uuid;
    v_ids       uuid[];
    v_events    jsonb;
    v_max_seq   integer;
    v_count     integer;
    v_result    public.lifecycle_cases%rowtype;
begin
    if v_user is null then
        raise exception 'Du har ikke adgang til IN-BASE.' using errcode = 'IB403';
    end if;
    if v_id is null or v_person_id is null or v_process is null
       or v_process not in ('onboarding', 'offboarding') then
        raise exception 'Sagen mangler id, person eller proces.' using errcode = 'IB422';
    end if;

    -- 1. Lås sagen og tjek versionen.
    select * into v_old from public.lifecycle_cases where id = v_id for update;
    v_found := found;
    if v_found then
        if v_old.process <> v_process or v_old.person_id <> v_person_id then
            raise exception 'Sagens proces eller person kan ikke ændres.' using errcode = 'IB422';
        end if;
        if p_expected_version is distinct from v_old.version then
            raise exception '% er ændret af %, efter du åbnede sagen. Dine ændringer er ikke gemt – åbn sagen igen og gentag dem.',
                coalesce(nullif(v_fields->>'name', ''), 'Sagen'),
                coalesce(nullif(v_old.updated_by, ''), 'en anden')
                using errcode = 'IB409';
        end if;
    elsif coalesce(p_expected_version, 0) <> 0 then
        raise exception 'Sagen findes ikke længere – den er slettet af en anden.'
            using errcode = 'IB409';
    end if;

    -- 2. Person.
    if exists (select 1 from public.people where id = v_person_id) then
        perform public.inbase_write_row('public.people', v_person - 'id' - 'created_at' - 'updated_at',
                                        v_person_id);
    else
        perform public.inbase_write_row('public.people', v_person - 'created_at' - 'updated_at');
    end if;

    -- 3. Ansættelse (stilling og område slås op på kode/navn).
    if coalesce(v_emp->>'position_code', '') <> '' then
        select id into v_position from public.positions where code = v_emp->>'position_code';
        if v_position is null then
            raise exception 'Ukendt stilling: %', v_emp->>'position_code' using errcode = 'IB422';
        end if;
    end if;
    if coalesce(trim(v_emp->>'area_name'), '') <> '' then
        select id into v_area from public.areas where name = trim(v_emp->>'area_name');
        if v_area is null then
            -- Et område, der ikke (længere) er på listen: gem det som inaktivt.
            insert into public.areas (name, sort_order, active)
            values (trim(v_emp->>'area_name'), 1000, false)
            on conflict (name) do update set name = excluded.name
            returning id into v_area;
        end if;
    end if;
    v_emp := (v_emp - 'position_code' - 'area_name' - 'id' - 'created_at' - 'updated_at')
             || jsonb_build_object('person_id', v_person_id, 'position_id', v_position,
                                   'area_id', v_area);
    v_emp_id := case when v_found then v_old.employment_record_id end;
    if v_emp_id is null then
        v_emp_id := gen_random_uuid();
        perform public.inbase_write_row('public.employment_records',
                                        v_emp || jsonb_build_object('id', v_emp_id));
    else
        perform public.inbase_write_row('public.employment_records', v_emp, v_emp_id);
    end if;

    -- 4. Selve sagen (versionen tælles op af triggeren ved update).
    v_fields := v_fields - 'version' - 'updated_at' - 'updated_by' - 'created_by'
                - 'person_id' - 'employment_record_id';
    if v_fields ? 'template_id' then
        v_fields := jsonb_set(v_fields, '{template_id}', coalesce(to_jsonb(
            (select t.id from public.workflow_templates t
             where t.id = (v_fields->>'template_id')::uuid)), 'null'::jsonb));
    end if;
    v_fields := v_fields || jsonb_build_object('employment_record_id', v_emp_id,
                                               'updated_by', v_user);
    if v_found then
        perform public.inbase_write_row('public.lifecycle_cases',
                                        v_fields - 'id' - 'created_at', v_id);
    else
        perform public.inbase_write_row('public.lifecycle_cases',
            v_fields || jsonb_build_object('person_id', v_person_id, 'created_by', v_user,
                                           'version', 1));
    end if;

    -- 5. Opgaver: kun ændrede/nye/slettede (eller alle ved tasks_replace).
    v_ids := array(select (x->>'id')::uuid from jsonb_array_elements(
                       coalesce(p_case->'tasks_upsert', '[]'::jsonb)) x);
    if exists (select 1 from public.case_tasks where id = any(v_ids) and case_id <> v_id) then
        raise exception 'En opgave tilhører en anden sag.' using errcode = 'IB422';
    end if;
    delete from public.case_tasks
    where case_id = v_id
      and (coalesce((p_case->>'tasks_replace')::boolean, false)
           or id = any(v_ids)
           or id = any(array(select (x #>> '{}')::uuid from jsonb_array_elements(
                                 coalesce(p_case->'tasks_delete', '[]'::jsonb)) x)));
    perform public.inbase_insert_rows('public.case_tasks', (
        select coalesce(jsonb_agg(x || jsonb_build_object('case_id', v_id)), '[]'::jsonb)
        from jsonb_array_elements(coalesce(p_case->'tasks_upsert', '[]'::jsonb)) x));

    -- 6. Rykkere: samme princip.
    v_ids := array(select (x->>'id')::uuid from jsonb_array_elements(
                       coalesce(p_case->'reminders_upsert', '[]'::jsonb)) x);
    if exists (select 1 from public.case_reminders where id = any(v_ids) and case_id <> v_id) then
        raise exception 'En rykker tilhører en anden sag.' using errcode = 'IB422';
    end if;
    delete from public.case_reminders
    where case_id = v_id
      and (coalesce((p_case->>'reminders_replace')::boolean, false)
           or id = any(v_ids)
           or id = any(array(select (x #>> '{}')::uuid from jsonb_array_elements(
                                 coalesce(p_case->'reminders_delete', '[]'::jsonb)) x)));
    perform public.inbase_insert_rows('public.case_reminders', (
        select coalesce(jsonb_agg(x || jsonb_build_object('case_id', v_id)), '[]'::jsonb)
        from jsonb_array_elements(coalesce(p_case->'reminders_upsert', '[]'::jsonb)) x));

    -- 7. Tidslinje: kun nye hændelser (insert-only), og kun i eget navn.
    select coalesce(max(sequence), -1) into v_max_seq
    from public.audit_events where case_id = v_id;
    select coalesce(jsonb_agg(e || jsonb_build_object('case_id', v_id,
                                                      'recorded_by', auth.uid())
                              order by (e->>'sequence')::int), '[]'::jsonb)
    into v_events
    from jsonb_array_elements(coalesce(p_case->'events', '[]'::jsonb)) e
    where (e->>'sequence')::int > v_max_seq;
    if exists (select 1 from jsonb_array_elements(v_events) e where e->>'actor' is distinct from v_user) then
        raise exception 'Hændelser i tidslinjen kan kun registreres i eget navn.'
            using errcode = 'IB403';
    end if;
    perform public.inbase_insert_rows('public.audit_events', v_events);
    select count(*), coalesce(max(sequence), -1) into v_count, v_max_seq
    from public.audit_events where case_id = v_id;
    if v_count <> v_max_seq + 1 then
        raise exception 'Tidslinjen er ude af trit med databasen. Åbn sagen igen.'
            using errcode = 'IB409';
    end if;

    select * into v_result from public.lifecycle_cases where id = v_id;
    return jsonb_build_object('version', v_result.version, 'updated_at', v_result.updated_at,
                              'created_at', v_result.created_at);
end;
$$;

-- ---------- Slet en sag permanent (kun administratorer) ----------------------
-- Sletter også personen og ansættelsen, hvis ingen anden sag bruger dem
-- (slettepolitik for persondata). Tidslinjen slettes med sagen (cascade).

create or replace function public.inbase_delete_case(p_case_id uuid, p_expected_version integer)
returns void language plpgsql security definer set search_path = '' as $$
declare v_case public.lifecycle_cases%rowtype;
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan slette sager permanent.' using errcode = 'IB403';
    end if;
    select * into v_case from public.lifecycle_cases where id = p_case_id for update;
    if not found then
        return;   -- allerede slettet
    end if;
    if v_case.version <> p_expected_version then
        raise exception 'Sagen er ændret af %, efter du åbnede den. Den er ikke slettet.',
            coalesce(nullif(v_case.updated_by, ''), 'en anden') using errcode = 'IB409';
    end if;
    delete from public.lifecycle_cases where id = p_case_id;
    delete from public.employment_records e
    where e.id = v_case.employment_record_id
      and not exists (select 1 from public.lifecycle_cases c where c.employment_record_id = e.id);
    delete from public.people p
    where p.id = v_case.person_id
      and not exists (select 1 from public.lifecycle_cases c where c.person_id = p.id);
end;
$$;

-- ---------- Gem en arbejdsgangsskabelon (kun administratorer) ---------------
-- p_template = {kolonner i workflow_templates, "tasks": [...], "versions": [{version, snapshot}]}

create or replace function public.inbase_save_workflow_template(p_template jsonb)
returns void language plpgsql security definer set search_path = '' as $$
declare
    v_id     uuid := (p_template->>'id')::uuid;
    v_fields jsonb;
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan ændre skabeloner.' using errcode = 'IB403';
    end if;
    if v_id is null then
        raise exception 'Skabelonen mangler id.' using errcode = 'IB422';
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

-- ---------- Brugere --------------------------------------------------------

-- Navne til "Ansvarlig"-listen: kun brugernavn og visningsnavn – ikke e-mail
-- eller rolle – for alle medlemmer.
create or replace function public.inbase_user_directory()
returns table (username text, display_name text)
language sql stable security definer set search_path = '' as $$
    select p.username, p.display_name from public.user_profiles p
    where public.inbase_is_member()
    order by lower(p.username);
$$;

-- Kaldes af klienten efter et vellykket skift af egen adgangskode.
create or replace function public.inbase_password_changed()
returns void language sql security definer set search_path = '' as $$
    update public.user_profiles set must_change_password = false where id = auth.uid();
$$;

-- Bruges af Edge Function admin-create-user til at genoptage en oprettelse,
-- der stoppede efter Auth-kontoen men før profilen. Kun service_role.
create or replace function public.inbase_auth_user_id_by_email(p_email text)
returns uuid language sql stable security definer set search_path = '' as $$
    select id from auth.users where lower(email) = lower(trim(p_email)) limit 1;
$$;

-- ENGANGSPROCEDURE: den allerførste administrator. Køres af projektejeren i
-- SQL Editor (som postgres) – kan IKKE kaldes fra programmet eller API'et.
-- Afvises, hvis der allerede findes en administrator.
create or replace function public.inbase_bootstrap_first_admin(
    p_email text, p_username text, p_display_name text default '')
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_uid uuid;
begin
    if exists (select 1 from public.user_profiles where role = 'Administrator') then
        raise exception 'Der findes allerede en administrator. Opret nye brugere fra IN-BASE.';
    end if;
    select id into v_uid from auth.users where lower(email) = lower(trim(p_email));
    if v_uid is null then
        raise exception 'Der findes ingen Auth-bruger med e-mailen %. Opret den først under Authentication → Users.', p_email;
    end if;
    insert into public.user_profiles (id, username, display_name, email, role, must_change_password)
    values (v_uid, trim(p_username), coalesce(nullif(trim(p_display_name), ''), trim(p_username)),
            lower(trim(p_email)), 'Administrator', false)
    on conflict (id) do update
        set role = 'Administrator', username = excluded.username,
            display_name = excluded.display_name, email = excluded.email;
    return v_uid;
end;
$$;

-- ---------- Hvem må kalde hvad ---------------------------------------------

revoke execute on function public.inbase_save_case(jsonb, integer)          from public, anon;
revoke execute on function public.inbase_delete_case(uuid, integer)        from public, anon;
revoke execute on function public.inbase_save_workflow_template(jsonb)     from public, anon;
revoke execute on function public.inbase_user_directory()                  from public, anon;
revoke execute on function public.inbase_password_changed()                from public, anon;
revoke execute on function public.inbase_auth_user_id_by_email(text)       from public, anon, authenticated;
revoke execute on function public.inbase_bootstrap_first_admin(text, text, text)
    from public, anon, authenticated, service_role;

grant execute on function public.inbase_save_case(jsonb, integer)      to authenticated;
grant execute on function public.inbase_delete_case(uuid, integer)    to authenticated;
grant execute on function public.inbase_save_workflow_template(jsonb) to authenticated;
grant execute on function public.inbase_user_directory()              to authenticated;
grant execute on function public.inbase_password_changed()            to authenticated;
grant execute on function public.inbase_auth_user_id_by_email(text)   to service_role;
