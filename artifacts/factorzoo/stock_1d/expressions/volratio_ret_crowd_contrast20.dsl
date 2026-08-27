cc = CROWD_CONTRAST($ret, $volume_ratio, 20, 0.5)
CS_NEUTRALIZE(RANK(FILLNA(cc, 0.0)), CS_BUCKET(LOG($float_cap), 10))
