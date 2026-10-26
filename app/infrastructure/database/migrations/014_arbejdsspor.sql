-- IN-BASE 014: Parallelle arbejdsspor, HR's behov og afdelinger (roller)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 013.
-- Kun tilføjelser: ingen data slettes eller ændres.
--
-- * Opgaver (case_tasks) og skabelonopgaver (workflow_template_tasks) får
--   arbejdsspor: fast nøgle, spor, ansvarlig afdeling, forudsætninger (andre
--   opgavers nøgler) og betingelse (behov). Sagsopgaver får også et planlagt
--   tidspunkt (fx oplæringsvagt) – adskilt fra opgavens status.
-- * lifecycle_cases.needs: HR's behovsregistrering (tøj, mobil, mail, bil).
--   Valideres i app/domain/behov.py; her sikres kun, at det er et JSON-objekt.
-- * user_profiles.roles: de afdelinger, brugeren er medlem af (flere mulige).
--   Bruges til arbejdsbakkerne ("Min afdeling"). Alle medlemmer må fortsat
--   behandle alle sager; Administrator (kolonnen role) er uændret.
--   Afdelingsnavnene svarer til app/domain/arbejdsspor.py (AFDELINGER).
--
-- inbase_save_case og inbase_save_workflow_template udleder selv kolonnerne
-- (003), så de nye felter gemmes uden nye udgaver af funktionerne.

-- ---------- Opgaver ----------------------------------------------------------

alter table public.case_tasks
    add column if not exists task_key   text not null default '',
    add column if not exists track      text not null default '',
    add column if not exists department text not null default '',
    add column if not exists depends_on text[] not null default '{}',
    add column if not exists condition  text not null default '',
    add column if not exists planned_at timestamptz;

alter table public.workflow_template_tasks
    add column if not exists task_key   text not null default '',
    add column if not exists track      text not null default '',
    add column if not exists department text not null default '',
    add column if not exists depends_on text[] not null default '{}',
    add column if not exists condition  text not null default '';

-- ---------- HR's behov ---------------------------------------------------------

alter table public.lifecycle_cases
    add column if not exists needs jsonb not null default '{}'::jsonb;
alter table public.lifecycle_cases drop constraint if exists lifecycle_cases_needs_object;
alter table public.lifecycle_cases add constraint lifecycle_cases_needs_object
    check (jsonb_typeof(needs) = 'object');

-- ---------- Afdelinger (roller) pr. bruger ------------------------------------

alter table public.user_profiles
    add column if not exists roles text[] not null default '{}';
alter table public.user_profiles drop constraint if exists user_profiles_roles_check;
alter table public.user_profiles add constraint user_profiles_roles_check
    check (roles <@ array['HR', 'Administration', 'Merch']::text[]);

-- Kun administratorer sætter afdelinger (brugere kan stadig kun selv ændre
-- tema og notifikationer, 002). Dubletter fjernes; rækkefølgen er fast.
create or replace function public.inbase_set_roles(p_user_id uuid, p_roles text[])
returns void language plpgsql security definer set search_path = '' as $$
declare v_roles text[];
begin
    if not public.inbase_is_admin() then
        raise exception 'Kun administratorer kan ændre afdelinger.' using errcode = 'IB403';
    end if;
    if not coalesce(p_roles, '{}') <@ array['HR', 'Administration', 'Merch'] then
        raise exception 'Ukendt afdeling.' using errcode = 'IB422';
    end if;
    v_roles := array(select r from unnest(array['HR', 'Administration', 'Merch']) r
                     where r = any(coalesce(p_roles, '{}')));
    update public.user_profiles set roles = v_roles where id = p_user_id;
    if not found then
        raise exception 'Brugeren findes ikke længere.' using errcode = 'IB409';
    end if;
end;
$$;
revoke execute on function public.inbase_set_roles(uuid, text[]) from public, anon;
grant execute on function public.inbase_set_roles(uuid, text[]) to authenticated;

-- Brugerlisten ("Ansvarlig") viser nu også afdelingerne, så en opgave kan
-- tildeles et medlem af den ansvarlige afdeling.
drop function if exists public.inbase_user_directory();
create function public.inbase_user_directory()
returns table (username text, display_name text, roles text[])
language sql stable security definer set search_path = '' as $$
    select p.username, p.display_name, p.roles from public.user_profiles p
    where public.inbase_is_member() and p.active
    order by lower(p.username);
$$;
revoke execute on function public.inbase_user_directory() from public, anon;
grant execute on function public.inbase_user_directory() to authenticated;
