from flask import Flask
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, manage_session=False)

# Importa y ejecuta la inicialización del core (rutas y eventos)
import core
core.initialize_app(app, socketio)

if __name__ == "__main__":
    socketio.run(app, debug=True)
