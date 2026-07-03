bps_lev = MULTIPLY($funda_bps, $funda_debt_to_assets)
bps_lev_ratio = DIVIDE(bps_lev, $adj_close)
bps_lev_w = CS_WINSORIZE(bps_lev_ratio, 0.02, 0.98)
CS_NEUTRALIZE(CS_ZSCORE(bps_lev_w), $industry_sw_l1)
