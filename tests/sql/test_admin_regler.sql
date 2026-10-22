-- KUN LOKAL TEST: administratorregler i databasen. Kører i en transaktion,
-- der rulles tilbage. Fejler med "FEJL: ..." hvis en regel ikke holder.
-- Køres af tools/lokal_testdatabase.py.
begin;

-- Udgangspunkt: ingen profiler (så bootstrap kan afprøves).
alter table public.user_profiles disable trigger user_profiles_keep_one_admin;
delete from public.user_profiles;
alter table public.user_profiles enable trigger user_profiles_keep_one_admin;

insert into auth.users (id, email) values
    ('00000000-0000-0000-0000-0000000000a1', 'foerste@test.invalid'),
    ('00000000-0000-0000-0000-0000000000a2', 'anden@test.invalid');

-- 1. Klienter (anon/authenticated) kan ikke kalde bootstrap.
set local role authenticated;
do $$ begin
    perform public.inbase_bootstrap_first_admin('foerste@test.invalid', 'x', 'x');
    raise exception 'FEJL: authenticated kan kalde bootstrap';
exception when insufficient_privilege then null;
end $$;
reset role;

-- 2. Første administrator kan oprettes én gang – og kun én gang.
select public.inbase_bootstrap_first_admin('Foerste@test.invalid', 'foerste', 'Første Admin');
do $$ begin
    if (select role from public.user_profiles where username = 'foerste') <> 'Administrator' then
        raise exception 'FEJL: første administrator ikke oprettet';
    end if;
    begin
        perform public.inbase_bootstrap_first_admin('anden@test.invalid', 'anden', 'Anden');
        raise exception 'FEJL: bootstrap tilladt, selvom der findes en administrator';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 3. Den sidste administrator kan hverken nedgraderes eller slettes.
do $$ begin
    begin
        update public.user_profiles set role = 'Bruger' where username = 'foerste';
        raise exception 'FEJL: sidste administrator kunne nedgraderes';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
    begin
        delete from auth.users where email = 'foerste@test.invalid';   -- cascade til profil
        raise exception 'FEJL: sidste administrators konto kunne slettes';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;

-- 4. Med to administratorer kan én nedgraderes – men ikke begge i ét hug.
insert into public.user_profiles (id, username, email, role)
values ('00000000-0000-0000-0000-0000000000a2', 'anden', 'anden@test.invalid', 'Administrator');
do $$ begin
    begin
        update public.user_profiles set role = 'Bruger' where role = 'Administrator';
        raise exception 'FEJL: alle administratorer kunne nedgraderes i én sætning';
    exception when others then
        if sqlerrm like 'FEJL:%' then raise; end if;
    end;
end $$;
update public.user_profiles set role = 'Bruger' where username = 'anden';

-- 5. En konto uden profil er ikke medlem og ser ingen sager.
set local role authenticated;
set local request.jwt.claims = '{"sub": "00000000-0000-0000-0000-0000000000a9"}';
do $$ begin
    if public.inbase_is_member() then
        raise exception 'FEJL: konto uden profil regnes som medlem';
    end if;
end $$;
reset role;

select 'Administratorregler: alle tjek bestået' as resultat;
rollback;
