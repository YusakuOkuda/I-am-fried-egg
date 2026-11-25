"""同じLAN内で使う、JSON行プロトコルの協力プレイ通信。"""

import json
import queue
import socket
import threading

DEFAULT_PORT = 47652
MAX_PLAYERS = 8


def local_ip():
    """LAN内の相手へ伝えるIPv4アドレスを調べる。UDP通信自体は送信しない。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def _packet(message):
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


class LanServer:
    """入力を受信し、ホストが作った状態を各参加者へ配信する。"""

    def __init__(self, port=DEFAULT_PORT):
        self.events = queue.Queue()
        self._clients = {}
        self._clients_lock = threading.Lock()
        self._running = threading.Event()
        self._running.set()
        self._next_id = 1
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("0.0.0.0", port))
        self.socket.listen(MAX_PLAYERS - 1)
        self.socket.settimeout(0.5)
        self.port = port
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

    def _accept_loop(self):
        while self._running.is_set():
            try:
                client, address = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._clients_lock:
                if len(self._clients) >= MAX_PLAYERS - 1:
                    client.close()
                    continue
                player_id = f"p{self._next_id}"
                self._next_id += 1
                self._clients[player_id] = {"socket": client, "send_lock": threading.Lock()}
            try:
                with self._clients[player_id]["send_lock"]:
                    client.sendall(_packet({"type": "welcome", "player_id": player_id}))
            except OSError:
                self._remove_client(player_id)
                continue
            self.events.put({"type": "join", "player_id": player_id, "address": address[0]})
            threading.Thread(target=self._read_client, args=(player_id, client), daemon=True).start()

    def _read_client(self, player_id, client):
        buffer = b""
        try:
            while self._running.is_set():
                data = client.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if message.get("type") == "input":
                        move = max(-1, min(1, int(message.get("move", 0))))
                        self.events.put({
                            "type": "input", "player_id": player_id,
                            "move": move, "jump": bool(message.get("jump", False)),
                        })
        except OSError:
            pass
        finally:
            self._remove_client(player_id)

    def _remove_client(self, player_id):
        with self._clients_lock:
            record = self._clients.pop(player_id, None)
        if record:
            try:
                record["socket"].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            record["socket"].close()
            self.events.put({"type": "leave", "player_id": player_id})

    def poll(self):
        messages = []
        while True:
            try:
                messages.append(self.events.get_nowait())
            except queue.Empty:
                return messages

    def broadcast(self, state):
        data = _packet({"type": "state", "state": state})
        with self._clients_lock:
            clients = list(self._clients.items())
        for player_id, record in clients:
            try:
                with record["send_lock"]:
                    record["socket"].sendall(data)
            except OSError:
                self._remove_client(player_id)

    def close(self):
        self._running.clear()
        try:
            self.socket.close()
        except OSError:
            pass
        with self._clients_lock:
            ids = list(self._clients)
        for player_id in ids:
            self._remove_client(player_id)


class LanClient:
    """ホストへ接続し、キー入力を送り、最新のゲーム状態を受け取る。"""

    def __init__(self, host, port=DEFAULT_PORT):
        self.events = queue.Queue()
        self._send_lock = threading.Lock()
        self._running = threading.Event()
        self._running.set()
        self.player_id = None
        self.socket = socket.create_connection((host, port), timeout=8.0)
        self.socket.settimeout(None)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        buffer = b""
        try:
            while self._running.is_set():
                data = self.socket.recv(8192)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    self.events.put(message)
        except OSError:
            pass
        finally:
            self.events.put({"type": "disconnected"})

    def send_input(self, move, jump):
        message = _packet({"type": "input", "move": move, "jump": jump})
        try:
            with self._send_lock:
                self.socket.sendall(message)
            return True
        except OSError:
            return False

    def poll(self):
        latest_state = None
        disconnected = False
        while True:
            try:
                message = self.events.get_nowait()
            except queue.Empty:
                return latest_state, disconnected
            if message.get("type") == "welcome":
                self.player_id = message.get("player_id")
            elif message.get("type") == "state":
                latest_state = message.get("state")
            elif message.get("type") == "disconnected":
                disconnected = True

    def close(self):
        self._running.clear()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()
