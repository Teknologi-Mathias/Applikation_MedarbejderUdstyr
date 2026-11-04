-- IN-BASE 022: Kalender – alle ser alle (forenkling af 021)
--
-- Køres én gang i Supabase Dashboard → SQL Editor EFTER 021.
--
-- På et kontor med 13 personer er deling pr. person unødig administration:
--   * Alle med modulet 'kalender' ser alle kalendere med alle detaljer ('read').
--   * Kun ejeren ændrer sine kalendere og begivenheder; administratorer kan stadig
--     slette (moderation, inbase_calendar_can_moderate fra 021).
--   * Private begivenheder vises stadig som "Optaget" for alle andre end ejeren
--     (maskeringen i inbase_calendar_events fra 021 er uændret).
-- Delingen fra 021 bruges ikke længere: delingerne slettes, og RPC'erne til at dele
-- fjernes. Tabellen calendar_shares bliver stående (tom), så intet skal rulles tilbage.
--
-- Hver kalender får sin egen farve: kalendere, der deler farve med en ældre
-- kalender, får den første ledige farve fra paletten (samme som
-- app/domain/kalender.py FARVER).

create or replace function public.inbase_calendar_access(p_calendar_id uuid)
returns text language sql stable security definer set search_path = '' as $$
    select case
        when not public.inbase_has_module('kalender') then null
        when exists (select 1 from public.calendars
                     where id = p_calendar_id and owner_id = auth.uid()) then 'owner'
        when exists (select 1 from public.calendars where id = p_calendar_id) then 'read'
    end;
$$;

delete from public.calendar_shares;
drop function if exists public.inbase_calendar_share_set(uuid, text, text);
drop function if exists public.inbase_calendar_share_remove(uuid, text);

-- ---------- Én farve pr. kalender ---------------------------------------------

do $$
declare
    v_palet text[] := array[
        '#4F46E5', '#0EA5E9', '#10B981', '#F59E0B', '#EF4444', '#EC4899', '#8B5CF6', '#64748B',
        '#14B8A6', '#F97316', '#84CC16', '#06B6D4', '#D946EF', '#A16207', '#0F766E', '#BE123C'];
    v_brugt text[] := '{}';
    v_k     record;
    v_ny    text;
begin
    for v_k in select id, upper(color) as color from public.calendars order by created_at, id loop
        if v_k.color = any(v_brugt) then
            select f into v_ny from unnest(v_palet) f where f <> all(v_brugt) limit 1;
            if v_ny is not null then
                update public.calendars set color = v_ny where id = v_k.id;
                v_brugt := v_brugt || v_ny;
            end if;
        else
            v_brugt := v_brugt || v_k.color;
        end if;
    end loop;
end $$;

insert into public.schema_migrations (version, name) values (22, '022_kalender_alle_ser_alle')
on conflict (version) do nothing;
