import asyncio
import random

BLOCK_LENGTH = 2**14 # 16KB
UNCHOKE_TIMEOUT = 5
MAX_TRACKERS = 10

class PeerManager:
    def __init__(self, trackers, torrent, max_conn):
        self.trackers = trackers
        self.torrent = torrent
        self.max_peers = max_conn
        self.tracker_semaphore = asyncio.Semaphore(MAX_TRACKERS)
        self.peers = asyncio.Queue()
        self.active_peers = []
        self.is_ready = asyncio.Event()
        self.peers_semaphore = asyncio.Semaphore(max_conn)
    
    async def wait_ready(self):
        print('waiting for peers')
        await self.is_ready.wait()
        print('wait ended')
    
    async def check_ready(self):
        for i in self.active_peers:
            if not i.is_busy():
                self.is_ready.set()
        self.is_ready.clear()
    
    async def capture_peers(self):
        for tracker in self.trackers:
            asyncio.create_task(self.add_peers(tracker))
    
    async def add_peers(self, tracker):
        async with self.tracker_semaphore:
            try:
                peers = await tracker.get_peer_list()
                for peer in peers:
                    await self.peers.put(peer)
            except Exception as e:
                print('error capturing from tracker', e, type(e))
    
    async def ensure_peers(self):
        await self.capture_peers()
        while True:
            await self.peers_semaphore.acquire() # so we dont get more than "max_conn" peers at the same time
            peer = await self.peers.get()
            asyncio.create_task(self.check_peer(peer))
    
    async def check_peer(self, peer):
        try:
            await peer.handshake()
            if peer.healthy:
                event = asyncio.Event()
                await peer.show_interest(event)
                await asyncio.wait_for(event.wait(), timeout=UNCHOKE_TIMEOUT)
                self.active_peers.append(peer)
                await self.check_ready()
        except Exception as e:
            print('error handshaking with peer', e, type(e))
            await peer.drop()
            self.peers_semaphore.release()
    
    async def remove_peer(self, peer):
        self.active_peers.remove(peer)
        self.peers_semaphore.release()
        await self.check_ready()
    
    async def peer_having_piece(self, index):
        peers = []
        for peer in self.active_peers:
            if peer.healthy and not peer.am_choking and not peer.is_busy() and peer.pieces[index]:
                peers.append(peer)
        if peers:
            return random.choice(peers)
        return None
    
    async def get_piece_from_peer(self, index, peer, piece_length):
        futures = []
        for begin in range(0, piece_length, BLOCK_LENGTH):
            future = asyncio.Future()
            if begin + BLOCK_LENGTH > piece_length:
                peer.request_block(index, begin, piece_length - begin, future)
            else:
                await peer.request_block(index, begin, BLOCK_LENGTH, future)
            futures.append(future)
            # print('requested from', begin)
        await self.check_ready()
        return self.reconstruct_piece(futures)
    
    async def reconstruct_piece(self, future_blocks):
        asd = future_blocks
        i = 0
        while asd:
            d, asd = await asyncio.wait(asd, return_when=asyncio.FIRST_COMPLETED)
            i += len(d)
            print(f'\033[92mgot {i} part out of {len(future_blocks)}' + '\033[0m')
        blocks = await asyncio.gather(*future_blocks)
        piece = b''
        for block in blocks:
            piece += block
        await self.check_ready()
        return piece