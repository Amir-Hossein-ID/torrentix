import asyncio
import struct

HANDSHAKE_TIMEOUT = 15
KEEP_ALIVE_TIMEOUT = 60

class Peer():
    def __init__(self, ip, port, torrent):
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.healthy = False
        self.pieces = [False] * torrent.piece_count
        self.peer_id = None
        self.writer = None
        self.reader = None
        self.last_active = 0
        self.keep_alive_task = None
        self.events = {}
    
    async def handshake(self):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = 0
        info_hash = self.torrent.info_hash
        peer_id = self.torrent.peer_id
        message = struct.pack(f'>B{pstrlen}sQ', pstrlen, pstr, reserved) + info_hash + bytes(peer_id, 'utf8')

        async def handle_handshake():
            reader, writer = await asyncio.open_connection(self.ip, self.port)
            writer.write(message)
            await writer.drain()
            # print('wrote')
            data = await reader.readexactly(1)
            # print(f'Received: {data.decode()!r}')
            data = int.from_bytes(data, 'big')
            newdata = await reader.readexactly(data)
            # print('pstr', newdata.decode())
            newdata = await reader.readexactly(8)
            newdata = await reader.readexactly(20)
            peer_id = await reader.readexactly(20)
            self.peer_id = peer_id
            self.writer = writer
            self.reader = reader

            return info_hash
        if self.torrent.info_hash != (await asyncio.wait_for(handle_handshake(), timeout=HANDSHAKE_TIMEOUT)):
            return False

        self.healthy = True
        self.last_active = asyncio.get_event_loop().time()
        #TODO: gives error
        # self.keep_alive_task = asyncio.get_event_loop().call_later(KEEP_ALIVE_TIMEOUT, asyncio.create_task, self.keep_alive())
        # print('after schedule')
        asyncio.create_task(self._listen())
        return True
        
        # print('Close the connection')
        # writer.close()
        # await writer.wait_closed()
    
    async def _listen(self):
        # print('entered listen mode')
        while self.healthy:
            try:
                data = await self.reader.readexactly(4)
                length = int.from_bytes(data, 'big')
                if length == 0: # Keep alive
                    continue

                data = await self.reader.readexactly(1)
                message_id = int.from_bytes(data, 'big')

                length -= 1

                payload = await self.reader.readexactly(length)
                await self._handle_message(message_id, payload)
            except Exception as e:
                # print('exception in listen', e, type(e))
                await self.drop()
                break
    
    async def _handle_message(self, message_id, payload):
        # print('message_id', message_id)
        match message_id:
            case 0: # Choke
                self.am_choking = True
            case 1: # Unchoke
                # print('unchoked')
                if 'unchoked' in self.events:
                    self.events['unchoked'].set()
                    del self.events['unchoked']
                self.am_choking = False
            case 2: # Interested
                self.peer_interested = True
            case 3: # NotInterested
                self.peer_interested = False
            case 4: # Have
                has_index = int.from_bytes(payload, 'big')
                self.pieces[has_index] = True
            case 5: # Bitfield
                if len(payload) != ((self.torrent.piece_count + 8 - 1) // 8):
                    await self.drop()
                    return
                
                index = 0
                for byte in payload:
                    have = bin(byte)[2:]
                    for bit in have:
                        if bit == '1':
                            if index < len(self.pieces):
                                self.pieces[index] = True
                            else:
                                # some error happend
                                await self.drop()
                        index += 1
                # print('received bitfield')
            case 6: # Request
                index, begin, length = struct.unpack('>III', payload)
            case 7: # Piece
                index, begin = struct.unpack('>II', payload[:8])
                block = payload[8:]
                # print(index, begin, self.events)
                if (index, begin) in self.events:
                    self.events[index, begin].set_result(block)
                    del self.events[index, begin]
                # await self.torrent.new_block(index, begin, block)
            case 8: # Cancel
                index, begin, length = struct.unpack('>III', payload)
            case 9: # Port
                port = int.from_bytes(payload, 'big')
    
    async def request_block(self, index, begin, length, event:asyncio.Future=None):
        try:
            self.last_active = asyncio.get_event_loop().time()
            # self.keep_alive_task.cancel()
            if event:
                self.events[index, begin] = event
            data = struct.pack('>IBIII', 13, 6, index, begin, length)  # <len=13><id=6>
            self.writer.write(data)
            await self.writer.drain()
            # self.keep_alive_task = asyncio.get_event_loop().call_later(KEEP_ALIVE_TIMEOUT, asyncio.create_task, self.keep_alive())
        except Exception as e:
            await self.drop()

    async def show_interest(self, event:asyncio.Event=None):
        try:
            self.last_active = asyncio.get_event_loop().time()
            # self.keep_alive_task.cancel()
            if event:
                self.events['unchoked'] = event
            self.writer.write(struct.pack('>IB', 1, 2)) # <len=1><id=2>
            await self.writer.drain()
            # self.keep_alive_task = asyncio.get_event_loop().call_later(KEEP_ALIVE_TIMEOUT, asyncio.create_task, self.keep_alive())
        except Exception as e:
            await self.drop()
    
    async def keep_alive(self):
        self.last_active = asyncio.get_event_loop().time()
        # self.keep_alive_task.cancel()
        try:
            self.writer.write(struct.pack('>I', 0)) # <len=0>
            await self.writer.drain()
        except Exception as e:
            self.healthy = False
            return
        # self.keep_alive_task = asyncio.get_event_loop().call_later(KEEP_ALIVE_TIMEOUT, asyncio.create_task, self.keep_alive())
    
    async def drop(self):
        # print('dropping')
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
        for i in self.events:
            if i != 'unchoked':
                self.events[i].set_result(b'')
                # TODO: set_exception
        self.events = {}
        self.healthy = False

    def is_busy(self):
        return bool(self.events)
