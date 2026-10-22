"""Built-in, auditable patch inventory. No arbitrary uploaded code execution."""
import copy
from world_extensions_v1_18 import digest
PATCHES=(
 dict(id='P001_SHARED_CLOCK',version=1,required=True,description='Calendar activity and synchronized active roster'),
 dict(id='P002_IDEMPOTENT_SETTLEMENT',version=1,required=True,description='Atomic match, H2H, rating, health and XP transaction'),
 dict(id='P003_FORMAL_XP_RECONCILIATION',version=1,required=True,description='Permanent 43-path XP with finite development rewards'),
 dict(id='P004_FORMATS',version=1,required=True,description='BO3/5/7 and declared multiway group rules'),
 dict(id='P005_OPT_IN_ANTI_SHUTOUT',version=2,required=False,default_enabled=False,description='Bounded score-context experiment'),
 dict(id='P006_PHYSICAL_FATIGUE',version=1,required=False,default_enabled=True,description='Fatigue-to-effective-body execution repair'))

def apply(world,patch_id,*,enabled=None,event_id=None):
    found=next((p for p in PATCHES if p['id']==patch_id),None)
    if found is None:raise ValueError('UNKNOWN_BUILT_IN_PATCH')
    if found['required']:
        if enabled is False:raise ValueError('STRUCTURAL_PATCH_CANNOT_BE_DISABLED_IN_THIS_FORMAT')
        world.consistency_check(deep=True)
        return dict(status='already_applied',patch=copy.deepcopy(found),no_state_change=True)
    if type(enabled)is not bool:raise ValueError('explicit optional-patch boolean required')
    key='anti_shutout' if patch_id=='P005_OPT_IN_ANTI_SHUTOUT' else 'physical_fatigue'
    if world.data['v1_18']['patches'].get(key,True)==enabled:
        return dict(status='already_applied',patch=copy.deepcopy(found),no_state_change=True)
    eid=event_id or 'config-patch:'+patch_id+':'+world.data['audit_head'][:16]
    result=world.set_experiment(enabled,eid) if key=='anti_shutout' else world.set_physical_fatigue(enabled,eid)
    return dict(status='applied',patch=copy.deepcopy(found),receipt=result)
