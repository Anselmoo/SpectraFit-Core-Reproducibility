import numpy as np
from spectrafit_core import MeasurementData, compose, fit, gaussian

# Synthetic "measured" data: a Gaussian peak plus a little noise.
x = np.linspace(-5, 5, 200)
y = 3.0 * np.exp(-0.5 * ((x - 0.5) / 1.2) ** 2) + np.random.default_rng(0).normal(
    0, 0.05, x.size
)

# Build the model graph: one Gaussian node with initial guesses.
graph = compose([gaussian("peak1", amplitude=1.0, center=0.0, sigma=1.0)]).build()

# Run the fit.
result = fit(graph, MeasurementData(x=x.tolist(), y=y.tolist()))

print(result.parameters)  # fitted amplitude/center/sigma, keyed "peak1.<param>"
print(result.r_squared)  # goodness of fit
