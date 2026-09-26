"""Versioned evidence from the existing catalog; no second retrieval index."""
from planning.requirements_contract import digest
from planning.knowledge.facts import fact_manifest
from pathlib import Path


def snapshot_for(cards, root=None):
    catalog_hash = digest(cards)
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    sources = [{'id': c['id'], 'sources': c['sources']} for c in cards]
    source_manifest_hash = digest({'formula_sources': sources, 'facts_and_documents': fact_manifest(root)})
    return dict(snapshot_id='knowledge:' + digest({'catalog_hash': catalog_hash, 'source_manifest_hash': source_manifest_hash}), catalog_hash=catalog_hash,
                source_manifest_hash=source_manifest_hash,
                embedding_weights_hash=None, tokenizer_config_hash=None,
                encoder_rule_version='not-used', retrieval_rule_version='requirements-lexical-v1')


def evidence_for(cards, snapshot, ranks):
    refs = []
    for card in cards:
        for i, source in enumerate(card['sources']):
            if not source.get('title') or not (source.get('url') or source.get('path')):
                continue
            refs.append(dict(evidence_id=f"{snapshot['snapshot_id']}:{card['id']}:{i}", kind='formula_card',
                source_title=source['title'], source_url=source.get('url'), source_id=None if source.get('url') else source.get('path'),
                locator=source.get('locator') or 'formula card source metadata', excerpt=card['description'],
                content_hash=digest(card), catalog_id=card['id'], card_version=card['version'], status=card['status'],
                knowledge_snapshot_id=snapshot['snapshot_id'], parameter_names=list(card['parameters']),
                relevance_rank=ranks[card['id']]))
    return refs


def plan_for(request, card, parameters, evidence_ids):
    by_name = {p['canonical_name']: p for p in parameters}
    plan = dict(plan_id=request['request_id'] + ':plan', task_id=request['task_id'], revision=request['revision'],
                objective='自由空间单链路损耗基准', selected_model=[card['id']],
                required_parameters=list(card['parameters']), assumptions=list(card['applicability'].get('notes', [])),
                evidence_ids=evidence_ids, steps=[dict(step_id='fspl-step', tool_id=card['id'],
                    inputs={name: dict(kind='parameter', ref=by_name[name]['parameter_id'], unit=spec['unit'])
                            for name, spec in card['parameters'].items()}, expected_unit=card['output']['unit'],
                    dependencies=[], required_conditions=list(card['applicability']['requires']))])
    plan['plan_hash'] = digest(plan)
    return plan
