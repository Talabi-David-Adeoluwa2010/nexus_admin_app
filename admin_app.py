import random
import string
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_super_secret_key_9988'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory database (Resets when server restarts on free plan)
banned_users = set()
activation_codes = {}  # Stores code: status (e.g., {"NEXUS-A1B2C3": "Active"})

@app.route('/')
def admin_portal():
    return render_template('admin_dashboard.html')

# --- Socket Real-time Actions ---

@socketio.on('connect')
def handle_connect():
    # Sync everything immediately when admin page is opened
    emit('system_init', {
        'status': 'Secure Link Active',
        'banned': list(banned_users),
        'codes': activation_codes
    })

@socketio.on('generate_code')
def handle_generate_code():
    # Create a 6-character unique code prefixed with NEXUS-
    new_code = "NEXUS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    activation_codes[new_code] = "Active"
    
    # Broadcast updates to the UI
    emit('code_update', {'codes': activation_codes}, broadcast=True)
    emit('new_log', {'message': f"🔑 Generated code: {new_code}"}, broadcast=True)

@socketio.on('delete_code')
def handle_delete_code(data):
    code = data.get('code')
    if code in activation_codes:
        del activation_codes[code]
        emit('code_update', {'codes': activation_codes}, broadcast=True)
        emit('new_log', {'message': f"🗑️ Revoked code: {code}"}, broadcast=True)

@socketio.on('apply_ban')
def handle_ban(data):
    username = data.get('username', '').strip()
    if username:
        banned_users.add(username)
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('new_log', {'message': f"🚫 Banned user account: {username}"}, broadcast=True)

@socketio.on('remove_ban')
def handle_unban(data):
    username = data.get('username')
    if username in banned_users:
        banned_users.remove(username)
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('new_log', {'message': f"✅ Unbanned user account: {username}"}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
