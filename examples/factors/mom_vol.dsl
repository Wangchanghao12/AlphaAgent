mom = DELTA($adj_close, 5)
vol = TS_STD($adj_close, 20)
DIVIDE(mom, ADD(vol, 1e-8))
