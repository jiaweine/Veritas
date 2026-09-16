# Veritas Mobile

The mobile client is an Expo SDK 57 / React Native 0.86 application over the same `/api/v1` contract as the web workbench. It supports the audit cockpit, paper list, findings, PDF upload, audit detail, and deterministic harness commands.

## Run

```bash
cd mobile
npm install
EXPO_PUBLIC_VERITAS_API_URL=http://192.168.1.20:8765 npm start
```

For a physical device, use a LAN/HTTPS address reachable from the phone. The FastAPI service only needs CORS when a browser-origin client is cross-origin; native iOS/Android fetches are not browser CORS requests. For Expo web or other browser clients, configure for example:

```bash
VERITAS_CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081 veritas-harness
```

The app targets Expo SDK 57 because the June 2026 release moves to React Native 0.86, and Expo recommends SDK 57 over 56 after the Hermes regression fixes shipped in 57.0.x.
