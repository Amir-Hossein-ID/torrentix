import asyncio
import random

class PeerManager:
    def __init__(self, trackers, torrent, max_conn=10):
        self.trackers = trackers
        self.torrent = torrent
        self.max_peers = max_conn
        self.tracker_semaphore = asyncio.Semaphore(max_conn)
        self.peers = asyncio.Queue()
        self.active_peers = []
        self.peers_semaphore = asyncio.Semaphore(max_conn)
    
    async def capture_peers(self):
        for tracker in self.trackers:
            asyncio.create_task(self.add_peers(tracker))
    
    async def add_peers(self, tracker):
        async with self.tracker_semaphore:
            try:
                peers = await tracker.get_peer_list()
                for peer in peers:
                    self.peers.put(peer)
            except:
                print('error capturing from tracker')
    
    async def ensure_peers(self):
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
                await asyncio.wait_for(event.wait(), timeout=10)
                self.active_peers.append(peer)
        except:
            print('error handshaking with peer')
            await peer.drop()
            await self.peers_semaphore.release()
    
    async def remove_peer(self, peer):
        self.active_peers.remove(peer)
        await self.peers_semaphore.release()
        



    