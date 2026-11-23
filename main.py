import os, sqlite3, secrets, hashlib, uuid, time, asyncio
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv()
DB=os.getenv('DATABASE_PATH','licenses.sqlite3'); APP_ID=os.getenv('APP_ID','com.ussd.popup')
ADMIN_TOKEN=os.getenv('ADMIN_API_TOKEN','CHANGE_THIS_LONG_RANDOM_VALUE')
BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN',''); ADMINS={x.strip() for x in os.getenv('ADMIN_TELEGRAM_IDS','').split(',') if x.strip()}
app=FastAPI(title='Training Simulator License API',version='1.0')
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row
 try: yield c; c.commit()
 finally:c.close()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def init():
 with db() as c:
  c.executescript("CREATE TABLE IF NOT EXISTS licenses(id TEXT PRIMARY KEY,code_hash TEXT UNIQUE,telegram_id TEXT,username TEXT,device_hash TEXT,device_token_hash TEXT,status TEXT,total_uses INTEGER,remaining_uses INTEGER,created_at INTEGER,activated_at INTEGER,last_activation_at INTEGER); CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY AUTOINCREMENT,license_id TEXT,request_id TEXT UNIQUE,created_at INTEGER); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,license_id TEXT,event TEXT,detail TEXT,created_at INTEGER);")
init()
def make_code():
 s=secrets.token_hex(8).upper();return '-'.join(s[i:i+4] for i in range(0,16,4))
def create_license(tg,username=None):
 code=make_code(); lid=str(uuid.uuid4()); now=int(time.time())
 with db() as c:c.execute('INSERT INTO licenses VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(lid,digest(code.replace('-','')),str(tg) if tg else None,username,None,None,'pending',15,15,now,None,None))
 return code,lid
def admin_check(uid):
 if str(uid) not in ADMINS: raise PermissionError('Administrator access required')
def bot_admin_create(tg,username=None):return create_license(tg,username)
class Validate(BaseModel): code:str=Field(min_length=8,max_length=32);app_id:str;device_id:str
class Device(BaseModel):app_id:str;device_id:str
class Consume(Device):request_id:str=Field(min_length=8,max_length=80)
def auth_device(auth):
 if not auth or not auth.startswith('Bearer '):raise HTTPException(401,'Device authorization required')
 token=auth[7:]
 with db() as c:r=c.execute('SELECT * FROM licenses WHERE device_token_hash=?',(digest(token),)).fetchone()
 if not r or r['status']!='active':raise HTTPException(403,'License inactive or revoked')
 return r
@app.get('/health')
def health():return {'ok':True,'service':'training-simulator-license-api'}
@app.post('/api/activation/validate')
def validate(x:Validate):
 if x.app_id!=APP_ID:raise HTTPException(400,'Unknown application')
 with db() as c:
  r=c.execute('SELECT * FROM licenses WHERE code_hash=?',(digest(x.code.upper().replace('-','')),)).fetchone()
  if not r: # codes generated without separators internally; accept normalized format
   normalized=x.code.upper().replace('-','');r=c.execute('SELECT * FROM licenses WHERE code_hash=?',(digest(normalized),)).fetchone()
  if not r:raise HTTPException(400,'Invalid activation code')
  if r['status']=='revoked':raise HTTPException(403,'License revoked')
  if r['status']=='active' and r['device_hash']!=digest(x.device_id):raise HTTPException(409,'Code already bound to another device')
  if r['status']=='pending':
   token=secrets.token_urlsafe(32);c.execute("UPDATE licenses SET status='active',device_hash=?,device_token_hash=?,activated_at=?,last_activation_at=? WHERE id=?",(digest(x.device_id),digest(token),int(time.time()),int(time.time()),r['id']))
  else:
   token=secrets.token_urlsafe(32);c.execute('UPDATE licenses SET device_token_hash=? WHERE id=?',(digest(token),r['id']))
  c.execute('UPDATE licenses SET code_hash=NULL WHERE id=?',(r['id'],));c.execute('INSERT INTO events(license_id,event,detail,created_at) VALUES(?,?,?,?)',(r['id'],'activated','device bound',int(time.time())))
  return {'ok':True,'license_id':r['id'],'device_token':token,'remaining_uses':r['remaining_uses']}
@app.post('/api/license/status')
def status(x:Device,authorization:str|None=Header(default=None)):
 r=auth_device(authorization)
 if x.app_id!=APP_ID or digest(x.device_id)!=r['device_hash']:raise HTTPException(403,'Device mismatch')
 return {'status':r['status'],'remaining_uses':r['remaining_uses'],'total_uses':r['total_uses'],'license_id':r['id']}
@app.post('/api/license/consume')
def consume(x:Consume,authorization:str|None=Header(default=None)):
 r=auth_device(authorization)
 if x.app_id!=APP_ID or digest(x.device_id)!=r['device_hash']:raise HTTPException(403,'Device mismatch')
 with db() as c:
  prior=c.execute('SELECT license_id FROM usage WHERE request_id=?',(x.request_id,)).fetchone()
  if prior:
   current=c.execute('SELECT remaining_uses FROM licenses WHERE id=?',(r['id'],)).fetchone();return {'ok':True,'remaining_uses':current['remaining_uses'],'duplicate':True}
  current=c.execute("SELECT remaining_uses,status FROM licenses WHERE id=?",(r['id'],)).fetchone()
  if current['status']!='active' or current['remaining_uses']<=0:raise HTTPException(403,'No authorized demonstrations remain')
  c.execute('UPDATE licenses SET remaining_uses=remaining_uses-1 WHERE id=?',(r['id'],));c.execute('INSERT INTO usage(license_id,request_id,created_at) VALUES(?,?,?)',(r['id'],x.request_id,int(time.time())))
  left=current['remaining_uses']-1
  if left==0:c.execute("UPDATE licenses SET status='exhausted' WHERE id=?",(r['id'],))
  c.execute('INSERT INTO events(license_id,event,detail,created_at) VALUES(?,?,?,?)',(r['id'],'use_consumed',str(left),int(time.time())))
  return {'ok':True,'remaining_uses':left}
# Admin HTTP operations require a separate server-side secret; never put this in the APK.
def admin(auth):
 if not auth or auth!=f'Bearer {ADMIN_TOKEN}':raise HTTPException(401,'Admin API authorization required')
@app.post('/api/admin/revoke/{license_id}')
def revoke(license_id:str,authorization:str|None=Header(default=None)):
 admin(authorization)
 with db() as c:c.execute("UPDATE licenses SET status='revoked' WHERE id=?",(license_id,))
 return {'ok':True}

class BotRequest(BaseModel):
    telegram_id: str
    username: str | None = None

@app.post('/api/activation/request')
def activation_request(x: BotRequest, authorization: str | None = Header(default=None)):
    admin(authorization)
    code, license_id = create_license(x.telegram_id, x.username)
    return {'activation_code': code, 'license_id': license_id, 'authorized_uses': 15}

class AdminRenew(BaseModel):
    license_id: str
    uses: int = Field(default=15, ge=1, le=10000)

@app.post('/api/license/renew')
def renew(x: AdminRenew, authorization: str | None = Header(default=None)):
    admin(authorization)
    with db() as c:
        cur = c.execute("UPDATE licenses SET total_uses=total_uses+?, remaining_uses=remaining_uses+?, status='active' WHERE id=? AND status!='revoked'", (x.uses, x.uses, x.license_id))
        if cur.rowcount != 1:
            raise HTTPException(404, 'License not found or revoked')
    return {'ok': True, 'added_uses': x.uses}

class AdminRevoke(BaseModel):
    license_id: str

@app.post('/api/license/revoke')
def revoke_body(x: AdminRevoke, authorization: str | None = Header(default=None)):
    admin(authorization)
    with db() as c:
        cur = c.execute("UPDATE licenses SET status='revoked' WHERE id=?", (x.license_id,))
        if cur.rowcount != 1:
            raise HTTPException(404, 'License not found')
    return {'ok': True}
