#!/bin/sh
# Køres af postgres-imaget første gang volumen er tom (docker compose up).
# Samme rækkefølge som tools/lokal_testdatabase.py: Supabase-stub, alle
# migreringer (med en konto i det gamle format lige før 005), testhjælpere og
# SQL-testen af administratorreglerne (fejler ved brudt regel).
set -eu

koer() {
    echo "  -> $1"
    psql -v ON_ERROR_STOP=1 -q --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$1"
}

koer /sql/tests/supabase_stub.sql
for fil in /sql/migrations/0*.sql; do
    case "$(basename "$fil")" in
        005*) koer /sql/tests/foer_005_gammel_konto.sql ;;
    esac
    koer "$fil"
done
koer /sql/tests/test_hjaelpere.sql
koer /sql/tests/test_admin_regler.sql
