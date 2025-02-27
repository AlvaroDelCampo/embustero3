import random, string
from flask import render_template, request, redirect, url_for, session
from flask_socketio import emit, disconnect, join_room, leave_room
from words import words_pool  # Importa la lista de palabras
# Diccionario global para almacenar las salas
rooms = {}

def generate_room_id(length=6):
    return ''.join(random.choices(string.ascii_uppercase, k=length))

def initialize_app(app, socketio):
    # Rutas HTTP
    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            alias = request.form.get("alias")
            room = request.form.get("room")
            if not alias:
                return redirect(url_for("index"))
            if not room:
                room = generate_room_id()
            session["alias"] = alias
            session["room"] = room
            if room not in rooms:
                rooms[room] = {"players": {}, "game_data": {}}
            # Aquí usamos el endpoint 'room_view'
            return redirect(url_for("room_view", room_id=room))
        return render_template("index.html")
    
    @app.route("/room/<room_id>")
    def room_view(room_id):
        if "alias" not in session or "room" not in session or session["room"] != room_id:
            return redirect(url_for("index"))
        return render_template("room.html", room_id=room_id)

    # Eventos de SocketIO
    @socketio.on("connect")
    def handle_connect():
        alias = session.get("alias")
        room_id = session.get("room")
        if not alias or not room_id:
            return False
        join_room(room_id)
        if room_id not in rooms:
            rooms[room_id] = {"players": {}, "game_data": {}}
        rooms[room_id]["players"][request.sid] = {"alias": alias, "ready": False, "repartir": False}
        update_players_list(room_id)
    
    @socketio.on("disconnect")
    def handle_disconnect():
        room_id = session.get("room")
        if room_id and room_id in rooms and request.sid in rooms[room_id]["players"]:
            del rooms[room_id]["players"][request.sid]
            leave_room(room_id)
            update_players_list(room_id)
            update_repartir_status(room_id)
    
    @socketio.on("player_ready")
    def handle_player_ready():
        room_id = session.get("room")
        if not room_id or room_id not in rooms:
            return
        if request.sid in rooms[room_id]["players"]:
            rooms[room_id]["players"][request.sid]["ready"] = True
        if "words" in rooms[room_id]["game_data"] and rooms[room_id]["game_data"].get("words"):
            game_data = rooms[room_id]["game_data"]
            players_list = [{"alias": p["alias"], "repartir": p.get("repartir", False)}
                            for p in rooms[room_id]["players"].values()]
            if request.sid == game_data["impostor"]:
                words = ["impostor"] * 10
            else:
                words = game_data["words"]
            emit("start_game", {
                "words": words,
                "players": players_list,
                "impostor": rooms[room_id]["players"][game_data["impostor"]]["alias"]
            }, room=request.sid)
            update_repartir_status(room_id)
        else:
            if rooms[room_id]["players"] and all(p["ready"] for p in rooms[room_id]["players"].values()):
                start_game(room_id)
            else:
                update_players_list(room_id)
    
    @socketio.on("toggle_repartir")
    def handle_toggle_repartir():
        room_id = session.get("room")
        if not room_id or room_id not in rooms:
            return
        if request.sid in rooms[room_id]["players"]:
            current = rooms[room_id]["players"][request.sid].get("repartir", False)
            rooms[room_id]["players"][request.sid]["repartir"] = not current
        update_repartir_status(room_id)
        if rooms[room_id]["players"] and all(p.get("repartir", False) for p in rooms[room_id]["players"].values()):
            start_game(room_id)
    
    @socketio.on("salir")
    def handle_salir():
        room_id = session.get("room")
        if room_id and room_id in rooms and request.sid in rooms[room_id]["players"]:
            del rooms[room_id]["players"][request.sid]
            leave_room(room_id)
            update_players_list(room_id)
            update_repartir_status(room_id)
        disconnect()
    
    # Funciones de utilidad internas
    def update_players_list(room_id):
        if room_id in rooms:
            players_list = [{"alias": p["alias"], "ready": p.get("ready", False)}
                            for p in rooms[room_id]["players"].values()]
            socketio.emit("update_players", {"players": players_list}, room=room_id)
    
    def update_repartir_status(room_id):
        if room_id in rooms:
            players_status = [{"alias": p["alias"], "repartir": p.get("repartir", False)}
                              for p in rooms[room_id]["players"].values()]
            socketio.emit("update_repartir", {"players": players_status}, room=room_id)
    
    def start_game(room_id):
        if room_id not in rooms or not rooms[room_id]["players"]:
            return
        random_words = random.sample(words_pool, 10)
        impostor_sid = random.choice(list(rooms[room_id]["players"].keys()))
        rooms[room_id]["game_data"] = {"words": random_words, "impostor": impostor_sid}
        players_list = []
        for p in rooms[room_id]["players"].values():
            p["ready"] = False
            p["repartir"] = False
            players_list.append({"alias": p["alias"], "repartir": False})
        for sid, p in rooms[room_id]["players"].items():
            if sid == impostor_sid:
                words = ["impostor"] * 10
            else:
                words = random_words
            socketio.emit("start_game", {
                "words": words,
                "players": players_list,
                "impostor": rooms[room_id]["players"][impostor_sid]["alias"]
            }, room=sid)
        update_repartir_status(room_id)
