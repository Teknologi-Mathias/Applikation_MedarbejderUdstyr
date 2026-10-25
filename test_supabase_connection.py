import os

from dotenv import load_dotenv
from supabase import create_client


def main():
    load_dotenv()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
    email = os.getenv("SUPABASE_TEST_EMAIL")
    password = os.getenv("SUPABASE_TEST_PASSWORD")

    # Kontrollér, at alle testindstillinger er tilgængelige.
    missing = [
        name
        for name, value in {
            "SUPABASE_URL": url,
            "SUPABASE_PUBLISHABLE_KEY": key,
            "SUPABASE_TEST_EMAIL": email,
            "SUPABASE_TEST_PASSWORD": password,
        }.items()
        if not value
    ]

    if missing:
        raise SystemExit(
            "Følgende indstillinger mangler: " + ", ".join(missing)
        )

    try:
        # Opret forbindelsen til Supabase.
        supabase = create_client(url, key)

        # Log ind med testbrugeren.
        auth_result = supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )

        if auth_result.user is None:
            raise RuntimeError("Login returnerede ingen bruger.")

        user_id = str(auth_result.user.id)

        print("Login gennemført.")
        print("Bruger-ID modtaget.")

        # Skriv en testpost til databasen.
        supabase.table("integration_probe").insert(
            {
                "user_id": user_id,
                "message": "Forbindelsestest fra IN-BASE",
            }
        ).execute()

        print("Testpost skrevet til databasen.")

        # Læs kun rækker, der tilhører den indloggede bruger.
        result = (
            supabase.table("integration_probe")
            .select("id, message, created_at")
            .eq("user_id", user_id)
            .execute()
        )

        print(f"Antal læste testposter: {len(result.data)}")
        print("Data:")
        print(result.data)

        print("\nSupabase-forbindelsen fungerer.")

    except Exception as error:
        print("Supabase-testen mislykkedes.")
        print(f"Fejl: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()