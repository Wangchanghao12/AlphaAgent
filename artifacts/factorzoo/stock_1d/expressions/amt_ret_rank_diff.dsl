amt_rank = RANK(LOG($amount))
ret_rank = RANK($adj_close)
SUBTRACT(amt_rank, ret_rank)
