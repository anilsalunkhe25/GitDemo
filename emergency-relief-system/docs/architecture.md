# Architecture

Streamlit is the presentation layer and communicates with Flask over JSON HTTP. It stores only the JWT session token and never opens a database connection.

Flask blueprints expose authenticated REST endpoints. Services own workflow rules such as priority scoring, inventory transactions, allocation, delivery events, and forecasting. SQLAlchemy models map the relational domain to MySQL (or SQLite for local tests).

The ML layer loads synthetic historical consumption data, cleans and encodes features, compares Linear Regression, Random Forest, and Gradient Boosting, then persists the best estimator with Joblib. Forecast output is compared to current non-expired available stock to calculate shortage and a recommendation.

## Data flow

Emergency -> affected area -> relief request -> transparent priority -> forecast and stock check -> human-reviewed allocation -> delivery events -> dashboard analytics.

Authentication uses hashed passwords and JWT access tokens. Role checks are applied at route boundaries; administrators approve requests and review critical AI recommendations, operators manage assigned operational data, and logistics volunteers update assigned deliveries.
