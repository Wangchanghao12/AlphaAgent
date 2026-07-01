ret = $ret
idio_ret = CS_DEMEAN(ret)
ret_win = CS_WINSORIZE(idio_ret, 0.01, 0.99)
q90 = TS_QUANTILE(ret_win, 20, 0.9)
q10 = TS_QUANTILE(ret_win, 20, 0.1)
raw_spread = SUBTRACT(q90, q10)
CS_NEUTRALIZE(raw_spread, CS_BUCKET(LOG($float_cap), 3))
