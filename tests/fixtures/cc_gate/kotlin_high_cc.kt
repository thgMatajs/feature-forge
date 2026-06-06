package app.fixtures

class HighCC {
    fun handleLogin(state: Int, retry: Boolean): String {
        if (state == 0) return "init"
        if (state == 1 && retry) return "retrying"
        if (state == 2) {
            for (i in 0..10) {
                if (i % 2 == 0) {
                    if (i > 5) return "even-large"
                    else return "even-small"
                } else {
                    if (i > 5) return "odd-large"
                }
            }
        }
        return when (state) {
            3 -> "three"
            4 -> "four"
            5 -> "five"
            6 -> if (retry) "six-retry" else "six"
            else -> "default"
        }
    }
}
