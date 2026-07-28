"""One-time bootstrap: create the first admin account. Run on the server:

    python create_admin.py
"""
import getpass

import auth
import db


def main():
    print("=== 3M Issues & Projects Tracker — create admin account ===")
    username = input("Username: ").strip()
    if db.get_user_by_username(username):
        print(f"User '{username}' already exists. Aborting.")
        return
    display_name = input("Display name: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match. Aborting.")
        return
    db.create_user(username, display_name, email, auth.hash_password(password), is_admin=True)
    print(f"Admin account '{username}' created. Log in at the app URL and add your team under Admin.")


if __name__ == "__main__":
    main()
