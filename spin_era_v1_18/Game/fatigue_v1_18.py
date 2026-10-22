"""Fatigue reduces available physical execution, never learned skills or PA.

Deterministic game-design coefficients. At the legacy neutral fatigue25 the
physical adjustment is exactly identity; compatibility mode disables it fully.
"""
VERSION='V1.18-PHYSICAL-FATIGUE-1'
VULNERABILITY=dict(speed=1.0,burst=1.0,agility=.9,stamina=.8,strength=.45,flexibility=.35)

def apply(state,fatigue):
    load=max(0.,float(fatigue)-25)
    factors={k:max(.80,1-.0015*load*v) for k,v in VULNERABILITY.items()}
    before=dict(state['p_eff'])
    state['p_eff']={k:before[k]*factors[k] for k in before}
    state['physical_fatigue_audit']=dict(version=VERSION,fatigue=fatigue,neutral_threshold=25,
        body_before=before,body_after=dict(state['p_eff']),multipliers=factors,
        coefficient_status='GAME_DESIGN_NOT_MEDICALLY_CALIBRATED',permanent_attributes_changed=False)
    return state
