"""Read-only coverage audit: resolve task placeholders before checking pairs/conditions."""
from collections import defaultdict, Counter
import json
from lab_isolated_data import load_candidate


def audit():
    data = load_candidate()
    lookup = defaultdict(list)
    for row in data['reaction_payload']() + data['MEDIUM_REACTIONS']:
        lookup[frozenset((row['a'], row['b']))].append(row)
    counts, gaps = Counter(), []
    for task in data['TASK6_BANK']:
        def resolve(value):
            return task['answer_x'] if value == '$X' else task['answer_y'] if value == '$Y' else value
        for experiment in task.get('experiments', []):
            pair = [resolve(value) for value in experiment['pair']]
            rows = lookup[frozenset(pair)]
            excess = resolve(experiment.get('excess', ''))
            status = 'covered'
            if not rows:
                status = 'missing_pair'
            elif excess and not any(row.get('excess') == excess for row in rows):
                status = 'missing_excess_variant'
            elif all(row.get('heat') for row in rows) and not experiment.get('heat'):
                status = 'requires_heat_not_in_task'
            elif all(row.get('t') == 'z' for row in rows):
                status = 'explicit_no_reaction'
            counts[status] += 1
            if status not in ('covered', 'explicit_no_reaction'):
                gaps.append({'task_id': task['id'], 'pair': pair, 'status': status})
    return {'scope': 'repository TASK6_BANK, not the full 235-task workbook',
            'tasks': len(data['TASK6_BANK']), 'experiments': sum(counts.values()),
            'counts': dict(counts), 'gaps': gaps,
            'limits': 'Pair/heat/excess availability check; not a chemical correctness proof or a full workbook audit.'}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
