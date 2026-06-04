import Foundation

class HighCC {
    func performLogin(state: Int, retry: Bool) -> String {
        if state == 0 { return "init" }
        if state == 1 && retry { return "retrying" }
        if state == 2 {
            for i in 0..<10 {
                if i % 2 == 0 {
                    if i > 5 { return "even-large" }
                    else { return "even-small" }
                } else {
                    if i > 5 { return "odd-large" }
                }
            }
        }
        switch state {
        case 3: return "three"
        case 4: return "four"
        case 5: return "five"
        case 6: return retry ? "six-retry" : "six"
        default: return "default"
        }
    }
}
