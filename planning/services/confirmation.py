"""Freeze server-produced review content. Hashes identify content, not authority."""
import copy
from planning.requirements_contract import digest, require, obj
from planning.services.requirement_validation import check_report
from planning.workflow.requirements_graph import stamp


def review_for(request, report, cards):
    review = dict(schema_version='1.0.0', profile='confirmed-fspl-loop-v1',
                  request=copy.deepcopy(request), report=copy.deepcopy(report),
                  model=copy.deepcopy(next((c for c in cards if c['id']=='fspl_ghz'),None)))
    review['review_hash'] = digest(review)
    return review


def confirm_review(review, cards):
    request, report = review['request'], review['report']
    require(review == review_for(request, report, cards), 'REVIEW_CONTENT_MISMATCH')
    checked = check_report(report, request, cards)
    require(checked['execution_status'] == 'AWAITING_CONFIRMATION', 'NOT_CONFIRMABLE')
    snapshot = dict(schema_version='1.0.0', profile='confirmed-fspl-loop-v1',
                    snapshot_id=request['request_id'] + ':confirmed', task_id=request['task_id'],
                    revision=request['revision'], review=copy.deepcopy(review),
                    confirmed_by='local_user', confirmed_at=stamp())
    snapshot['content_hash'] = digest(snapshot)
    return snapshot


def validate_snapshot(snapshot, review, cards):
    obj(snapshot, 'schema_version profile snapshot_id task_id revision review confirmed_by confirmed_at content_hash')
    require(snapshot['content_hash'] == digest({k:v for k,v in snapshot.items() if k != 'content_hash'}), 'SNAPSHOT_HASH_MISMATCH')
    require(snapshot['schema_version']=='1.0.0' and snapshot['profile']=='confirmed-fspl-loop-v1', 'SNAPSHOT_PROFILE')
    require(snapshot['review'] == review and review == review_for(review['request'], review['report'], cards), 'SNAPSHOT_INPUT_MISMATCH')
    request = review['request']
    require(snapshot['task_id']==request['task_id'] and snapshot['revision']==request['revision'] and
            snapshot['snapshot_id']==request['request_id']+':confirmed', 'SNAPSHOT_IDENTITY_MISMATCH')
    require(snapshot['confirmed_by']=='local_user' and bool(snapshot['confirmed_at']), 'CONFIRMATION_REQUIRED')
    check_report(review['report'], request, cards)
    require(review['report']['execution_status']=='AWAITING_CONFIRMATION', 'NOT_CONFIRMABLE')
    return copy.deepcopy(snapshot)
