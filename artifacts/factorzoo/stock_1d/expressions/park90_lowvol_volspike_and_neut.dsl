# park90 交集版：低波 且 波动未激增 -> 高值
park = TS_STD(LOG(DIVIDE($high, $low)), 90)
rv10 = TS_STD($ret, 10)
vol_z = TS_ZSCORE(rv10, 250)
leg1 = NEG(RANK(park))
leg2 = NEG(RANK(TS_RANK(vol_z, 250)))
f = MIN(leg1, leg2)
CS_NEUTRALIZE(f, CS_BUCKET(LOG($float_cap), 10))
