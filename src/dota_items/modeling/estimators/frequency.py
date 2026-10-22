"""Train-observed frequency; target eligibility is the trainer's responsibility."""


class FrequencyEstimator:
    def fit_parameters(self, x, y, *, c, solver):
        return {"frequency": float(y.mean())}
