# Validator-claim fixture template (Python) — input pra subprocess do sandbox.
# Auditor preenche shape que DEVERIA fazer o validator falhar.
#
# fixture_id:        {{fixture_id}}
# target_validator:  {{validator_path}}
# language:          python
#
# claim.what_validator_says: {{claim}}
# claim.what_we_test:        {{counter_example}}
# claim.expected_exit_code:  1   # validator deveria sinalizar falha


def fixture_input():
    """Payload sintético — auditor substitui pelo contra-exemplo concreto."""
    return {}  # {{payload}}
