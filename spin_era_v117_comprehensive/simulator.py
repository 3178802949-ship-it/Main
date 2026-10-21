"""Public API for the V1.1.7 comprehensive baseline.

The internal ``v118`` filenames identify the additive development layer, not a
public 1.1.8 release. Legacy modules and checkpoints remain separate.
"""
from world_v118 import WorldSession, RULESET, VERSION, ruleset_fingerprint
from Card import v118 as Card
from Game import v118 as Game
from Training import v118 as Training
from Area import v118 as Area
import narrative_v118 as Narrative

__all__ = ['WorldSession', 'RULESET', 'VERSION', 'ruleset_fingerprint',
           'Card', 'Game', 'Training', 'Area', 'Narrative']
