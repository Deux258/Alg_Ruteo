"""Autómata de secuencias prohibidas para ejecutar Dijkstra con giros reales."""
from collections import defaultdict


def state_graph(edges, forbidden):
    from core.contracts import stable_id
    by_id = {e['id']: e for e in edges}
    outgoing = defaultdict(list)
    for e in edges:
        outgoing[e['source']].append(e['id'])
    forbidden = {tuple(p) for p in forbidden}
    prefixes = {p[:i] for p in forbidden for i in range(1, len(p))}
    states = {e: {'id': e, 'edge_id': e, 'context': [e] if (e,) in prefixes else []} for e in by_id}
    special = {}
    for prefix in sorted(prefixes):
        if len(prefix) < 2:
            continue
        ident = stable_id('turn-state:' + ','.join(map(str, prefix)))
        if ident in states:
            raise ValueError('Colisión de ID de estado de giro')
        special[prefix] = ident
        states[ident] = dict(id=ident, edge_id=prefix[-1], context=list(prefix))
    transitions = []
    seen = set()
    for state in sorted(states.values(), key=lambda s: s['id']):
        for following in sorted(outgoing[by_id[state['edge_id']]['target']]):
            history = tuple(state['context']) + (following,)
            if any(len(p) <= len(history) and history[-len(p):] == p for p in forbidden):
                continue
            suffix = max((p for p in prefixes if len(p) <= len(history) and history[-len(p):] == p), key=len, default=())
            target = special[suffix] if len(suffix) > 1 else following
            ident = stable_id(f'transition:{state["id"]}:{target}')
            if ident in seen:
                raise ValueError('Transición duplicada o colisión')
            seen.add(ident)
            transitions.append(dict(id=ident, source=state['id'], target=target, edge_id=following))
    return sorted(states.values(), key=lambda s: s['id']), transitions
