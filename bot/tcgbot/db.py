"""Watchlist alerts and collections, in a small SQLite file under data/."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
create table if not exists watches(
  id integer primary key autoincrement, user_id integer not null, card_id integer not null,
  printing text, direction text not null, price real not null, armed integer not null default 1,
  created text default current_timestamp);
create table if not exists collection(
  user_id integer not null, card_id integer not null, printing text not null, qty integer not null,
  paid_each real, primary key(user_id, card_id, printing));
create table if not exists meta(key text primary key, value text);
"""


class DB:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        self.c.commit()

    # meta
    def get(self, key, default=None):
        r = self.c.execute("select value from meta where key=?", (key,)).fetchone()
        return r["value"] if r else default

    def put(self, key, value):
        self.c.execute("insert into meta(key,value) values(?,?) on conflict(key) do update set value=excluded.value", (key, str(value)))
        self.c.commit()

    # watches
    def add_watch(self, user_id, card_id, printing, direction, price) -> int:
        cur = self.c.execute("insert into watches(user_id,card_id,printing,direction,price) values(?,?,?,?,?)",
                             (user_id, card_id, printing, direction, price))
        self.c.commit()
        return cur.lastrowid

    def watches(self, user_id=None):
        if user_id is None:
            return self.c.execute("select * from watches").fetchall()
        return self.c.execute("select * from watches where user_id=? order by id", (user_id,)).fetchall()

    def remove_watch(self, user_id, wid) -> bool:
        cur = self.c.execute("delete from watches where id=? and user_id=?", (wid, user_id))
        self.c.commit()
        return cur.rowcount > 0

    def set_armed(self, wid, armed: bool):
        self.c.execute("update watches set armed=? where id=?", (1 if armed else 0, wid))
        self.c.commit()

    # collection
    def add_card(self, user_id, card_id, printing, qty, paid_each=None):
        row = self.c.execute("select qty, paid_each from collection where user_id=? and card_id=? and printing=?",
                             (user_id, card_id, printing)).fetchone()
        if row:
            new_qty = row["qty"] + qty
            if paid_each is not None and row["paid_each"] is not None:
                paid = (row["paid_each"] * row["qty"] + paid_each * qty) / new_qty
            else:
                paid = paid_each if paid_each is not None else row["paid_each"]
            if new_qty <= 0:
                self.c.execute("delete from collection where user_id=? and card_id=? and printing=?", (user_id, card_id, printing))
            else:
                self.c.execute("update collection set qty=?, paid_each=? where user_id=? and card_id=? and printing=?",
                               (new_qty, paid, user_id, card_id, printing))
        elif qty > 0:
            self.c.execute("insert into collection values(?,?,?,?,?)", (user_id, card_id, printing, qty, paid_each))
        self.c.commit()

    def collection(self, user_id):
        return self.c.execute("select * from collection where user_id=?", (user_id,)).fetchall()
