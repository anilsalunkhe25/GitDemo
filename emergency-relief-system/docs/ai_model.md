# AI model

The model predicts future resource requirement from synthetic demo history. It uses `population_affected`, `emergency_duration`, `emergency_severity`, `resource_type`, `daily_consumption`, `days_since_emergency`, `previous_demand`, and `current_inventory`.

`python -m backend.ml.generate_dataset` creates the dataset and `python -m backend.ml.train_model` cleans it, encodes categorical features, performs a reproducible 80/20 split, evaluates Linear Regression, Random Forest, and Gradient Boosting with MAE, RMSE, and R2, and saves the highest-R2 estimator plus metrics. The checked-in metrics file reports measurements on this synthetic dataset only.

At prediction time, the selected model estimates future demand. The service calculates `expected_shortage = max(predicted_quantity - current_available_stock, 0)` and recommends the shortage quantity when positive, otherwise it reports that stock is sufficient.

Forecasts are recommendations, not decisions. Historical data quality, synthetic data distribution, changing disaster conditions, and feature assumptions limit reliability. Critical resource decisions require human review, which is recorded through the forecast review endpoint and shown in the UI.
