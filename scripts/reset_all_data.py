from shared.database import init_db, reset_all_system_data


def main() -> None:
    init_db()
    deleted = reset_all_system_data()
    print("RESET_ALL_DATA_OK")
    for table_name in sorted(deleted):
        print(f"{table_name}: {deleted[table_name]}")


if __name__ == "__main__":
    main()
