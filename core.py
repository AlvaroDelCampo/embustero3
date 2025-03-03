import random, string, json, os
from flask import render_template, request, redirect, url_for, session
from flask_socketio import emit, disconnect, join_room, leave_room
from words import words_pool  # Lista de 100 palabras


def generate_room_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase, k=length))

# Funciones para obtener y actualizar el estado de la sala en Redis

def get_room(room_id):
    data = redis_client.get("room:" + room_id)
    if data:
        return json.loads(data)
    return None

def set_room(room_id, room_data):
    redis_client.set("room:" + room_id, json.dumps(room_data))

def initialize_app(app, socketio):
    @app.route("/", methods=["GET", "POST"])
    def index():
        error = None
        if request.method == "POST":
            alias = request.form.get("alias")
            room = request.form.get("room")
            if not alias:
                error = "El alias es requerido."
                return render_template("index.html", error=error)
            if not room:
                room = generate_room_id()
            # Si la sala ya existe, se verifica que el alias no se use
            room_data = get_room(room)
            if room_data:
                for player in room_data["players"].values():
                    if player["alias"].lower() == alias.lower():
                        error = "El alias ya existe en la sala."
                        break
            if error:
                return render_template("index.html", error=error)
            session["alias"] = alias
            session["room"] = room
            if not room_data:
                room_data = {"players": {}, "game_data": {}}
            set_room(room, room_data)
            return redirect(url_for("room_view", room_id=room))
        return render_template("index.html", error=error)
    
    @app.route("/room/<room_id>")
    def room_view(room_id):
        if "alias" not in session or "room" not in session or session["room"] != room_id:
            return redirect(url_for("index"))
        return render_template("room.html", room_id=room_id)
    
    # ---------------------------
    # Eventos de Socket.IO
    # ---------------------------
    
    @socketio.on("connect")
    def handle_connect():
        from flask import request
        alias = session.get("alias")
        room_id = session.get("room")
        if not alias or not room_id:
            return False
        join_room(room_id)
        room_data = get_room(room_id)
        if not room_data:
            room_data = {"players": {}, "game_data": {}}
        # Agrega el jugador con su request.sid
        room_data["players"][request.sid] = {"alias": alias, "ready": False, "repartir": False}
        set_room(room_id, room_data)
        update_players_list(room_id)
    
    @socketio.on("disconnect")
    def handle_disconnect():
        from flask import request
        room_id = session.get("room")
        room_data = get_room(room_id)
        if room_id and room_data and request.sid in room_data["players"]:
            del room_data["players"][request.sid]
            set_room(room_id, room_data)
            leave_room(room_id)
            update_players_list(room_id)
            update_repartir_status(room_id)
    
    @socketio.on("player_ready")
    def handle_player_ready():
        from flask import request
        room_id = session.get("room")
        room_data = get_room(room_id)
        if not room_id or not room_data:
            return
        if request.sid in room_data["players"]:
            room_data["players"][request.sid]["ready"] = True
        set_room(room_id, room_data)
        if "words" in room_data["game_data"] and room_data["game_data"].get("words"):
            game_data = room_data["game_data"]
            players_list = [{"alias": p["alias"], "repartir": p.get("repartir", False)}
                            for p in room_data["players"].values()]
            if request.sid == game_data["impostor"]:
                words = ["impostor"] * 10
            else:
                words = game_data["words"]
            emit("start_game", {
                "words": words,
                "players": players_list,
                "impostor": room_data["players"][game_data["impostor"]]["alias"]
            }, room=request.sid)
            update_repartir_status(room_id)
        else:
            if room_data["players"] and all(p["ready"] for p in room_data["players"].values()):
                start_game(room_id)
            else:
                update_players_list(room_id)
    
    @socketio.on("toggle_repartir")
    def handle_toggle_repartir():
        from flask import request
        room_id = session.get("room")
        room_data = get_room(room_id)
        if not room_id or not room_data:
            return
        if request.sid in room_data["players"]:
            current = room_data["players"][request.sid].get("repartir", False)
            room_data["players"][request.sid]["repartir"] = not current
        set_room(room_id, room_data)
        update_repartir_status(room_id)
        if room_data["players"] and all(p.get("repartir", False) for p in room_data["players"].values()):
            start_game(room_id)
    
    @socketio.on("salir")
    def handle_salir():
        from flask import request
        room_id = session.get("room")
        room_data = get_room(room_id)
        if room_id and room_data and request.sid in room_data["players"]:
            del room_data["players"][request.sid]
            set_room(room_id, room_data)
            leave_room(room_id)
            update_players_list(room_id)
            update_repartir_status(room_id)
        disconnect()
    
    # ---------------------------
    # Funciones de Utilidad
    # ---------------------------
    
    def update_players_list(room_id):
        room_data = get_room(room_id)
        if room_data:
            players_list = [{"alias": p["alias"], "ready": p.get("ready", False)}
                            for p in room_data["players"].values()]
            socketio.emit("update_players", {"players": players_list}, room=room_id)
    
    def update_repartir_status(room_id):
        room_data = get_room(room_id)
        if room_data:
            players_status = [{"alias": p["alias"], "repartir": p.get("repartir", False)}
                              for p in room_data["players"].values()]
            socketio.emit("update_repartir", {"players": players_status}, room=room_id)
    
    def start_game(room_id):
        room_data = get_room(room_id)
        if not room_data or not room_data["players"]:
            return
        random_words = random.sample(words_pool, 10)
        impostor_sid = random.choice(list(room_data["players"].keys()))
        room_data["game_data"] = {"words": random_words, "impostor": impostor_sid}
        set_room(room_id, room_data)
        players_list = []
        for p in room_data["players"].values():
            p["ready"] = False
            p["repartir"] = False
            players_list.append({"alias": p["alias"], "repartir": False})
        for sid, p in room_data["players"].items():
            words_to_send = ["impostor"] * 10 if sid == impostor_sid else random_words
            socketio.emit("start_game", {
                "words": words_to_send,
                "players": players_list,
                "impostor": room_data["players"][impostor_sid]["alias"]
            }, room=sid)
        update_repartir_status(room_id)
