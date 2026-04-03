# GSPS Mobile (Flutter)

Flutter app for:
- Login (JWT, same as web)
- Profile
- Clock in/out (GPS + camera + geofence check against Sites)
- Apply leave
- View schedule

## Run
1. Install Flutter SDK
2. From this folder:

```bash
flutter pub get
flutter run
```

## Backend requirements
The web backend must expose `/api/v1` endpoints for:
- Auth token: `POST /api/v1/auth/token`
- Profile: `GET /api/v1/me`
- Sites: `GET /api/v1/sites?company_id=...`
- Schedule: `GET /api/v1/schedule?company_id=...`
- Leave types + apply: `GET /api/v1/leave/types?company_id=...`, `POST /api/v1/leave/requests?company_id=...`
- Clock events: `POST /api/v1/clock/events?company_id=...`

