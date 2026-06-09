// Validator-claim fixture template (Swift) — input pra subprocess do sandbox.
// Auditor preenche shape que DEVERIA fazer o validator falhar.
//
// fixture_id:        {{fixture_id}}
// target_validator:  {{validator_path}}
// language:          swift
//
// claim.what_validator_says: {{claim}}
// claim.what_we_test:        {{counter_example}}
// claim.expected_exit_code:  1  // validator deveria sinalizar falha

enum FixtureInput {
    // Payload sintético — auditor substitui pelo contra-exemplo concreto.
    static let payload: [String: Any] = [:] // {{payload}}
}
