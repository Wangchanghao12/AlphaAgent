sh = CROWD_SHARE($turnover_rate, $volume, 30, 'high', 0.7)
CS_NEUTRALIZE(RANK(FILLNA(sh, 0.5)), CS_BUCKET(LOG($float_cap), 10))
