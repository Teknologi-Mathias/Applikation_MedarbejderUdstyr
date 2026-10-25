-- KUN LOKAL TEST: brugernavnslogin og administratorregler i databasen. Kører
-- i en transaktion, der rulles tilbage. Fejler med "FEJL: ..." hvis en regel
-- ikke holder. Køres af tools/lokal_testdatabase.py (efter alle migreringer).
begin;

-- 0. Migrering 005 har flyttet den gamle e-mail-konto (foer_005_gammel_konto.sql).
do $$ begin
    if (select username from public.user_profiles
        where id = '00000000-0000-0000-0000-0000000000b1') <> 'GAMMEL.ADMIN' then
        raise exception 'FEJL: brugernavnet er ikke normaliseret af 005';
    end if;
    if (select email from auth.users where id = '00000000-0000-0000-0000-0000000000b1')
       <> 'gammel.admin@brugere.in-base.invalid' then
        raise exception 'FEJL: kontoen er ikke flyttet til login-aliasset';
    end if;
    if (select identity_data->>'email' from auth.identities
        where user_id = '00000000-0000-0000-0000-0000000000b1')
       <> 'gammel.admin@brugere.in-base.invalid' then
        raise exception 'FEJL: identiteten er ikke flyttet til login-aliasset';
    end if;
    if exists (select 1 from information_schema.columns where table_schema = 'public'
               and table_name = 'user_profiles' and column_name = 'email') then
        raise exception 'FEJL: user_profiles har stadig en e-mail-kolonne';
    end if;
end $$;

-- Udgangspunkt: ingen profiler (så bootstrap kan afprøves).
alter table public.user_profiles disable trigger user_profiles_keep_one_admin;
delete from public.user_profiles;
alter table public.user_profiles enable trigger user_profiles_keep_one_admin;

insert into auth.users (id, email) values
    ('00000000-0000-0000-0000-0000000000a1', 'foerste@brugere.in-base.invalid'),
    ('00000000-0000-0000-0000-0000000000a2', 'anden@brugere.in-base.invalid'),
    ('00000000-0000-0000-0000-0000000000a3', 'tredje@brugere.in-base.invalid');

-- 1. Klienter (anon/authenticated) kan ikke kalde bootstrap.
set local role authenticated;
do $$ begin
    perform public.inbase_bootstrap_first_admin('foerste', 'x');
    raise exception 'FEJL: authenticated kan kalde bootstrap';
exception when insufficient_privilege then null;
end $$;
reset role;

-- 2. Bootstrap kræver en Auth-bruger med login-aliasset.
do $$ begin
    begin
        perform public.inbase_bootstrap_first_admin('ukendt', 'x');
        raise exception 'FEJL: bootstrap uden Auth-bruger tilladt';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 3. Første administrator kan oprettes én gang – og kun én gang. Brugernavnet normaliseres.
select public.inbase_bootstrap_first_admin(' Foerste ', 'Første Admin');
do $$ begin
    if (select role from public.user_profiles where username = 'FOERSTE') <> 'Administrator' then
        raise exception 'FEJL: første administrator ikke oprettet med normaliseret brugernavn';
    end if;
    begin
        perform public.inbase_bootstrap_first_admin('anden', 'Anden');
        raise exception 'FEJL: bootstrap tilladt, selvom der findes en administrator';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 4. Den sidste aktive administrator kan hverken nedgraderes, deaktiveres eller slettes.
do $$ begin
    begin
        update public.user_profiles set role = 'Bruger' where username = 'FOERSTE';
        raise exception 'FEJL: sidste administrator kunne nedgraderes';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
    begin
        update public.user_profiles set active = false where username = 'FOERSTE';
        raise exception 'FEJL: sidste administrator kunne deaktiveres';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
    begin
        delete from auth.users where email = 'foerste@brugere.in-base.invalid';   -- cascade til profil
        raise exception 'FEJL: sidste administrators konto kunne slettes';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 5. Med to administratorer kan én nedgraderes/deaktiveres – men ikke begge i ét hug.
insert into public.user_profiles (id, username, role)
values ('00000000-0000-0000-0000-0000000000a2', 'ANDEN', 'Administrator');
do $$ begin
    begin
        update public.user_profiles set role = 'Bruger' where role = 'Administrator';
        raise exception 'FEJL: alle administratorer kunne nedgraderes i én sætning';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;
update public.user_profiles set active = false where username = 'ANDEN';
do $$ begin
    begin
        update public.user_profiles set role = 'Bruger' where username = 'FOERSTE';
        raise exception 'FEJL: en deaktiveret administrator tæller som aktiv administrator';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 6. Brugernavne skal være normaliserede og gyldige – og unikke uanset store/små bogstaver.
do $$ begin
    begin
        insert into public.user_profiles (id, username)
        values ('00000000-0000-0000-0000-0000000000a3', 'smaa');
        raise exception 'FEJL: brugernavn med små bogstaver tilladt';
    exception when check_violation then null;
    end;
    begin
        insert into public.user_profiles (id, username)
        values ('00000000-0000-0000-0000-0000000000a3', 'A..B');
        raise exception 'FEJL: brugernavn med to punktummer tilladt';
    exception when check_violation then null;
    end;
    begin
        insert into public.user_profiles (id, username)
        values ('00000000-0000-0000-0000-0000000000a3', 'ANDEN');
        raise exception 'FEJL: dubleret brugernavn tilladt';
    exception when unique_violation then null;
    end;
end $$;

-- 7. En konto uden profil og en deaktiveret konto er ikke medlemmer.
set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-0000000000a9"}';
do $$ begin
    if public.inbase_is_member() then
        raise exception 'FEJL: konto uden profil regnes som medlem';
    end if;
end $$;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-0000000000a2"}';
do $$ begin
    if public.inbase_is_member() or public.inbase_is_admin()
       or public.inbase_current_username() is not null then
        raise exception 'FEJL: deaktiveret administrator har stadig adgang';
    end if;
end $$;
reset role;

select 'Administratorregler: alle tjek bestået' as resultat;
rollback;
