"""Offline, explicit platform bootstrap and legacy ownership migration.
Run python scripts/saas_admin.py --help with the API stopped.
"""
import argparse
import csv
import getpass
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from app import auth
from app.config import get_data_dir, DATASET_FILES
from app.data_service import DataService
from app.tenancy import TenantRegistry, acquire_process_lock


def bootstrap(username, password):
    with auth.transaction() as data:
        if any(u.get('role') == 'super_admin' for u in data['users'].values()):
            raise ValueError('A Super Admin already exists. Bootstrap cannot create or reset another.')
        if username in data['users']:
            raise ValueError('Username already exists. Choose a new platform-owner username.')
        data['users'][username] = auth.new_user(username, password, 'super_admin', must_change=True)
        auth.audit(data, 'offline-operator', 'super_admin_bootstrapped', username)


def migrate(source, manifest, registry):
    """Complete manifest; stage and validate all files; never overwrite existing records."""
    source = Path(source).resolve()
    legacy = DataService(source).load()
    with open(manifest, encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    mapping = {}
    institutions = auth.read_store()['institutions']
    for row in rows:
        sid, iid = row['student_id'].strip().upper(), row['institution_id'].strip()
        if sid in mapping or iid not in institutions:
            raise ValueError('Duplicate student mapping or unknown institution.')
        mapping[sid] = iid
    if set(mapping) != set(legacy.students.index):
        raise ValueError('Manifest must map every legacy student exactly once, with no extra IDs.')
    paths = [source / name for name in DATASET_FILES.values()]
    paths += list((source / 'source_sheets').glob('*.csv'))
    stage = Path(tempfile.mkdtemp(prefix='tenant-migration-', dir=source.parent))
    moved = []
    try:
        for iid in set(mapping.values()):
            target = registry.path(iid)
            if target.exists():
                for csv_path in target.rglob('*.csv'):
                    with csv_path.open(encoding='utf-8-sig', newline='') as h:
                        if any(csv.DictReader(h)):
                            raise ValueError('Target has records; refusing to overwrite institution data.')
            for path in paths:
                with path.open(encoding='utf-8-sig', newline='') as h:
                    reader = csv.DictReader(h)
                    columns, records = reader.fieldnames, list(reader)
                id_column = 'student_id' if columns and 'student_id' in columns else 'Student ID'
                if not columns or id_column not in columns:
                    raise ValueError(f'Ownership cannot be established for {path.name}.')
                if any(r[id_column].strip().upper() not in mapping for r in records):
                    raise ValueError(f'Orphan student ID in {path.name}; resolve ownership before migrating.')
                dest = stage / iid / path.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('w', encoding='utf-8', newline='') as h:
                    writer = csv.DictWriter(h, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(r for r in records if mapping[r[id_column].strip().upper()] == iid)
            DataService(stage / iid).load()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
        for iid in set(mapping.values()):
            target = registry.path(iid)
            backup = target.with_name(target.name + '.empty-backup-' + stamp)
            if target.exists():
                target.rename(backup)
            moved.append((target, backup))
            target.parent.mkdir(parents=True, exist_ok=True)
            (stage / iid).rename(target)
        with auth.transaction() as data:
            auth.audit(data, 'offline-operator', 'legacy_data_mapped', str(len(mapping)) + ' student records')
    except Exception:
        # Restore only the explicitly tracked target directories; preserve staged data.
        for target, backup in reversed(moved):
            if target.exists():
                target.rename(stage / (target.name + '-rolled-back'))
            if backup.exists():
                backup.rename(target)
        raise
    finally:
        # Leave migration staging/backup directories for operator review, never delete data.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    bootstrap_parser = commands.add_parser('bootstrap-super-admin', aliases=['bootstrap'])
    bootstrap_parser.add_argument('--username')
    migrate_parser = commands.add_parser('migrate-legacy-data', aliases=['migrate-data'])
    migrate_parser.add_argument('--source', required=True)
    migrate_parser.add_argument('--manifest', required=True)
    reset = commands.add_parser('reset-super-admin')
    reset.add_argument('--username', required=True)
    args = parser.parse_args()
    with acquire_process_lock(auth.USERS_FILE.with_suffix('.lock')), acquire_process_lock(get_data_dir() / '.tenant-writer.lock'):
        if auth.USERS_FILE.exists():
            backup = auth.USERS_FILE.with_name(auth.USERS_FILE.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
            shutil.copy2(auth.USERS_FILE, backup)
        if args.command in {'migrate-legacy-data', 'migrate-data'}:
            migrate(args.source, args.manifest, TenantRegistry(get_data_dir()))
        else:
            username = (args.username or input('Super Admin username: ').strip()) if args.command in {'bootstrap-super-admin', 'bootstrap'} else args.username
            password = getpass.getpass('New password (12-256 characters): ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords do not match.')
            if args.command in {'bootstrap-super-admin', 'bootstrap'}:
                bootstrap(username, password)
            else:
                with auth.transaction() as data:
                    row = data['users'].get(username)
                    if not row or row.get('role') != 'super_admin':
                        raise ValueError('Existing Super Admin not found.')
                    if not 12 <= len(password) <= 256:
                        raise ValueError('Password must contain 12-256 characters.')
                    row['password_hash'] = auth._hash_password(password)
                    row['must_change_password'] = True
                    auth.revoke(row)
                    auth.audit(data, 'offline-operator', 'super_admin_recovery', username)
    print('Completed. No credentials were written to the console.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc))
