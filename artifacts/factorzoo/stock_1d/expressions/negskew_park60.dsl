skew_r = RANK(CS_WINSORIZE(TS_SKEW($ret, 20), 0.01, 0.99))
park = TS_STD(LOG(DIVIDE($high, $low)), 60)
park_r = RANK(park)
SUBTRACT(NEG(skew_r), park_r)
