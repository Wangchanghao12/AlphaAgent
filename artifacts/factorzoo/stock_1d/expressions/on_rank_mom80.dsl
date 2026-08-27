on = DIVIDE($open, DELAY($close, 1))
TS_MEAN(RANK(SUBTRACT(on, 1)), 80)
