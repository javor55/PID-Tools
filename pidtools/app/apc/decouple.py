"""APC – rozvazbení 2×2: převody decouplerů do jednotek PCS 7."""


def gain_eng(d, src, dst):
    """Zesílení decoupleru v inženýrských jednotkách: ΔMV_dst [j.] / ΔMV_src [j.]."""
    return d["gain"] * (dst["mv_rng"][1] - dst["mv_rng"][0]) / (src["mv_rng"][1] - src["mv_rng"][0])
