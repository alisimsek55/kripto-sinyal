import json

from e2_independent import ROOT, State, baseline, load, simulate


CLAIMS = {"DOGE": 0.967721, "BTC": 0.976432}


if __name__ == "__main__":
    saved = json.loads((ROOT / "sonuc/parametreler.json").read_text(encoding="utf-8"))
    all_ok = True
    for coin in ("DOGE", "BTC"):
        df = load(coin)
        selections = saved["coinler"][coin]["kurallar"]["alim"]["kat_secimleri"]
        first_year = selections[0]["yil"]
        first = int(df.index[df["tarih"].str[:4].astype(int) == first_year][0])
        initial_coin, _ = baseline(df, 0, first - 1)
        months_before = int(df.loc[:first - 1, "monthly"].sum())
        s = State(coin=initial_coin, invested=months_before * 100.0,
                  contributions=months_before * 100.0)
        _, full_base = baseline(df)
        previous_ratio = 1.0
        year_rows = []
        for item in selections:
            year, p = item["yil"], item["alim"]
            indices = df.index[df["tarih"].str[:4].astype(int) == year]
            start, end = int(indices[0]), int(indices[-1])
            if p is None and s.reserve > 1e-9 and s.parts == 0:
                s.parts = 3
            s, values = simulate(df, p, start, end, s)
            cumulative = values[-1] / full_base[end]
            year_ratio = cumulative / previous_ratio
            year_rows.append((year, year_ratio, cumulative))
            previous_ratio = cumulative
        ratio = previous_ratio
        rel = abs(ratio - CLAIMS[coin]) / CLAIMS[coin]
        ok = rel <= 1e-6
        all_ok &= ok
        expected_years = saved["coinler"][coin]["kurallar"]["alim"]["ileri_yuruyus"]["yillar"]
        first_diff = None
        for own, expected in zip(year_rows, expected_years):
            if abs(own[1] - expected["oran"]) > 1e-12:
                first_diff = (own[0], own[1], expected["oran"], own[1] - expected["oran"])
                break
        print(f"{coin} independent_chain={ratio:.12f} claim={CLAIMS[coin]:.12f} "
              f"rel_error={rel:.3e} first_year_diff={first_diff}")
    print(f"E6 {'PASS' if all_ok else 'FAIL'}")
