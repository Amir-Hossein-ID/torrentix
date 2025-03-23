import aiofiles.os
import bencode
from tracker import Tracker
from peer_manager import PeerManager
import asyncio
from hashlib import sha1
from string import digits, ascii_letters
import random
import aiofiles
import os

chars = digits + ascii_letters

class Torrent:
    def __init__(self, torrent_path, max_peers=15):
        self.peer_id = ''.join(random.choice(chars) for i in range(20))
        self.max_peers = max_peers
        with open(torrent_path, 'rb') as f:
            self.torrent_data = bencode.decode(f.read())
        self.info_hash = sha1(bencode.encode(self.torrent_data['info'])).digest()
        self.piece_length = self.torrent_data['info']['piece length']
        self.total_length = 0
        self.files = []
        if 'files' in self.torrent_data['info']:
            folder = self.torrent_data['info'].get('name', torrent_path[:torrent_path.rfind('.')])
            os.makedirs(folder, exist_ok=True)
            for file in self.torrent_data['info']['files']:
                for i in range(len(file['path']) - 1):
                    os.makedirs(os.path.join(folder, *file['path'][:i+1]), exist_ok=True)
                if not os.path.exists(os.path.join(folder, *file['path'])):
                    open(os.path.join(folder, *file['path']), 'w').close()
                self.files.append({'path': os.path.join(folder, *file['path']), 'length': file['length']})
                self.total_length += file['length']
        else:
            name = self.torrent_data['info'].get('name', torrent_path[:torrent_path.rfind('.')])
            open(name, 'w').close()
            self.files.append({'path': name, 'length': self.torrent_data['info']['length']})
            self.total_length = self.torrent_data['info']['length']
        self.piece_count = (self.total_length + self.piece_length - 1) // self.piece_length
        trackers = [Tracker(addr[0], self) for addr in
                         [[self.torrent_data['announce']]] + self.torrent_data.get('announce-list', [])]
        self.peer_manager = PeerManager(trackers, self, max_peers)
        self.pieces = {i: [(0, self.piece_length)]
                       for i in range(self.piece_count)}
        self.pieces[self.piece_count - 1] = [(0, self.total_length % self.piece_length)]
        self.in_progress = {}
        self.done = []
    
    async def _check_pieces(self):
        cur_piece = 0
        data = b''
        print(self.files)
        for file in self.files:
            async with aiofiles.open(file['path'], 'r+b') as f:
                while True:
                    data += await f.read(self.piece_length - len(data))
                    if len(data) != self.piece_length:
                        break
                    if sha1(data).digest() == self.torrent_data['info']['pieces'][cur_piece * 20: (cur_piece+1) * 20]:
                        print('\033[96m' + 'already got piece', cur_piece, '\033[0m')
                        del self.pieces[cur_piece]
                        self.done.append(cur_piece)
                    # else:
                    #     print('\033[91m' + 'bad hash', cur_piece, '\033[0m')
                    data = b''
                    cur_piece += 1
    
    async def start(self):
        await self._check_pieces()
        asyncio.create_task(self.peer_manager.ensure_peers())
        while self.pieces:
            for i in self.pieces:
                if i in self.in_progress:
                    continue
                await self.peer_manager.wait_ready()
                peer = await self.peer_manager.peer_having_piece(i)
                if peer:
                    print('\033[93m' + 'got peer', i, self.peer_manager.active_peers.__len__(), '\033[0m')
                    piece_corutine = await self.peer_manager.get_piece_from_peer(i, peer, self.piece_length)
                    self.in_progress[i] = asyncio.create_task(self._new_piece(i, piece_corutine))
            for i in self.done:
                self.pieces.pop(i, None)
                self.in_progress.pop(i, None)
    
    async def _new_piece(self, index, piece_corut):
        data = await piece_corut
        # print('\033[92m' + 'new', index)
        #TODO write and check hash
        if sha1(data).digest() == self.torrent_data['info']['pieces'][index * 20: (index+1) * 20]:
            self.done.append(index)
            print('\033[92m' + 'new', index)
            start = self.piece_length * index
            end = start + self.piece_length
            cur = 0
            for file in self.files:
                cur += file['length']
                if start <= cur:
                    async with aiofiles.open(file['path'], 'r+b') as f:
                        await f.seek(start - cur + file['length'])
                        if end > cur + file['length']:
                            await f.write(data[: cur - start])
                            start = cur
                            data = data[cur - start:]
                        else:
                            await f.write(data)
                            break
        else:
            self.in_progress.pop(index, None)
            print('\033[91m' + 'bad hash', index)



async def main():
    t = Torrent('t4.torrent', max_peers=25)
    await t.start()

if __name__ == '__main__':
    asyncio.run(main())
