"""SQLite transactions that also close their OS file handles on exit."""
import sqlite3


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(*args, **kwargs):
    return sqlite3.connect(*args, factory=Connection, **kwargs)
