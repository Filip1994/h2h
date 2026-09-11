import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

root = Path('.')
files = sorted((root / 'data' / 'raw_api').glob('*.jsonl'))
if not files:
    raise SystemExit('No raw API files found')

for src in files:
    base = src.stem
    key = f'quantumbet/raw-api/{base}.jsonl.gz'
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    head = subprocess.run([
        'aws', 's3api', 'head-object', '--bucket', os.environ['S3_BUCKET'],
        '--key', key, '--endpoint-url', os.environ['S3_ENDPOINT'],
        '--region', os.environ['AWS_DEFAULT_REGION'],
    ], capture_output=True, text=True)
    if head.returncode == 0:
        meta = json.loads(head.stdout).get('Metadata', {})
        if meta.get('sha256') != sha:
            raise RuntimeError(f'Checksum mismatch for immutable object {key}')
        print(f'Already migrated: {src}')
        continue
    with tempfile.NamedTemporaryFile(suffix='.jsonl.gz', delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with src.open('rb') as fin, gzip.open(tmp_path, 'wb') as fout:
            while chunk := fin.read(1024 * 1024):
                fout.write(chunk)
        subprocess.run([
            'aws', 's3', 'cp', str(tmp_path), f"s3://{os.environ['S3_BUCKET']}/{key}",
            '--endpoint-url', os.environ['S3_ENDPOINT'],
            '--region', os.environ['AWS_DEFAULT_REGION'],
            '--metadata', f'sha256={sha}', '--no-progress',
        ], check=True)
    finally:
        tmp_path.unlink(missing_ok=True)

print('Raw API archive upload: PASS')

jsonl_files = sorted((root / 'data').glob('*.jsonl'))
json_files = [root / name for name in [
    'bets.json', 'predictions.json', 'ledger_meta.json', 'api_usage.json',
    'api_usage_history.json', 'generation_health.json',
    'generation_health_history.json', 'odds_collection_budget.json',
    'odds_collection_state.json', 'odds_collection_metrics.json',
    'production_dashboard.json', 'production_operations_gate.md',
] if (root / name).exists()]

with psycopg.connect(os.environ['RAILWAY_DATABASE_URL'], sslmode='require') as conn:
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS quantumbet_archive_records (
            record_id text PRIMARY KEY, source_file text NOT NULL, line_no bigint NOT NULL,
            payload jsonb NOT NULL, migrated_at timestamptz NOT NULL DEFAULT now())''')
        cur.execute('''CREATE TABLE IF NOT EXISTS quantumbet_archive_manifest (
            source_file text PRIMARY KEY, source_bytes bigint NOT NULL,
            source_sha256 text NOT NULL, record_count bigint NOT NULL,
            migrated_at timestamptz NOT NULL DEFAULT now())''')

    def put(source_file, line_no, payload):
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        record_id = hashlib.sha256(f'{source_file}\0{line_no}\0{canonical}'.encode()).hexdigest()
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO quantumbet_archive_records
                (record_id, source_file, line_no, payload) VALUES (%s,%s,%s,%s)
                ON CONFLICT (record_id) DO NOTHING''',
                (record_id, source_file, line_no, Jsonb(payload)))

    for path in jsonl_files + json_files:
        count = 0
        if path.suffix == '.jsonl':
            with path.open('r', encoding='utf-8', errors='replace') as fh:
                for line_no, line in enumerate(fh, 1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        put(str(path), line_no, payload)
                        count += 1
        else:
            raw = path.read_text(encoding='utf-8')
            payload = json.loads(raw) if path.suffix == '.json' else {'text': raw}
            if isinstance(payload, list):
                for idx, item in enumerate(payload, 1):
                    put(str(path), idx, item)
                count = len(payload)
            else:
                put(str(path), 1, payload)
                count = 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO quantumbet_archive_manifest
                (source_file, source_bytes, source_sha256, record_count) VALUES (%s,%s,%s,%s)
                ON CONFLICT (source_file) DO UPDATE SET source_bytes=EXCLUDED.source_bytes,
                source_sha256=EXCLUDED.source_sha256, record_count=EXCLUDED.record_count,
                migrated_at=now()''', (str(path), path.stat().st_size, digest, count))
        print(f'Migrated {path}: {count} records')
    conn.commit()

with psycopg.connect(os.environ['RAILWAY_DATABASE_URL'], sslmode='require') as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM quantumbet_archive_records')
        records = cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM quantumbet_archive_manifest')
        manifests = cur.fetchone()[0]
assert manifests > 0
print(f'Postgres archive records: {records}')
print(f'Postgres archive manifests: {manifests}')
print('Postgres migration verification: PASS')
