// Validator-claim fixture template (Kotlin) — input pra subprocess do sandbox.
// Auditor preenche shape que DEVERIA fazer o validator falhar.
//
// fixture_id:        {{fixture_id}}
// target_validator:  {{validator_path}}
// language:          kotlin
//
// claim.what_validator_says: {{claim}}
// claim.what_we_test:        {{counter_example}}
// claim.expected_exit_code:  1  // validator deveria sinalizar falha

object FixtureInput {
    // Payload sintético — auditor substitui pelo contra-exemplo concreto.
    val payload: Map<String, Any?> = emptyMap() // {{payload}}
}
