"""SQLite durability, append-only evidence, process lock, and verified backups."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class Store:
    def __init__(self, path, identity):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_file = open(str(self.path) + '.lock', 'a')
        os.chmod(self.lock_file.name, 0o600)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, purpose TEXT NOT NULL, created REAL NOT NULL, reverses_task TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS operations(
          id TEXT PRIMARY KEY, operation_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
          task_id TEXT NOT NULL REFERENCES tasks(id), device_id INTEGER NOT NULL,
          requested TEXT NOT NULL, before_values TEXT NOT NULL, after_values TEXT NOT NULL,
          before_etag TEXT NOT NULL, state TEXT NOT NULL, request_id TEXT, native_id INTEGER,
          reverses TEXT REFERENCES operations(id), created REAL NOT NULL, updated REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_correction ON operations(reverses)
          WHERE reverses IS NOT NULL AND state NOT IN ('failed','rejected');
        CREATE TABLE IF NOT EXISTS events(
          seq INTEGER PRIMARY KEY, operation_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL,
          at REAL NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_changes(id INTEGER PRIMARY KEY, payload TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS native_no_update BEFORE UPDATE ON native_changes BEGIN SELECT RAISE(ABORT,'native evidence is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS native_no_delete BEFORE DELETE ON native_changes BEGIN SELECT RAISE(ABORT,'native evidence is append-only'); END;
        ''')
        with self.lock():
            row = self.db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            if row and row[0] != encode(identity):
                raise ValueError('Journal belongs to a different instance, lineage, actor, or policy')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('identity',?)", (encode(identity),))
            self.verify()

    @contextmanager
    def lock(self):
        fcntl.flock(self.lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def event(self, kind, payload, operation_id=None):
        row = self.db.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        previous = row[0] if row else '0' * 64
        at = time.time()
        value = {'operation_id': operation_id, 'kind': kind, 'payload': payload, 'at': at, 'previous_hash': previous}
        self.db.execute('INSERT INTO events(operation_id,kind,payload,at,previous_hash,hash) VALUES(?,?,?,?,?,?)',
                        (operation_id, kind, encode(payload), at, previous, digest(value)))

    def set_state(self, op_id, state, receipt=None, **columns):
        allowed = {'request_id', 'native_id', 'after_values'}
        if not set(columns) <= allowed:
            raise ValueError('Invalid state update')
        with self.transaction():
            sql = 'UPDATE operations SET state=?,updated=?' + ''.join(',' + k + '=?' for k in columns) + ' WHERE id=?'
            self.db.execute(sql, (state, time.time(), *columns.values(), op_id))
            self.event('state', {'state': state, 'receipt': receipt, 'columns': columns}, op_id)

    def verify(self):
        previous = '0' * 64
        projected = {}
        for row in self.db.execute('SELECT * FROM events ORDER BY seq'):
            value = {'operation_id': row['operation_id'], 'kind': row['kind'], 'payload': json.loads(row['payload']),
                     'at': row['at'], 'previous_hash': row['previous_hash']}
            if row['previous_hash'] != previous or digest(value) != row['hash']:
                raise RuntimeError('Journal event integrity failure')
            previous = row['hash']
            payload = value['payload']
            if row['kind'] == 'prepared':
                projected[row['operation_id']] = dict(payload)
            elif row['kind'] == 'state':
                if row['operation_id'] not in projected:
                    raise RuntimeError('State event has no durable intent')
                projected[row['operation_id']]['state'] = payload['state']
                projected[row['operation_id']].update(payload['columns'])
        operations = list(self.db.execute('SELECT * FROM operations'))
        if len(operations) != len(projected):
            raise RuntimeError('Operation projection integrity failure')
        for operation in operations:
            expected = projected.get(operation['id'], {})
            if any(operation[k] != v for k, v in expected.items() if k != 'updated'):
                raise RuntimeError('Operation projection differs from immutable evidence')
        for row in self.db.execute('SELECT * FROM native_changes'):
            if digest(json.loads(row['payload'])) != row['hash']:
                raise RuntimeError('Native archive integrity failure')
        return {'event_head': previous, 'integrity': 'verified'}

    def export(self):
        self.verify()
        return {table: [dict(r) for r in self.db.execute('SELECT * FROM ' + table)]
                for table in ['metadata', 'tasks', 'operations', 'events', 'native_changes']}

    def backup(self, path):
        with self.lock():
            self.verify()
            destination = Path(path)
            if destination.exists():
                raise ValueError('Backup destination already exists')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            with sqlite3.connect(destination) as conn:
                self.db.backup(conn)
            os.chmod(destination, 0o600)
            return {'path': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}

    def close(self):
        self.db.close()
        self.lock_file.close()
