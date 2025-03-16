import asyncio
import struct

class Peer():
    def __init__(self, ip, port, torrent):
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.choked = True
        self.interested = False
    
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
        print(data)
        newdata = await reader.readexactly(int(data))
        print('pstr', newdata.decode())
        newdata = await reader.readexactly(8)
        newdata = await reader.readexactly(20)
        if self.torrent.info_hash == newdata:
            self.writer = writer
            self.reader = reader
        else:
            return False
        
        # print('Close the connection')
        # writer.close()
        # await writer.wait_closed()


