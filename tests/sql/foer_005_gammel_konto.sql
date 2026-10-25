-- KUN LOKAL TEST: køres EFTER 004 og FØR 005 af tools/lokal_testdatabase.py.
-- En konto i det gamle format (login med e-mail, e-mail i profilen), så
-- test_admin_regler.sql kan kontrollere, at 005 flytter den til brugernavnslogin.
insert into auth.users (id, email, email_confirmed_at)
values ('00000000-0000-0000-0000-0000000000b1', 'Gammel.Admin@Firma.dk', now());
insert into auth.identities (user_id, provider, identity_data)
values ('00000000-0000-0000-0000-0000000000b1', 'email',
        '{"sub": "00000000-0000-0000-0000-0000000000b1", "email": "gammel.admin@firma.dk"}');
insert into public.user_profiles (id, username, display_name, email, role, must_change_password)
values ('00000000-0000-0000-0000-0000000000b1', 'gammel.admin', 'Gammel Admin',
        'gammel.admin@firma.dk', 'Administrator', false);
