"""Stable identities and immutable dated snapshots; no on-demand rerolls."""
import copy
import hashlib
from datetime import date
from common import canonical_json

def snapshot_hash(card):return hashlib.sha256(canonical_json(card).encode()).hexdigest()

def register(registry,player_id,card=None,*,as_of=None,source_ref,classification='ASSESSMENT'):
    if not isinstance(player_id,str) or not player_id or not source_ref:raise ValueError('identity and source required')
    if card is not None:
        if card.get('player_id')!=player_id:raise ValueError('snapshot identity mismatch')
        as_of=as_of or card.get('snapshot_date')
    if as_of is None:raise ValueError('dated snapshots required')
    date.fromisoformat(as_of)
    row=registry.setdefault(player_id,dict(player_id=player_id,snapshots={}))
    digest=snapshot_hash(card) if card is not None else None
    value=dict(as_of=as_of,card=copy.deepcopy(card),sha256=digest,source_ref=source_ref,classification=classification)
    previous=row['snapshots'].get(as_of)
    if previous:
        if previous['sha256']!=digest:raise ValueError('LOCKED_PLAYER_SNAPSHOT_CONFLICT')
        return copy.deepcopy(previous)
    row['snapshots'][as_of]=value;return copy.deepcopy(value)

def select(registry,player_id,as_of):
    date.fromisoformat(as_of);rows=registry[player_id]['snapshots']
    keys=[k for k in rows if k<=as_of]
    if not keys:raise ValueError('NO_NONFUTURE_PLAYER_SNAPSHOT')
    return copy.deepcopy(rows[max(keys)])
