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
        self.trackers = [Tracker(addr[0], self) for addr in
                         [[self.torrent_data['announce']]] + self.torrent_data.get('announce-list', [])]
    
    # async def _get_peer(self):
    #     # tasks = asyncio.gather(*[tracker.get_peer_list() for tracker in self.trackers])
        
    #     for i in self.trackers:
    #         try:
    #             print(i.announce_addr)
    #             s = await i.get_peer_list()
    #             print('FOUND',len(s))
    #         except Exception as e:
    #             print(e)


async def main():
    t = Torrent('t.torrent')
    # print(t.torrent_data['announce-list'])
    # tr = Tracker('http://tracker.opentrackr.org/announce')
    # tr = Tracker('udp://tracker2.dler.org:80/announce', t)
    # await tr.get_peer_list(
    # await t._get_peer()

if __name__ == '__main__':
    asyncio.run(main())
    