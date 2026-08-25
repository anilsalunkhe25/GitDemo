# API

All protected endpoints require `Authorization: Bearer <access-token>`. Responses use `{success, message, data}`; validation errors use HTTP 422.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` |
| Users | `GET/POST /api/users`, `PUT /api/users/<id>` |
| Emergencies | `GET/POST /api/emergencies`, `GET/PUT/DELETE /api/emergencies/<id>` |
| Areas | `GET/POST /api/areas`, `PUT/DELETE /api/areas/<id>` |
| Requests | `GET/POST /api/requests`, `GET/PUT/DELETE /api/requests/<id>`, `PUT /approve`, `PUT /reject`, `GET /priority-explanation` |
| Resources | `GET/POST /api/resources`, `PUT /api/resources/<id>` |
| Inventory | `GET /api/inventory`, stock add/remove/transfer, reserve/release, transactions, low-stock and expiring alerts |
| Centers | `GET/POST /api/centers`, `PUT /api/centers/<id>`, `GET /api/centers/<id>/inventory` |
| Allocation | `POST/GET /api/allocation`, `GET /api/allocation/<id>`, `PUT /cancel` |
| Delivery | `GET/POST /api/deliveries`, `GET /<id>`, `PUT /<id>/status`, assign, timeline |
| Forecast | `POST /api/forecast/predict`, `GET /history`, `GET /metrics`, `PUT /<id>/review` |
| Dashboard | `GET /api/dashboard/summary`, `/notifications`, `/analytics` |

Use JSON request bodies. Quantity values must be positive integers; dates use ISO `YYYY-MM-DD` format. Role permissions are enforced by the API and must not be trusted from the client.
