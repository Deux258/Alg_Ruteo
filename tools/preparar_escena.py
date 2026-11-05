"""Preprocess the geographic scene once, outside interactive HTTP requests."""
import argparse
import json
from core.patrol import snapshot_context,terrain
from core.geographic_scene import prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',required=True,help='Existing context.json belonging to this repository')
    args=parser.parse_args()
    print(json.dumps(prepare(snapshot_context(args.context),terrain())))
