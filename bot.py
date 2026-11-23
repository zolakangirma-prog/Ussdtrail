import os, asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application,CommandHandler,ContextTypes
from main import ADMINS,create_license,db,admin_check,make_code,digest
load_dotenv(); TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
def is_admin(uid):return str(uid) in ADMINS
async def start(u:Update,c:ContextTypes.DEFAULT_TYPE):
 await u.message.reply_text('Welcome to the Training Simulator Activation Center.\nUse /activate to request a one-time activation code (15 demonstrations).\nCommands: /status /help')
async def help_cmd(u,c):await u.message.reply_text('/activate — request 15 demonstrations\n/status — license status\n/help — instructions')
async def activate(u,c):
 uid=u.effective_user.id; username=u.effective_user.username
 code,lid=create_license(uid,username)
 await u.message.reply_text(f'Activation code: {code}\nAuthorized demonstrations: 15\nEnter this code in the simulator. It binds to the first device that redeems it.')
async def status(u,c):
 uid=str(u.effective_user.id)
 with db() as con:r=con.execute('SELECT status,remaining_uses,total_uses,id FROM licenses WHERE telegram_id=? ORDER BY created_at DESC LIMIT 1',(uid,)).fetchone()
 await u.message.reply_text('No license found.' if not r else f"Status: {r['status']}\nRemaining: {r['remaining_uses']} / {r['total_uses']}\nLicense: {r['id']}")
async def admin(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 await u.message.reply_text('Admin commands: /generate <telegram_id> /licenses /user <telegram_id> /revoke <license_id> /extend <license_id> <uses> /reset <license_id> /broadcast <message>')
async def generate(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 if not c.args:return await u.message.reply_text('Usage: /generate TELEGRAM_ID')
 code,lid=create_license(c.args[0]);await u.message.reply_text(f'Code: {code}\nLicense: {lid}\nUses: 15')
async def licenses(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 with db() as con:rows=con.execute('SELECT status,COUNT(*) n FROM licenses GROUP BY status').fetchall()
 await u.message.reply_text('\n'.join(f"{x['status']}: {x['n']}" for x in rows) or 'No licenses')
async def user(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 if not c.args:return await u.message.reply_text('Usage: /user TELEGRAM_ID')
 with db() as con:r=con.execute('SELECT id,status,remaining_uses,total_uses FROM licenses WHERE telegram_id=? ORDER BY created_at DESC',(c.args[0],)).fetchall()
 await u.message.reply_text('\n'.join(f"{x['id']} | {x['status']} | {x['remaining_uses']}/{x['total_uses']}" for x in r) or 'No record')
async def revoke(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 if not c.args:return await u.message.reply_text('Usage: /revoke LICENSE_ID')
 with db() as con:con.execute("UPDATE licenses SET status='revoked' WHERE id=?",(c.args[0],))
 await u.message.reply_text('Revocation applied if license existed.')
async def extend(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 if len(c.args)!=2:return await u.message.reply_text('Usage: /extend LICENSE_ID USES')
 try:n=max(1,min(10000,int(c.args[1])))
 except:return await u.message.reply_text('Uses must be a number.')
 with db() as con:con.execute("UPDATE licenses SET total_uses=total_uses+?,remaining_uses=remaining_uses+?,status='active' WHERE id=?",(n,n,c.args[0]))
 await u.message.reply_text('Extension applied if license existed.')
async def reset(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 if not c.args:return await u.message.reply_text('Usage: /reset LICENSE_ID CONFIRM')
 if len(c.args)<2 or c.args[1]!='CONFIRM':return await u.message.reply_text('Confirm explicitly: /reset LICENSE_ID CONFIRM')
 with db() as con:con.execute("UPDATE licenses SET remaining_uses=15,total_uses=15,status='active' WHERE id=?",(c.args[0],))
 await u.message.reply_text('Reset applied if license existed.')
async def broadcast(u,c):
 if not is_admin(u.effective_user.id):return await u.message.reply_text('Not authorized.')
 msg=' '.join(c.args)
 if not msg:return await u.message.reply_text('Usage: /broadcast message')
 with db() as con:ids=[x[0] for x in con.execute('SELECT DISTINCT telegram_id FROM licenses WHERE telegram_id IS NOT NULL')]
 sent=0
 for uid in ids:
  try:await c.bot.send_message(int(uid),msg);sent+=1
  except Exception:pass
 await u.message.reply_text(f'Broadcast sent to {sent} users.')
def main():
 app=Application.builder().token(TOKEN).build()
 for cmd,fn in [('start',start),('help',help_cmd),('activate',activate),('status',status),('admin',admin),('generate',generate),('licenses',licenses),('user',user),('revoke',revoke),('extend',extend),('reset',reset),('broadcast',broadcast)]:app.add_handler(CommandHandler(cmd,fn))
 app.run_polling()
if __name__=='__main__':main()
