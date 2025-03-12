from aiohttp import ClientSession
from urllib.parse import quote_plus
import asyncio
import bencode

user_agent = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0'}

class Tracker:
    def __init__(self, announce_addr):
        self.announce_addr = announce_addr
    
    async def get_peer_list(self, info_hash, peer_id):
        if self.announce_addr.startswith('http'):
            return await self._get_http_peer_list(info_hash, peer_id)
        else: #TODO udp
            raise
    
    async def _get_http_peer_list(self, info_hash, peer_id):
        async with ClientSession(headers=user_agent) as session:
            r = await session.get(
                self.announce_addr + f'?info_hash={quote_plus(info_hash)}',
                params={
                        'peer_id': peer_id,
                        'port': 6881,
                        'uploaded': 0,
                        'downloaded': 0,
                        'left': 2042402026, #TODO
                        # 'compact': 1,
                        'event': 'started',
                        }, )
            answer = bencode.decode(await r.read())
            return answer.get('peers', [])

async def main():
    pass

if __name__ == '__main__':
    asyncio.run(main())
    
