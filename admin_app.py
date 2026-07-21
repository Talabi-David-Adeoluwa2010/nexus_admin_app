# MUST BE THE FIRST TWO LINES IN THE FILE TO PREVENT DEADLOCKS
from gevent import monkey
monkey.patch_all()

import os
import random
import string
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_super_secret_key_9988'
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

banned_users = set()
activation_codes = {}
active_sessions = {}

# --- External API Endpoints ---

@app.route('/api/verify_code', methods=['POST'])
def verify_code():
    data = request.json or {}
    code = data.get('code', '').strip().upper()
    
    if not code:
        return jsonify({"valid": False, "reason": "No code provided."}), 200

    # Strict check: Key must exist in generated activation codes
    if code in activation_codes:
        details = activation_codes[code]
        current_time = time.time()
        
        # Check if key has expired
        if current_time > details['expires_at']:
            del activation_codes[code]
            socketio.emit('code_update', {'codes': get_serializable_codes()})
            socketio.emit('new_log', {'message': f"⚠️ Code {code} expired automatically."})
            return jsonify({"valid": False, "reason": "This activation code has expired."}), 200
            
        # Consume key so it cannot be reused or shared
        del activation_codes[code]
        socketio.emit('code_update', {'codes': get_serializable_codes()})
        socketio.emit('new_log', {'message': f"🔑 Code {code} redeemed successfully."})

        return jsonify({
            "valid": True, 
            "expires_at": details['expires_at'],
            "time_remaining": int(details['expires_at'] - current_time)
        }), 200

    # Reject if key does not exist or was already used
    return jsonify({"valid": False, "reason": "Invalid or already used activation code."}), 200

@app.route('/api/check_ban/<username>', methods=['GET'])
def check_ban(username):
    is_banned = username.strip() in banned_users
    return jsonify({"banned": is_banned}), 200

@app.route('/api/apply_ban_remote', methods=['POST'])
def apply_ban_remote():
    data = request.json or {}
    username = data.get('username', '').strip()
    if username:
        banned_users.add(username)
        sessions_to_kill = [sid for sid, sess in list(active_sessions.items()) if sess['username'] == username]
        for sid in sessions_to_kill:
            if sid in active_sessions:
                del active_sessions[sid]
        socketio.emit('blacklist_update', {'banned': list(banned_users)})
        socketio.emit('session_update', {'sessions': list(active_sessions.values())})
    return jsonify({"success": True}), 200

@app.route('/api/register_session_remote', methods=['POST'])
def register_session_remote():
    data = request.json or {}
    username = data.get('username')
    ip_address = data.get('ip', request.remote_addr)
    sid = data.get('sid', str(time.time()))
    
    if username:
        active_sessions[sid] = {
            "username": username,
            "joined_at": time.strftime('%H:%M:%S', time.localtime()),
            "ip": ip_address
        }
        socketio.emit('session_update', {'sessions': list(active_sessions.values())})
        socketio.emit('new_log', {'message': f"🟢 User connected: {username} ({ip_address})"})
    return jsonify({"success": True}), 200

@app.route('/api/remove_session_remote', methods=['POST'])
def remove_session_remote():
    data = request.json or {}
    sid = data.get('sid')
    if sid and sid in active_sessions:
        user = active_sessions[sid]['username']
        del active_sessions[sid]
        socketio.emit('session_update', {'sessions': list(active_sessions.values())})
        socketio.emit('new_log', {'message': f"🔴 User exited: {user}"})
    return jsonify({"success": True}), 200

# --- Web UI Routes ---

@app.route('/')
def admin_portal():
    return render_template('admin_dashboard.html')

def get_serializable_codes():
    current_time = time.time()
    formatted = {}
    expired_to_clean = []
    
    for code, details in activation_codes.items():
        remaining = details['expires_at'] - current_time
        if remaining <= 0:
            expired_to_clean.append(code)
        else:
            formatted[code] = {
                "expires_in_mins": round(remaining / 60, 1),
                "duration_hours": details['duration_hours']
            }
            
    for code in expired_to_clean:
        if code in activation_codes:
            del activation_codes[code]
        
    return formatted

# --- Socket Event Controls ---

@socketio.on('connect')
def handle_connect():
    emit('system_init', {
        'status': 'Secure Link Active',
        'banned': list(banned_users),
        'codes': get_serializable_codes(),
        'sessions': list(active_sessions.values())
    })

@socketio.on('generate_code')
def handle_generate_code(data):
    hours = float(data.get('hours', 1.0))
    
    # Generates exact 14-character code: 'NEXUS-' (6 chars) + 8 random chars = 14 total
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    new_code = f"NEXUS-{random_part}"
    
    expiration_timestamp = time.time() + (hours * 3600)
    activation_codes[new_code] = {
        "expires_at": expiration_timestamp,
        "duration_hours": hours
    }
    
    emit('code_update', {'codes': get_serializable_codes()}, broadcast=True)
    emit('new_log', {'message': f"🔑 14-Char Code Generated: {new_code} (Valid for {hours} hours)"}, broadcast=True)

@socketio.on('delete_code')
def handle_delete_code(data):
    code = data.get('code')
    if code in activation_codes:
        del activation_codes[code]
        emit('code_update', {'codes': get_serializable_codes()}, broadcast=True)
        emit('new_log', {'message': f"🗑️ Revoked key: {code}"}, broadcast=True)

@socketio.on('apply_ban')
def handle_ban(data):
    username = data.get('username', '').strip()
    if username:
        banned_users.add(username)
        sessions_to_kill = [sid for sid, sess in list(active_sessions.items()) if sess['username'] == username]
        for sid in sessions_to_kill:
            if sid in active_sessions:
                del active_sessions[sid]
            
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('session_update', {'sessions': list(active_sessions.values())}, broadcast=True)
        emit('force_logout_user', {'username': username}, broadcast=True)
        emit('new_log', {'message': f"🚫 Blocked user profile: {username}"}, broadcast=True)

@socketio.on('remove_ban')
def handle_unban(data):
    username = data.get('username')
    if username in banned_users:
        banned_users.remove(username)
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('new_log', {'message': f"✅ Restored access: {username}"}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
