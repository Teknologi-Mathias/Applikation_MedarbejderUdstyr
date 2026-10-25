-- KUN TIL LOKAL TEST (køres EFTER migreringerne i den midlertidige container).
-- Spiller Edge Function admin-create-user's rolle: opretter en Auth-konto og
-- evt. en profil. Kun service_role må kalde den. ALDRIG i Supabase.

create or replace function public.test_opret_konto(
    p_email text, p_username text default null, p_role text default 'Bruger')
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid := gen_random_uuid();
begin
    insert into auth.users (id, email) values (v_id, p_email);
    if p_username is not null then
        insert into public.user_profiles (id, username, display_name, email, role,
                                          must_change_password)
        values (v_id, p_username, initcap(p_username), p_email, p_role, false);
    end if;
    return v_id;
end;
$$;
revoke execute on function public.test_opret_konto(text, text, text) from public, anon, authenticated;
grant execute on function public.test_opret_konto(text, text, text) to service_role;

-- Sletter en Auth-konto (som Edge Function admin-manage-user ville gøre).
create or replace function public.test_slet_konto(p_id uuid)
returns void language sql security definer set search_path = '' as $$
    delete from auth.users where id = p_id;
$$;
revoke execute on function public.test_slet_konto(uuid) from public, anon, authenticated;
grant execute on function public.test_slet_konto(uuid) to service_role;
