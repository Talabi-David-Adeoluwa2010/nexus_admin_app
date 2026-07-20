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

# Enhanced for Gevent engine production configurations
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# State Storage (In-Memory Structures)
banned_users = set()
activation_codes = {}
active_sessions = {}

# --- External API Endpoints for Main App Intercommunication ---

@app.route('/api/verify_code', methods=['POST'])
def verify_code():
    data = request.json or {}
    code = data.get('code', '').strip()
    
    if not code or code not in activation_codes:
        return jsonify({"valid": False, "reason": "Invalid or unregistered code."}), 200
    
    details = activation_codes[code]
    current_time = time.time()
    
    if current_time > details['expires_at']:
        del activation_codes[code]
        socketio.emit('code_update', {'codes': get_serializable_codes()})
        socketio.emit('new_log', {'message': f"⚠️ Code {code} expired automatically upon verification attempt."})
        return jsonify({"valid": False, "reason": "This activation code has expired."}), 200
        
    return jsonify({
        "valid": True, 
        "expires_at": details['expires_at'],
        "time_remaining": int(details['expires_at'] - current_time)
    }), 200

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
        sessions_to_kill = [sid for sid, sess in active_sessions.items() if sess['username'] == username]
        for sid in sessions_to_kill:
            del active_sessions[sid]
        socketio.emit('blacklist_update', {'banned': list(banned_users)})
        socketio.emit('session_update', {'sessions': list(active_sessions.values())})
    return jsonify({"success": True}), 200

# --- Web UI Routes ---

@app.route('/')
def admin_portal():
    return render_template('admin_dashboard.html')

# --- Helper Utilities ---

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

# --- Socket Real-Time Controls ---

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
    new_code = "NEXUS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    expiration_timestamp = time.time() + (hours * 3600)
    activation_codes[new_code] = {
        "expires_at": expiration_timestamp,
        "duration_hours": hours
    }
    
    emit('code_update', {'codes': get_serializable_codes()}, broadcast=True)
    emit('new_log', {'message': f"🔑 Code Generated: {new_code} (Valid for {hours} hours)"}, broadcast=True)

@socketio.on('delete_code')
def handle_delete_code(data):
    code = data.get('code')
    if code in activation_codes:
        del activation_codes[code]
        emit('code_update', {'codes': get_serializable_codes()}, broadcast=True)
        emit('new_log', {'message': f"🗑️ Revoked verification token: {code}"}, broadcast=True)

@socketio.on('apply_ban')
def handle_ban(data):
    username = data.get('username', '').strip()
    if username:
        banned_users.add(username)
        
        sessions_to_kill = [sid for sid, sess in active_sessions.items() if sess['username'] == username]
        for sid in sessions_to_kill:
            if sid in active_sessions:
                del active_sessions[sid]
            
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('session_update', {'sessions': list(active_sessions.values())}, broadcast=True)
        emit('force_logout_user', {'username': username}, broadcast=True)
        emit('new_log', {'message': f"🚫 Restricted profile and terminated active sessions: {username}"}, broadcast=True)

@socketio.on('remove_ban')
def handle_unban(data):
    username = data.get('username')
    if username in banned_users:
        banned_users.remove(username)
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('new_log', {'message': f"✅ Restored system access: {username}"}, broadcast=True)

@socketio.on('register_user_session')
def handle_user_session(data):
    username = data.get('username')
    ip_address = data.get('ip', request.remote_addr)
    
    if username:
        active_sessions[request.sid] = {
            "username": username,
            "joined_at": time.strftime('%H:%M:%S', time.localtime()),
            "ip": ip_address
        }
        emit('session_update', {'sessions': list(active_sessions.values())}, broadcast=True)
        emit('new_log', {'message': f"🟢 User joined network: {username} ({ip_address})"}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_sessions:
        user = active_sessions[request.sid]['username']
        del active_sessions[request.sid]
        emit('session_update', {'sessions': list(active_sessions.values())}, broadcast=True)
        emit('new_log', {'message': f"🔴 User exited network: {user}"}, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
