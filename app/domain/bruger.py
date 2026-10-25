"""Brugernavne: den identitet, der vises i IN-BASE og står i tidslinjer og kommentarer.

Et brugernavn normaliseres ALTID på samme måde (mellemrum fjernes, store
bogstaver), så " hafra" og "HAFRA" er samme bruger. Samme regel håndhæves i
databasen (005) og i Edge Functions (supabase/functions/_shared/admin.ts).
"""
import re

# 2-40 tegn: A-Z, 0-9, punktum, bindestreg og understreg. Starter og slutter
# med et bogstav/tal og har aldrig to punktummer i træk (brugernavnet indgår
# i et internt login-alias, som skal være en gyldig e-mailadresse).
BRUGERNAVN_MOENSTER = re.compile(r"^(?!.*\.\.)[A-Z0-9](?:[A-Z0-9._-]{0,38}[A-Z0-9])$")
BRUGERNAVN_REGEL = ("Brugernavnet skal være 2-40 tegn: bogstaver (A-Z), tal, punktum, "
                    "- eller _ – og starte og slutte med et bogstav eller tal.")


def normaliser_brugernavn(tekst) -> str:
    """" hafra " -> "HAFRA"."""
    return str(tekst or "").strip().upper()


def er_gyldigt_brugernavn(brugernavn: str) -> bool:
    """brugernavn skal være normaliseret."""
    return bool(BRUGERNAVN_MOENSTER.match(brugernavn or ""))
