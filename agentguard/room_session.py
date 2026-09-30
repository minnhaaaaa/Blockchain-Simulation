import time
import uuid

from agentguard.canonical import encode_signature, signing_bytes
from agentguard.identity import Signer, fingerprint, verify
from agentguard.canonical import decode_signature
from agentguard.schema_validation import SchemaValidator
from signalling.client import SignallingClient, SignallingClientError


class RoomSessionError(ValueError): pass


class RoomSessionCoordinator:
    def __init__(self,client:SignallingClient,schemas:SchemaValidator,signer:Signer,node_id:str,node_name:str,
                 advertised_host:str,advertised_port:int,clock_ms=None,on_verified_room=None):
        self.client=client; self.schemas=schemas; self.signer=signer; self.node_id=node_id; self.node_name=node_name
        self.advertised_host=advertised_host; self.advertised_port=advertised_port
        self.clock_ms=clock_ms or (lambda:int(time.time()*1000)); self._listeners=[on_verified_room] if on_verified_room else []
        self._active_room_id=None
        self.active_manifest=None

    def add_listener(self,listener): self._listeners.append(listener)

    def configure(self,request:dict):
        self.schemas.validate_named("room-session-request.schema.json",request)
        try:
            if request["operation"]=="create":
                now=self.clock_ms(); manifest={"schema_version":1,"room_id":request["room_id"],
                  "protocol_version":request["protocol_version"],"consensus":{"type":"pos","parameters":request["consensus_parameters"]},
                  "genesis":{"block_id":str(uuid.uuid4()),"created_at_ms":now,"allocations":request["genesis_allocations"]},
                  "creator_public_key":self.signer.public_key_pem,"created_at_ms":now}
                manifest["signature"]=encode_signature(self.signer.sign(signing_bytes("agentguard.room-manifest.v1",manifest,"signature")))
                manifest=self.client.create_room(manifest)
            else: manifest=self.client.get_room(request["room_id"])
        except SignallingClientError as exc: raise RoomSessionError(str(exc)) from exc
        self.schemas.validate_named("room-manifest.schema.json",manifest)
        try: signature=decode_signature(manifest["signature"])
        except Exception as exc: raise RoomSessionError("room manifest signature encoding is invalid") from exc
        if not verify(manifest["creator_public_key"],signature,signing_bytes("agentguard.room-manifest.v1",manifest,"signature")):
            raise RoomSessionError("room manifest signature is invalid")
        member={"schema_version":1,"node_id":self.node_id,"name":self.node_name,"advertised_host":self.advertised_host,
                "advertised_port":self.advertised_port,"public_key_fingerprint":fingerprint(self.signer.public_key_pem)}
        try: self.client.join(manifest["room_id"],member); members=self.client.members(manifest["room_id"])
        except SignallingClientError as exc: raise RoomSessionError(str(exc)) from exc
        old_room=self._active_room_id
        try:
            for listener in self._listeners: listener(manifest,members["items"])
        except Exception:
            if old_room != manifest["room_id"]:
                try: self.client.leave(manifest["room_id"],self.node_id)
                except SignallingClientError: pass
            raise
        self._active_room_id=manifest["room_id"]
        self.active_manifest=manifest
        if old_room and old_room != self._active_room_id:
            try: self.client.leave(old_room,self.node_id)
            except SignallingClientError: pass
        return manifest
