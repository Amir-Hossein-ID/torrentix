import asyncio
from hashlib import sha1
import random
import os
import pickle

import aiofiles
from tqdm import tqdm

import torrentix.bencode as bencode
from torrentix.tracker import Tracker
from torrentix.peer_manager import PeerManager

from string import digits, ascii_letters
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
    
    def _check_pieces(self):
        if os.path.isfile(f'{self.info_hash.hex()}.torrentix'):
            with open(f'{self.info_hash.hex()}.torrentix', 'rb') as f:
                self.pieces, self.done = pickle.load(f)
            if self.piece_count - 1 in self.done:
                new_value = self.total_length % self.piece_length + self.piece_length * (len(self.done) - 1)
            else:
                new_value = self.piece_length * len(self.done)
            self.progress_bar.n = new_value
            self.progress_bar.last_print_n = new_value
            self.progress_bar.refresh()
            self._update_progress_bar()
        # cur_piece = 0
        # data = b''
        # for file in self.files:
        #     async with aiofiles.open(file['path'], 'r+b') as f:
        #         # await f.truncate(file['length'])
        #         while True:
        #             data += await f.read(self.piece_length - len(data))
        #             if len(data) != self.piece_length:
        #                 break
        #             if sha1(data).digest() == self.torrent_data['info']['pieces'][cur_piece * 20: (cur_piece+1) * 20]:
        #                 # print('\033[96m' + 'already got piece', cur_piece, '\033[0m')
        #                 del self.pieces[cur_piece]
        #                 self.done.append(cur_piece)
        #                 self.progress_bar.update(self.piece_length)
        #                 self._update_progress_bar()
        #             data = b''
        #             cur_piece += 1
        # if sha1(data).digest() == self.torrent_data['info']['pieces'][cur_piece * 20: (cur_piece+1) * 20]:
        #     # print('\033[96m' + 'already got piece', cur_piece, '\033[0m')
        #     del self.pieces[cur_piece]
        #     self.done.append(cur_piece)
        #     self.progress_bar.update(len(data))
        #     self._update_progress_bar()
    
    def _update_pieces(self):
        with open(f'{self.info_hash.hex()}.torrentix', 'wb') as f:
            pickle.dump((self.pieces, self.done), f)
    
    def _update_progress_bar(self):
        self.progress_bar.set_description(f'Peers {len(self.peer_manager.active_peers)} / {self.max_peers}'
                                               f' | Pieces {len(self.done)} / {self.piece_count} ')
    
    async def start(self):
        self.progress_bar = tqdm(total=self.total_length, 
                                 unit='B', unit_scale=True, 
                                 desc=f'Peers 0 / {self.max_peers} Pieces 0 / {self.piece_count} ',
                                 ncols=90)
        self._check_pieces()
        # print('REMAINING', len(self.pieces), 'from', self.piece_count)
        asyncio.create_task(self.peer_manager.ensure_peers())
        while self.pieces:
            for i in self.pieces:
                if i in self.in_progress and len(self.pieces) != len(self.in_progress):
                    continue
                await self.peer_manager.wait_ready()
                peer = await self.peer_manager.peer_having_piece(i)
                if peer:
                    # print('\033[93m' + 'got peer', i, self.peer_manager.active_peers.__len__(), '\033[0m')
                    piece_corutine = await self.peer_manager.get_piece_from_peer(i, peer, self.pieces[i][-1][1])
                    self.in_progress[i] = asyncio.create_task(self._new_piece(i, piece_corutine))
                    self._update_progress_bar()
            for i in self.done:
                self.pieces.pop(i, None)
                self.in_progress.pop(i, None)
            await self.peer_manager.remove_peers_not_having_piece(self.pieces.keys())
    
    async def _new_piece(self, index, piece_corut):
        try:
            data = await asyncio.wait_for(piece_corut, 60) #TODO: pieces timeout
            # print('\033[92m' + 'new', index)
            if sha1(data).digest() == self.torrent_data['info']['pieces'][index * 20: (index+1) * 20]:
                # print('\033[92m' + 'new', index, '\033[0m')
                start = self.piece_length * index
                end = start + len(data)
                cur = 0
                for file in self.files:
                    cur += file['length']
                    if start <= cur:
                        async with aiofiles.open(file['path'], 'r+b') as f:
                            await f.seek(start - cur + file['length'])
                            if end > cur:
                                await f.write(data[: cur - start])
                                data = data[cur - start:]
                                start = cur
                            else:
                                await f.write(data)
                                break
                self.done.append(index)
                self.progress_bar.update(len(data))
                self._update_pieces()
                self._update_progress_bar()
            else:
                self.in_progress.pop(index, None)
                # self.progress_bar.update(len(data))
                # print('\033[91m' + 'bad hash', index, '\033[0m')
        except asyncio.TimeoutError:
            self.in_progress.pop(index, None)
