d52 = RANK(DIVIDE($adj_close, TS_MAX($adj_close, 250)))
ma120 = TS_MEAN($adj_close, 120)
mdev = NEG(RANK(DIVIDE(SUBTRACT($adj_close, ma120), ma120)))
ADD(d52, mdev)
