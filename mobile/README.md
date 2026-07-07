# Vels Online — Mobile

React Native (Expo) staff app for the day-to-day SOC workflow on iOS and
Android phones: Incidents, Alert Inbox, Scheduled Search Rules, Threat
Hunting, and the Contacts/Assets directory, with full notification support
(in-app notification center + native push).

## Stack

- **Expo SDK 57** / React Native 0.86, TypeScript, `expo-router` file-based navigation
- **lucide-react-native** — same icon set as the web frontend
- Dark theme mirroring `frontend/src/globals.css` tokens (`src/lib/theme.ts`)
- **axios** against the existing backend REST API (session auth + CSRF echo header)
- **expo-notifications** for native push, delivered by the backend through the
  Expo push service (`notifications.ExpoPushToken`)

## Development

```bash
npm install
npm start          # Expo dev server; press i / a for simulator, or scan with Expo Go
npm test           # jest-expo + @testing-library/react-native
npx tsc --noEmit   # type check
```

Point the login screen's **Server** field at your backend. For local dev use
the Docker Compose stack (`http://localhost:8000`) — with `DEV_AUTO_LOGIN`
enabled the app signs straight in without the SSO round-trip.

### Sign-in flow

The backend authenticates with allauth (OIDC SSO) over Django session cookies.
The app opens `{server}/auth/login/` in a WebView that shares its cookie store
with the app's networking layer (`sharedCookiesEnabled`); once the session
lands on `/login-redirect/`, the app re-checks `/api/me/`, captures the CSRF
token from the echoed `X-CSRFToken` response header, and registers the
device's Expo push token.

## Structure

```
src/
  app/           expo-router routes (tabs: incidents, alerts, rules, hunts, directory)
  components/    shared UI (Badge, Card, SearchBar, FilterChips, …)
  context/       AuthContext, OrgContext (mirrors the web app's contexts)
  hooks/         usePagedList — pagination over the backend's envelope
  lib/           api client, theme, labels, format, transitions
  notifications/ push registration
  screens/       tests for router screens (kept out of app/ so Metro doesn't route them)
```

## Container

`Dockerfile` exports the Expo **update bundle** (Hermes bytecode for iOS +
Android plus `metadata.json`) and serves it with nginx — the self-hosted OTA
update artifact installed apps pull. Built and pushed as
`registry.vels.online/vels/mobile` by `.github/workflows/build-containers.yaml`
on version tags, alongside the backend and frontend images.

Store binaries (IPA/APK) are built with EAS or `npx expo run:{ios,android}`
from this directory when a new native shell is needed; JS-only changes ship
through the update bundle.
