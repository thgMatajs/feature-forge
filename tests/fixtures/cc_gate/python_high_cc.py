def tokenize(state: int, retry: bool) -> str:
    if state == 0:
        return "init"
    if state == 1 and retry:
        return "retrying"
    if state == 2:
        for i in range(10):
            if i % 2 == 0:
                if i > 5:
                    return "even-large"
                else:
                    return "even-small"
            else:
                if i > 5:
                    return "odd-large"
    if state == 3:
        return "three"
    elif state == 4:
        return "four"
    elif state == 5:
        return "five"
    elif state == 6:
        return "six-retry" if retry else "six"
    return "default"
