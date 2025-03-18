import asyncio
import struct

BLOCK_LENGTH = 2 ** 14 # 16KB

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
    
    async def handshake(self):
        pstrlen = 19
        pstr = b"BitTorrent protocol"
        reserved = 0
        info_hash = self.torrent.info_hash
        peer_id = self.torrent.peer_id
        reader, writer = await asyncio.open_connection(self.ip, self.port)
        message = struct.pack(f'>B{pstrlen}sQ', pstrlen, pstr, reserved) + info_hash + bytes(peer_id, 'utf8')
        writer.write(message)
        await writer.drain()
        print('wrote')
        data = await reader.readexactly(1)
        print(f'Received: {data.decode()!r}')
        data = int.from_bytes(data, 'big')
        newdata = await reader.readexactly(data)
        print('pstr', newdata.decode())
        newdata = await reader.readexactly(8)
        newdata = await reader.readexactly(20)
        peer_id = await reader.readexactly(20)
        if self.torrent.info_hash == newdata:
            self.writer = writer
            self.reader = reader
            self.healthy = True
            self.peer_id = peer_id
        else:
            return False
        
        asyncio.create_task(self._listen())
        
        # print('Close the connection')
        # writer.close()
        # await writer.wait_closed()
    
    async def _listen(self):
        print('entered listen mode')
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
                print(e)
                break
    
    async def _handle_message(self, message_id, payload):
        print('message_id', message_id)
        match message_id:
            case 0: # Choke
                self.am_choking = True
            case 1: # Unchoke
                print('unchoked')
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
                print('received bitfield')
            case 6: # Request
                index, begin, length = struct.unpack('>III', payload)
            case 7: # Piece
                index, begin = struct.unpack('>II', payload[:8])
                block = payload[8:]
                print('recieved from', begin, len(block))
            case 8: # Cancel
                index, begin, length = struct.unpack('>III', payload)
            case 9: # Port
                port = int.from_bytes(payload, 'big')
    
    async def request_piece(self, index):
        if not self.healthy or self.am_choking:
            return False
        if not self.pieces[index]:
            return False
        
        for begin in range(0, self.torrent.piece_length, BLOCK_LENGTH):
            await self._request_block(index, begin, BLOCK_LENGTH)
            print('requested from', begin)
    
    async def _request_block(self, index, begin, length):
        data = struct.pack('>IBIII', 13, 6, index, begin, length)  # <len=13><id=6>
        self.writer.write(data)
        await self.writer.drain()

    async def show_interest(self):
        self.writer.write(struct.pack('>IB', 1, 2)) # <len=1><id=2>
        await self.writer.drain()
    
    async def drop(self):
        print('dropping')
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.healthy = False
