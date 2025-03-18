import bencode
from tracker import Tracker
import asyncio
from hashlib import sha1
from string import digits, ascii_letters
import random

chars = digits + ascii_letters

class Torrent:
    def __init__(self, torrent_path):
        self.peer_id = ''.join(random.choice(chars) for i in range(20))
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
        self.trackers = [Tracker(addr[0], self) for addr in
                         [[self.torrent_data['announce']]] + self.torrent_data.get('announce-list', [])]
    
    async def _get_peer(self):
        # tasks = asyncio.gather(*[tracker.get_peer_list() for tracker in self.trackers])
        # udp://exodus.desync.com:6969/announce
        # udp://open.stealth.si:80/announce
        # udp://tracker.torrent.eu.org:451/announce
        # udp://tracker.torrent.eu.org:451
        
        tracker = Tracker('udp://open.stealth.si:80/announce', self)
        try:
            print(tracker.announce_addr)
            s = await tracker.get_peer_list()
            print('FOUND',len(s))
            i = 0
            while True:
                print(s[i].ip, s[i].port)
                try:
                    await asyncio.wait_for(s[i].handshake(), 10)
                    break
                except Exception as e:
                    print(e)
                    i += 1
            while True:
                await asyncio.sleep(1)
                


        # except Exception as e:
        #     print(e)
        finally:
            pass


async def main():
    t = Torrent('t.torrent')
    # print(t.torrent_data['announce-list'])
    # tr = Tracker('http://tracker.opentrackr.org/announce')
    # tr = Tracker('udp://tracker2.dler.org:80/announce', t)
    # await tr.get_peer_list(
    await t._get_peer()

if __name__ == '__main__':
    asyncio.run(main())
    