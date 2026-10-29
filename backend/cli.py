import argparse
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import config, db


def main():
    parser=argparse.ArgumentParser(description='Operação do blog Állan Torres')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('health')
    schedule=sub.add_parser('schedule')
    schedule.add_argument('action',choices=['start','pause','status'])
    generate=sub.add_parser('generate')
    generate.add_argument('--topic',default='')
    generate.add_argument('--url',default='')
    backup=sub.add_parser('backup')
    backup.add_argument('--directory',default='/data/backups')
    sub.add_parser('worker-health')
    args=parser.parse_args()
    db.init()
    if args.command=='health':
        print(json.dumps({'database':'ok','provider':config.provider_info()}))
    elif args.command=='schedule':
        if args.action != 'status':
            if args.action=='start' and not config.provider_info()['configured']:
                raise SystemExit('Configure o provedor antes de iniciar a agenda.')
            db.update_settings({'schedulerEnabled':args.action=='start'})
        settings=db.get_settings()
        print(json.dumps({key:settings[key] for key in ['schedulerEnabled','publicationMode','timezone','schedule']},ensure_ascii=False))
    elif args.command=='generate':
        print(json.dumps(db.queue_job({'topic':args.topic,'url':args.url}),ensure_ascii=False))
    elif args.command=='worker-health':
        health=db.get_settings()['worker'].get('heartbeat_at','')
        if not health or datetime.fromisoformat(health)<datetime.now(timezone.utc)-timedelta(minutes=5):
            raise SystemExit(1)
    elif args.command=='backup':
        directory=Path(args.directory)
        directory.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        target=directory/f'blog-{stamp}.sqlite3'
        with db.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        print('Backup SQLite verificado:',target.name)
        with sqlite3.connect(target) as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('Falha de integridade no backup')
        # Only this task's dated backup files are eligible for retention cleanup.
        for stale in sorted(directory.glob('blog-????????T??????Z.sqlite3'))[:-30]:
            stale.unlink()


if __name__=='__main__':
    main()
