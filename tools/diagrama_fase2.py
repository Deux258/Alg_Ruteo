"""DOT del esquema real exportado; renderizar con Graphviz dentro de Docker."""
import argparse
import json
from pathlib import Path
from collections import defaultdict


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('diagnostic',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    report=json.loads(args.diagnostic.read_text(encoding='utf-8'));tables=defaultdict(list)
    for row in report['schema']:tables[row['table_name']].append(row)
    lines=['digraph BD {','graph [rankdir=LR,bgcolor="white",pad=0.3,nodesep=0.35,ranksep=0.9,fontname="DejaVu Sans",fontsize=24,labelloc=t,label="Fase 2 · 29 tablas · esquema y FK inspeccionados en PostgreSQL"];','node [shape=record,fontname="DejaVu Sans",fontsize=12,style=filled,fillcolor="#EDF5F7",color="#3e8d64"];','edge [fontname="DejaVu Sans",fontsize=9,color="#81959c"];']
    primary={r['source']:r['definition'] for r in report['constraints'] if r['kind']=='p'}
    for name,fields in sorted(tables.items()):
        label=name+'|'+''.join(row['column_name']+' : '+row['udt_name']+'\\l' for row in fields)
        if name in primary:label+='|'+primary[name].replace('PRIMARY KEY','PK')+'\\l'
        color='#E0EFE3' if name in ['run_areas','base_catalogue','mission_evaluations'] else '#EDF5F7'
        lines.append(f'{name} [label="{{{label}}}",fillcolor="{color}"];')
    seen=set()
    for constraint in report['constraints']:
        if constraint['kind']=='f':
            key=(constraint['source'],constraint['target'])
            if key not in seen:lines.append(f'{key[0]} -> {key[1]} [label="FK"];');seen.add(key)
    lines.append('}');args.output.write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
