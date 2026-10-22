-- KUN TIL LOKAL TEST: efterligner de dele af Supabase, som IN-BASE-migreringerne
-- bruger (roller, auth.users, auth.uid() og Supabases standardprivilegier).
-- Køres i en tom, midlertidig PostgreSQL-container – ALDRIG i Supabase.

create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
grant anon, authenticated, service_role to postgres;

create schema auth;
grant usage on schema auth to anon, authenticated, service_role;

create table auth.users (
    id     uuid primary key default gen_random_uuid(),
    email  text unique
);

create function auth.uid() returns uuid language sql stable as $$
    select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
$$;

-- PostgREST logger ind som authenticator og skifter til rollen fra JWT'en.
create role authenticator login password 'lokaltest' noinherit;
grant anon, authenticated, service_role to authenticator;

grant usage on schema public to anon, authenticated, service_role;
-- Supabase giver som standard alle rettigheder på nye objekter i public.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
