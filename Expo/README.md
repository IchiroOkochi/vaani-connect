# Expo Frontend Setup (Beginner Friendly)

This is the mobile/web app for Vaani Connect.

It connects to the Python backend (recommended to run on port `8000`).

---

## 1) Install prerequisites

- Node.js LTS: <https://nodejs.org/>
- npm (included with Node.js)

Check versions:

```bash
node -v
npm -v
```

---

## 2) Install and start frontend

```bash
cd /workspace/vaani-connect/Expo
npm install
npm run start
```

In Expo terminal output, choose one:

- Android emulator/device
- iOS simulator/device
- Web browser

---

## 3) Make sure backend is running

In a separate terminal, run backend from `bakcend/`:

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

If backend is not running, frontend features that call translation/speech APIs will fail.

---

## 4) Reset project (optional)

```bash
npm run reset-project
```

This moves starter code to `app-example/` and creates a clean `app/` folder.

---

## Useful links

- Expo docs: <https://docs.expo.dev>
- Expo Router docs: <https://docs.expo.dev/router/introduction>
