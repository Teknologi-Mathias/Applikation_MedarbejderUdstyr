-- KUN TIL LOKAL TEST (køres EFTER migreringerne i den midlertidige container).
-- Spiller Edge Functions' rolle (admin-create-user / admin-manage-user):
-- opretter en Auth-konto med login-aliasset og evt. en profil, (de)aktiverer
-- og sletter. Kun service_role må kalde dem. ALDRIG i Supabase.

create or replace function public.test_opret_konto(
    p_username text, p_role text default 'Bruger', p_profil boolean default true)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid := gen_random_uuid();
begin
    insert into auth.users (id, email, email_confirmed_at)
    values (v_id, public.inbase_login_alias(p_username), now());
    if p_profil then
        insert into public.user_profiles (id, username, display_name, role, must_change_password)
        values (v_id, upper(trim(p_username)), initcap(p_username), p_role, false);
    end if;
    return v_id;
end;
$$;
revoke execute on function public.test_opret_konto(text, text, boolean) from public, anon, authenticated;
grant execute on function public.test_opret_konto(text, text, boolean) to service_role;

-- (De)aktiverer en profil (som Edge Function admin-manage-user, action set_active).
create or replace function public.test_saet_aktiv(p_id uuid, p_active boolean)
returns void language sql security definer set search_path = '' as $$
    update public.user_profiles set active = p_active where id = p_id;
$$;
revoke execute on function public.test_saet_aktiv(uuid, boolean) from public, anon, authenticated;
grant execute on function public.test_saet_aktiv(uuid, boolean) to service_role;

-- Sletter en Auth-konto (som Edge Function admin-manage-user ville gøre).
create or replace function public.test_slet_konto(p_id uuid)
returns void language sql security definer set search_path = '' as $$
    delete from auth.users where id = p_id;
$$;
revoke execute on function public.test_slet_konto(uuid) from public, anon, authenticated;
grant execute on function public.test_slet_konto(uuid) to service_role;
