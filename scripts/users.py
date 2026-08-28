#!/usr/bin/env python3
"""
Manage vault access keys.

There are no usernames or passwords: each vault is opened with one long random
key, printed once here. Keys and personal data live in vault.db; recipes.db
stays a clean, shareable recipe library.

    python3 scripts/users.py add "Petre"        # new empty vault
    python3 scripts/users.py add "Petre" --claim  # ...and adopt existing data
    python3 scripts/users.py list                # ids and labels (never keys)
    python3 scripts/users.py revoke <id>         # invalidate a key
    python3 scripts/users.py revoke <id> --delete-data
    python3 scripts/users.py stats                # rows per vault

In Docker:  docker compose exec cooker python3 scripts/users.py add "Petre"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import VAULT_DB_PATH  # noqa: E402
from lib.db import get_db  # noqa: E402
from lib.users import ORPHAN_TABLES, create_user, list_users, revoke_user, users_exist  # noqa: E402


def _orphan_rows(db):
    return sum(
        db.execute(f"SELECT count(*) FROM vault.{t} WHERE user_id=''").fetchone()[0]
        for t in ORPHAN_TABLES
    )


def cmd_add(args):
    db = get_db()
    first = not users_exist()
    orphans = _orphan_rows(db)
    claim = args.claim or (first and orphans > 0 and not args.no_claim)

    uid, key = create_user(args.label or "", claim_orphans=claim)

    print()
    print("  Vault created" + (f" for {args.label!r}" if args.label else ""))
    print(f"  id:  {uid}")
    print(f"  key: {key}")
    print()
    print("  Give this key to the person who owns the vault. It is shown once and")
    print("  cannot be recovered — only its hash is stored. Anyone holding it can")
    print("  open this vault, so send it over something private.")
    if claim:
        print(f"\n  Adopted {orphans} pre-existing rows (favourites, history, list, notes).")
    elif orphans:
        print(f"\n  Note: {orphans} rows still belong to no vault. Re-run with --claim")
        print("  on the vault that should own them.")
    if first:
        print("\n  Access keys are now required for every request.")
    print()


def cmd_list(args):
    users = list_users()
    if not users:
        print("No vaults yet — everything belongs to the single default vault.")
        return
    print(f"{'id':18} {'created':21} label")
    for u in users:
        print(f"{u['id']:18} {u['created_at']:21} {u['label'] or '-'}")
    print(f"\n{len(users)} vault(s) in {VAULT_DB_PATH}")


def cmd_revoke(args):
    if args.delete_data and not args.yes:
        confirm = input(f"Delete ALL data owned by {args.id}? Type the id to confirm: ")
        if confirm.strip() != args.id:
            print("Aborted.")
            return
    if revoke_user(args.id, delete_data=args.delete_data):
        print(f"Revoked {args.id}" + (" and deleted its data." if args.delete_data else "."))
        if not args.delete_data:
            print("Its data is still on disk but unreachable; re-add with --claim is not possible.")
    else:
        print(f"No vault with id {args.id}.")


def cmd_stats(args):
    db = get_db()
    rows = [("(unclaimed)", "")] + [(u["label"] or u["id"], u["id"]) for u in list_users()]
    tables = list(ORPHAN_TABLES) + ["user_recipes"]
    header = f"{'vault':22}" + "".join(f"{t[:12]:>14}" for t in tables)
    print(header)
    for label, uid in rows:
        counts = []
        for t in tables:
            col = "owner" if t == "user_recipes" else "user_id"
            counts.append(db.execute(f"SELECT count(*) FROM vault.{t} WHERE {col}=?", [uid]).fetchone()[0])
        print(f"{label[:22]:22}" + "".join(f"{c:>14}" for c in counts))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="create a vault and print its access key")
    a.add_argument("label", nargs="?", default="", help="name for your own reference")
    a.add_argument("--claim", action="store_true", help="adopt data that belongs to no vault")
    a.add_argument("--no-claim", action="store_true", help="never adopt existing data")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="list vault ids and labels (never keys)")
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("revoke", help="invalidate a key")
    r.add_argument("id")
    r.add_argument("--delete-data", action="store_true", help="also erase everything it owns")
    r.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    r.set_defaults(func=cmd_revoke)

    s = sub.add_parser("stats", help="row counts per vault")
    s.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
