#!/usr/bin/env python3
import psycopg2


def main():
    with psycopg2.connect(host="db", database="bot", user="bot", password="bot") as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
            print(f"Result: {result[0]}")


if __name__ == "__main__":
    main()
