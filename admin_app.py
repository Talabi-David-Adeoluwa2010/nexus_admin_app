from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nexus_admin_super_secret_2026'

# Allow cross-origin requests so your main app and admin app can talk to each other
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory database to keep track of active sessions and blacklisted users
admin_data = {
    "system_status": "Online & Secure",
    "banned_users": ["spammer_account", "test_bad_user"], # Default mock bans
    "logs": [
        {"time": "09:00", "event": "Admin Console Initialized successfully."},
        {"time": "09:15", "event": "Global websocket listener established."}
    ]
}

@app.route('/')
def admin_index():
    return render_template('admin_dashboard.html')

# --- REST APIs for system status & configuration ---
@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "status": admin_data["system_status"],
        "banned_count": len(admin_data["banned_users"]),
        "logs": admin_data["logs"]
    })

@app.route('/api/ban', methods=['POST'])
def ban_user():
    data = request.json or {}
    username = data.get('username')
    if username:
        if username not in admin_data["banned_users"]:
            admin_data["banned_users"].append(username)
            admin_data["logs"].append({"time": "Just Now", "event": f"User '{username}' was successfully blacklisted."})
            # Emit globally to update any connected admin interface screens
            socketio.emit('admin_log_update', {"event": f"BANNED: {username}"})
            return jsonify({"success": True, "message": f"User {username} has been blacklisted."})
        return jsonify({"success": False, "message": "User is already blacklisted."})
    return jsonify({"success": False, "message": "Invalid username specified."})

@app.route('/api/unban', methods=['POST'])
def unban_user():
    data = request.json or {}
    username = data.get('username')
    if username in admin_data["banned_users"]:
        admin_data["banned_users"].remove(username)
        admin_data["logs"].append({"time": "Just Now", "event": f"User '{username}' was unbanned."})
        socketio.emit('admin_log_update', {"event": f"UNBANNED: {username}"})
        return jsonify({"success": True, "message": f"User {username} is now unbanned."})
    return jsonify({"success": False, "message": "User was not blacklisted."})

# --- SOCKET EVENTS ---
@socketio.on('connect')
def admin_connect():
    print("An administrative console session connected.")
    emit('system_init', {
        "status": admin_data["system_status"],
        "banned": admin_data["banned_users"]
    })

if __name__ == '__main__':
    # Runs on port 5001 so it doesn't conflict with the main app on port 5000!
    socketio.run(app, debug=True, port=5001)
