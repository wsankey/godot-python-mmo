import queue
from server import packet
from server import models
from autobahn.twisted.websocket import WebSocketServerProtocol

class GameServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        super().__init__()
        self._packet_queue: queue.Queue[tuple['GameServerProtocol', packet.Packet]] = queue.Queue()
        self._state: callable = None
        self._user: models.User = None

    def LOGIN(self, sender: 'GameServerProtocol', p: packet.Packet):
        if p.action == packet.Action.Login:
            username, password = p.payloads
            if models.User.objects.filter(username=username, password=password).exists():
                self._user = models.User.objects.get(username=username)
                self.send_client(packet.OkPacket())
                self._state = self.PLAY
            else:
                self.send_client(packet.DenyPacket("Username or password incorrect"))

        elif p.action == packet.Action.Register:
            username, password = p.payloads
            if models.User.objects.filter(username=username).exists():
                self.send_client(packet.DenyPacket("This username is already taken"))
            else:
                user = models.User(username=username, password=password)
                user.save()
                self.send_client(packet.OkPacket())

    def PLAY(self, sender: 'GameServerProtocol', p: packet.Packet):
        if p.action == packet.Action.Chat:
            if sender == self:
                self.broadcast(p, exclude_self=True)
            else:
                self.send_client(p)

    def tick(self):
        # Process the next packet in the queue
        if not self._packet_queue.empty():
            s, p = self._packet_queue.get()
            self._state(s, p)

    def broadcast(self, p: packet.Packet, exclude_self: bool = False):
        for other in self.factory.players:
            if other == self and exclude_self:
                continue
            other.onPacket(self, p)

    # Override
    def onConnect(self, request):
        print(f"Client connecting: {request.peer}")

    # Override
    def onOpen(self):
        print(f"Websocket connection open.")
        self._state = self.LOGIN

    # Override
    def onClose(self, wasClean, code, reason):
        self.factory.players.remove(self)
        print(f"Websocket connection closed{' unexpectedly' if not wasClean else ' cleanly'} with code {code}: {reason}")

    # Override
    def onMessage(self, payload, isBinary):
        decoded_payload = payload.decode('utf-8')

        try:
            p: packet.Packet = packet.from_json(decoded_payload)
        except Exception as e:
            print(f"Could not load message as packet: {e}. Message was: {payload.decode('utf8')}")

        self.onPacket(self, p)

    def onPacket(self, sender: 'GameServerProtocol', p: packet.Packet):
        self._packet_queue.put((sender, p))
        print(f"Queued packet: {p}")

    def send_client(self, p: packet.Packet):
        b = bytes(p)
        self.sendMessage(b)
