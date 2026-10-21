"""Internal process worker; requests and results are standard JSON."""
import json
import sys
from common import RUNTIME
import tactical_match_v116 as tactical


def main():
    request = json.load(sys.stdin)
    if request.get('ruleset') == 'V1.1.6-HGR-CANDIDATE-1':
        from Game import specialist_engine as tactical_engine
    else:
        tactical_engine = tactical
    result = tactical_engine.play_match(request['cards'], request['seed'], keep_points=True,
                                 fatigue=tuple(request['fatigue']), max_games=request['max_games'])
    json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)


if __name__ == '__main__':
    main()
