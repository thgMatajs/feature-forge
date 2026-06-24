// fixture pra demonstrar SECRETS-OVERRIDE no commit body.
// O integration test gera commit body contendo:
//   SECRETS-OVERRIDE: tests/fixtures/secrets/file_with_test_fixture.kt:5 kind=aws-access-key — test fixture
object FakeAws {
    const val KEY = "AKIA00000000FAKE0001"
}
