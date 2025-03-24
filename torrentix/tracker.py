import asyncio
import struct
import random
from urllib.parse import quote_plus, urlparse

from aiohttp import ClientSession

import bencode
from peer import Peer

TRACKER_TIMEOUT = 15

user_agent = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0'}

class Tracker:
    def __init__(self, announce_addr, torrent):
        self.torrent = torrent
        self.announce_addr = announce_addr
        self.peer_list = []
    
    async def get_peer_list(self):
        if self.announce_addr.startswith('http'):
            return await self._get_http_peer_list()
        elif self.announce_addr.startswith('udp'):
            # print('calling udp')
            return await self._get_udp_peer_list()
        else:
            raise NotImplementedError('Unsupported protocol')
    
    async def _get_udp_peer_list(self):
        loop = asyncio.get_running_loop()
        on_con_lost = loop.create_future()
        host, port = urlparse(self.announce_addr).netloc.split(':')
        # print(host, port)
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UdpTrackerProtocol(self, on_con_lost),
            remote_addr=(host, port))

        try:
            await asyncio.wait_for(on_con_lost, TRACKER_TIMEOUT)
        finally:
            transport.close()
        # print('reel peers', len(self.peer_list))
        return self.peer_list
        
    async def _get_http_peer_list(self):
        async with ClientSession(headers=user_agent) as session:
            r = await session.get(
                self.announce_addr + f'?info_hash={quote_plus(self.torrent.info_hash)}',
                params={
                        'peer_id': self.torrent.peer_id,
                        'port': 6881,
                        'uploaded': 0,
                        'downloaded': 0,
                        'left': self.torrent.total_length,
                        # 'compact': 1, #TODO
                        'event': 'started',
                        }, 
                timeout=TRACKER_TIMEOUT) #TODO
            answer = bencode.decode(await r.read())
            self.peer_list = answer.get('peers', [])
            if isinstance(self.peer_list, bytes):
                self.peer_list = self.bytes_to_peers(self.peer_list)
            else:
                self.peer_list = [Peer(peer['ip'], peer['port'], self.torrent) for peer in self.peer_list]
            return self.peer_list
    
    def bytes_to_peers(self, data):
        while data:
            *ip, port = struct.unpack('>BBBBH', data[:6])
            self.peer_list.append(Peer('.'.join(str(i) for i in ip), port, self.torrent))
            data = data[6:]

class _UdpTrackerProtocol:
    def __init__(self, tracker: Tracker, on_con_lost):
        self.tracker = tracker
        self.on_con_lost = on_con_lost
        self.state = 'connection'
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self._send_connection_request()

    def datagram_received(self, data, addr):
        if self.state == 'connection':
            if len(data) < 16:
                # print('Invalid data received')
                return
            action, transaction_id, connection_id = struct.unpack('>IIQ', data[:16])
            if action == 0 and transaction_id == self.transaction_id:
                # print('connection response received')
                self._send_announce_request(connection_id)
        elif self.state == 'announce':
            if len(data) < 20:
                # print('Invalid data received')
                return
            action, transaction_id, interval, leechers, seeders = struct.unpack('>IIIII', data[:20])
            if action == 1 and transaction_id == self.transaction_id:
                # print('announce response received')
                # print('interval:', interval)
                # print('leechers:', leechers)
                # print('seeders:', seeders)
                data = data[20:]

                self.tracker.bytes_to_peers(data)

            self.on_con_lost.set_result(True)
        else:
            pass
            # print('Invalid action or transaction_id')

        self.data = data
    
    def eof_received(self):
        pass
        # print("EOF received")

    def error_received(self, exc):
        pass
        # print('Error received:', exc)

    def connection_lost(self, exc):
        pass
        # print("Connection closed")
    
    def _send_connection_request(self):
        # print('sending connection request')
        self.transaction_id = random.randint(0, 0xFFFFFFFF)
        connection_request = struct.pack('>QII',
                                         0x41727101980, # protocol_id, magic constant
                                         0, # action, connect
                                         self.transaction_id)
        self.transport.sendto(connection_request)
    
    def _send_announce_request(self, connection_id):
        # print('sending announce request')
        self.state = 'announce'
        self.transaction_id = random.randint(0, 0xFFFFFFFF)
        info_hash = self.tracker.torrent.info_hash
        announce_request = struct.pack('>QII20s20sQQQiiiiH',
                                        connection_id,
                                        1, # action, announce
                                        self.transaction_id,
                                        info_hash,
                                        self.tracker.torrent.peer_id.encode(),
                                        0, # downloaded
                                        self.tracker.torrent.total_length, # left
                                        0, # uploaded
                                        2, # event, started
                                        0, # ip
                                        90, # key
                                        -1, # num_want
                                        6881, # port
                                        )
        self.transport.sendto(announce_request)

async def main():
    pass

if __name__ == '__main__':
    asyncio.run(main())
    
