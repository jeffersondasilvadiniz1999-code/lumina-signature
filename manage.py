"""Explicit migrations and portable backups. Never accepts a connection URL in argv."""
import argparse,base64,json,os,re
from pathlib import Path
from datetime import datetime,timezone
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import load_dotenv
load_dotenv()


def connection():
    return psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row,connect_timeout=15,prepare_threshold=None)


def backup(path):
    with connection() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        tables=[r['table_name'] for r in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name")]
        data={}
        for table in tables:
            rows=c.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchall()
            data[table]=rows
        def encode(value):
            if isinstance(value,(bytes,memoryview)):return '\\x'+bytes(value).hex()
            if isinstance(value,datetime):return value.isoformat()
            from decimal import Decimal
            if isinstance(value,Decimal):return str(value)
            raise TypeError(type(value).__name__)
        payload={'format':'lumina-backup-v1','created_at':datetime.now(timezone.utc).isoformat(),'tables':data}
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(payload,f,ensure_ascii=False,default=encode)
        print('Backup salvo. Contagens:',{t:len(rows) for t,rows in data.items()})


def restore(path):
    payload=json.loads(Path(path).read_text())
    if payload.get('format')!='lumina-backup-v1':raise ValueError('Backup incompatível.')
    with connection() as c:
        if c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() LIMIT 1").fetchone():
            raise RuntimeError('Restauração exige banco/schema vazio. Não substitui dados existentes.')
    # Build the new schema before importing. Source backups stay unchanged.
    from app import app,init
    with app.app_context():init()
    order=['admins','customers','categories','colors','subcategories','uploaded_images','products','carts','orders','order_changes','settings','login_attempts','admin_invites','password_resets']
    with connection() as c:
        # Defaults inserted by migration are safe only in this previously empty destination.
        c.execute("DELETE FROM settings")
        if payload['tables'].get('categories'):c.execute("DELETE FROM categories WHERE name='Sem categoria'")
        for table in order:
            for row in payload['tables'].get(table,[]):
                fields=list(row)
                values=[bytes.fromhex(v[2:]) if table=='uploaded_images' and k=='data' and isinstance(v,str) and v.startswith('\\x') else v for k,v in row.items()]
                query=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(sql.Placeholder() for _ in fields))
                c.execute(query,values)
            if table in ('admins','customers','categories','colors','subcategories','products','orders','order_changes'):
                seq=c.execute('SELECT pg_get_serial_sequence(%s,%s) AS seq',(table,'id')).fetchone()['seq']
                c.execute(sql.SQL('SELECT setval(%s,coalesce((SELECT max(id) FROM {}),1),(SELECT count(*)>0 FROM {}))').format(sql.Identifier(table),sql.Identifier(table)),(seq,))
        print('Restauração concluída em destino vazio.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['migrate','backup','restore','create-admin']);parser.add_argument('path',nargs='?');args=parser.parse_args()
    if args.command=='backup':backup(args.path)
    elif args.command=='restore':restore(args.path)
    else:
        from app import app,init,db,now
        with app.app_context():
            init()
            if args.command=='create-admin':
                from werkzeug.security import generate_password_hash
                password=os.environ.get('ADMIN_INITIAL_PASSWORD','');email=os.environ.get('ADMIN_INITIAL_EMAIL','admin@lumina.local')
                if len(password)<12:raise ValueError('Defina uma senha inicial com pelo menos 12 caracteres.')
                c=db()
                if c.execute('SELECT 1 FROM admins').fetchone():raise RuntimeError('Administradora já existe. Nenhuma senha foi substituída.')
                c.execute('INSERT INTO admins(email,password_hash,created_at,role) VALUES(%s,%s,%s,%s)',(email,generate_password_hash(password),now(),'owner'));c.commit()
            print('Migrações concluídas; dados preservados.')

if __name__=='__main__':main()
