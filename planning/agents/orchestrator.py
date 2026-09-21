"""Auditable bounded scheduling policy. Model suggestions have no goto authority."""
from planning.requirements_contract import require

MAX_CALCULATIONS = 2


def decide(state):
    attempts = state.get('calculation_attempts', 0)
    require(type(attempts) is int and 0 <= attempts <= MAX_CALCULATIONS, 'INVALID_EXECUTION_BUDGET')
    status = state['status']
    if status == 'VALIDATING_RESULT':
        require(state.get('result') is not None, 'RESULT_REQUIRED')
        action, reason = 'validate_result', 'tool_result_available'
    elif status == 'VALIDATING_REPORT':
        require(state.get('review_assessment', {}).get('role', {}).get('proposal', {}).get('decision') == 'pass', 'REVIEW_REQUIRED')
        action, reason = 'publish', 'review_passed'
    elif status in {'RETRYABLE_CALCULATION_FAILURE', 'RECALCULATION_REQUESTED'}:
        require(state.get('confirmed_snapshot') is not None, 'CONFIRMATION_REQUIRED')
        if attempts < MAX_CALCULATIONS:
            action = 'calculation'
            reason = 'transient_tool_retry' if status == 'RETRYABLE_CALCULATION_FAILURE' else 'review_requested_recalculation'
        else:
            action, reason = 'stop', 'calculation_budget_exhausted'
    elif status in {'AWAITING_INPUT', 'NEEDS_MODEL', 'FAILED'}:
        action, reason = 'stop', {'AWAITING_INPUT':'user_input_required', 'NEEDS_MODEL':'model_scope_review', 'FAILED':'hard_failure'}[status]
    else:
        raise ValueError('UNROUTABLE_STATE')
    return dict(action=action, reason_code=reason, input_status=status,
                calculation_attempts=attempts, max_calculations=MAX_CALCULATIONS, mode='bounded_policy')
