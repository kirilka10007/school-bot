from shared.database import get_connection


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM known_telegram_users
        WHERE telegram_username IS NULL OR TRIM(telegram_username) = ''
        """
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"CLEANED_KNOWN_USERS_WITHOUT_USERNAME: {deleted}")


if __name__ == "__main__":
    main()
