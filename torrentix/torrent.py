import bencode
from tracker import Tracker
from peer_manager import PeerManager
import asyncio
from hashlib import sha1
from string import digits, ascii_letters
import random
from bisect import bisect

chars = digits + ascii_letters

class Torrent:
    def __init__(self, torrent_path, max_peers=15):
        self.peer_id = ''.join(random.choice(chars) for i in range(20))
        self.max_peers = max_peers
        with open(torrent_path, 'rb') as f:
            self.torrent_data = bencode.decode(f.read())
        self.info_hash = sha1(bencode.encode(self.torrent_data['info'])).digest()
        self.piece_length = self.torrent_data['info']['piece length']
        if 'files' in self.torrent_data['info']:
            self.multi_file = True
            self.total_length = sum(i['length'] for i in self.torrent_data['info']['files'])
        else:
            self.multi_file = False
            self.total_length = self.torrent_data['info']['length']
        self.piece_count = (self.total_length + self.piece_length - 1) // self.piece_length
        trackers = [Tracker(addr[0], self) for addr in
                         [[self.torrent_data['announce']]] + self.torrent_data.get('announce-list', [])]
        self.peer_manager = PeerManager(trackers, self, max_peers)
        # self.pieces = {i: (i * self.piece_length, min((i+1) * self.piece_length, self.total_length))
        #                for i in range(self.piece_count)}
        self.pieces = {i: [(0, self.piece_length)]
                       for i in range(self.piece_count)}
        self.pieces[self.piece_count - 1] = [(0, self.total_length % self.piece_length)]
        self.in_progress = {}
        self.done = []
    
    async def start(self):
        asyncio.create_task(self.peer_manager.ensure_peers())
        in_progress_pieces = {}
        while self.pieces:
            for i in self.pieces:
                if i in in_progress_pieces:
                    continue
                await self.peer_manager.wait_ready()
                peer = await self.peer_manager.peer_having_piece(i)
                if peer:
                    print('\033[93m' + 'got peer', i, '\033[0m')
                    piece_corutine = await self.peer_manager.get_piece_from_peer(i, peer, self.piece_length)
                    in_progress_pieces[i] = asyncio.create_task(self.new_piece(i, piece_corutine))
            for i in self.done:
                self.pieces.pop(i, None)
                in_progress_pieces.pop(i, None)
    
    async def new_piece(self, index, piece_corut):
        data = await piece_corut
        print('\033[92m' + 'new', index)
        # remove the recieved part from self.pieces
        self.done.append(index)
        #TODO write and check hash


async def main():
    t = Torrent('t4.torrent', max_peers=25)
    await t.start()

if __name__ == '__main__':
    asyncio.run(main())
