export function computeTotal(state: number, retry: boolean): string {
    if (state === 0) return "init";
    if (state === 1 && retry) return "retrying";
    if (state === 2) {
        for (let i = 0; i < 10; i++) {
            if (i % 2 === 0) {
                if (i > 5) return "even-large";
                else return "even-small";
            } else {
                if (i > 5) return "odd-large";
            }
        }
    }
    switch (state) {
        case 3: return "three";
        case 4: return "four";
        case 5: return "five";
        case 6: return retry ? "six-retry" : "six";
        default: return "default";
    }
}
