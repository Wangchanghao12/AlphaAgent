w = 18
price = $vwap * $adjfactor
ret = $ret
eff = TS_EFFICIENCY_RATIO(price, w)
crowd = CROWD_CONTRAST(eff, ret, w)
vol_w = TS_MEAN(ADD($amount/$float_cap, 1), w)
MULTIPLY(crowd, vol_w)
