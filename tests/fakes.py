import uuid

from agentguard.node_service import Submission


class MemoryNodeService:
    def __init__(self,ledger_state="included"):
        self.ledger_state=ledger_state; self.events={}; self.callbacks=[]
    def submit_event(self,event):
        existing=self.events.get(event["event_id"])
        if existing and existing!=event: raise ValueError("ID_REUSE")
        self.events[event["event_id"]]=event
        submission=Submission(str(uuid.uuid4()),event["event_id"],self.ledger_state,event["event_hash"])
        for callback in self.callbacks: callback({"event_id":event["event_id"],"ledger_state":self.ledger_state})
        return submission
    def get_event(self,event_id): return self.events.get(event_id)
    def list_job_events(self,job_id): return sorted((e for e in self.events.values() if e["job_id"]==job_id),key=lambda e:e["sequence"])
    def get_chain_summary(self,limit): return {"height":1,"finalized_height":0,"head_hash":"0"*64,"blocks":[]}
    def get_block(self,block_id): return None
    def get_peer_summaries(self): return []
    def get_stake_snapshot(self): return {"epoch_seed":"0"*64,"total_stake":1,"latest_proposer_fingerprint":None,"items":[]}
    def subscribe_state_changes(self,callback):
        self.callbacks.append(callback)
        return lambda:self.callbacks.remove(callback)


class RegistryClient:
    def __init__(self,registry): self.registry=registry
    def create_room(self,manifest): return self.registry.create_room(manifest)
    def get_room(self,room_id): return self.registry.get_room(room_id)
    def join(self,room_id,member): return self.registry.join(room_id,member)
    def members(self,room_id): return self.registry.list_members(room_id)
    def heartbeat(self,room_id,node_id): return self.registry.heartbeat(room_id,node_id)
    def leave(self,room_id,node_id): return self.registry.leave(room_id,node_id)

