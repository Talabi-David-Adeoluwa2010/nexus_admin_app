import random
import string
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_super_secret_key_9988'
socketio = SocketIO(app, cors_allowed_origins="*")

# State Storage (In-Memory)
banned_users = set()
# Format: {"NEXUS-CODE": {"expires_at": timestamp, "duration_hours": float}}
activation_codes = {}
# Format: {"session_id": {"username": str, "joined_at": timestamp, "ip": str}}
active_sessions = {}

# --- External API Endpoints for your Main App to talk to ---

@app.route('/api/verify_code', methods=['POST'])
def verify_code():
    data = request.json or {}
    code = data.get('code', '').strip()
    
    if not code or code not in activation_codes:
        return jsonify({"valid": False, "reason": "Invalid or unregistered code."}), 400
    
    details = activation_codes[code]
    current_time = time.time()
    
    if current_time > details['expires_at']:
        # Automatically clean up expired code
        del activation_codes[code]
        socketio.emit('code_update', {'codes': get_serializable_codes()})
        socketio.emit('new_log', {'message': f"⚠️ Code {code} expired automatically upon verification attempt."})
        return jsonify({"valid": False, "reason": "This activation code has expired."}), 400
        
    return jsonify({
        "valid": True, 
        "expires_at": details['expires_at'],
        "time_remaining": int(details['expires_at'] - current_time)
    }), 200

@app.route('/api/check_ban/<username>', methods=['GET'])
def check_ban(username):
    is_banned = username.strip() in banned_users
    return jsonify({"banned": is_banned}), 200

# --- Web UI Routes ---

@app.route('/')
def admin_portal():
    return render_template('admin_dashboard.html')

# --- Helper Utilities ---

def get_serializable_codes():
    """Formates codes safely with remaining time calculations for the UI."""
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
            
    # Clean up expired entries in-memory
    for code in expired_to_clean:
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
        
        # Disconnect active session if they are online
        sessions_to_kill = [sid for sid, sess in active_sessions.items() if sess['username'] == username]
        for sid in sessions_to_kill:
            del active_sessions[sid]
            
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('session_update', {'sessions': list(active_sessions.values())}, broadcast=True)
        # Notify the main app to instantly boot this user
        emit('force_logout_user', {'username': username}, broadcast=True)
        emit('new_log', {'message': f"🚫 Restricted profile and terminated active sessions: {username}"}, broadcast=True)

@socketio.on('remove_ban')
def handle_unban(data):
    username = data.get('username')
    if username in banned_users:
        banned_users.remove(username)
        emit('blacklist_update', {'banned': list(banned_users)}, broadcast=True)
        emit('new_log', {'message': f"✅ Restored system access: {username}"}, broadcast=True)

# --- Active Directory Synchronization (Triggered by Main App via Sockets) ---

@socketio.on('register_user_session')
def handle_user_session(data):
    username = data.get('username')
    ip_address = data.get('ip', request.remote_addr)
    
    if username:
        # Save session mapped to socket session ID
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
    socketio.run(app, debug=True)
