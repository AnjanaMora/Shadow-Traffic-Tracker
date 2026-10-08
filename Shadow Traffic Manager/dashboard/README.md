# 📊 Dashboard Module (`dashboard/`)

> High-performance real-time operations console built in React, Vite, and Tailwind CSS with Recharts time-series baselining and WebSocket streaming.

---

## 1. Overview & Key Capabilities

The Shadow Traffic Dashboard provides operations and SRE teams with real-time visibility into traffic dynamics and predictive risk:

1. **Fleet Overview Card Grid**:
   - Color-coded risk score gauge (`Normal`, `Watch`, `Warning`, `Critical`).
   - Estimated time-to-congestion badge (`~18 min until congestion`).
   - 30-minute sparkline trends for Active Users, Request Rate, Response Time, and Error Rate.
   - Primary risk driver callout.
2. **Interactive Site Detail Modal (Recharts)**:
   - Full-size time-series charts for all 4 core metrics.
   - **Seasonal Baseline Shaded Band**: Overlays historical $[\mu - 1.5\sigma, \mu + 1.5\sigma]$ normal range so operators visually see departures from expected diurnal patterns.
   - **SHAP-Style Attribution Bar**: Visual breakdown showing percentage contribution (e.g. Response Time: 45%, Request Rate: 30%, Error Rate: 25%).
3. **Live Streaming & Resilience**:
   - Real-time updates pushed over WebSocket (`/ws/traffic`).
   - Seamless automatic reconnection with HTTP polling fallback if connection drops.
4. **Mini-SaaS Site Management**:
   - Multi-tenant site registration modal (`+ Add Website`).
   - Generates scoped API keys (`st_live_<hex>`) and displays copyable collector startup commands.
5. **Remediation & Incident History**:
   - Live banner showing mock cloud auto-remediation status (e.g., *Auto-remediation triggered: scaled from 2 to 4 instances*).
   - Incident timeline with automated deployment root-cause hypotheses.

---

## 2. Running in Isolation

### Prerequisites
- Node.js 18+ (tested with Node 20 / npm 10)

### Installation
From the `dashboard/` directory:
```bash
npm install
```

### Development Server
```bash
npm run dev
```
The Vite development server will start at:
👉 **[http://localhost:3000](http://localhost:3000)** (or [http://localhost:5173](http://localhost:5173))

### Configuration
By default, the Vite development server proxies requests to `http://localhost:8000` via `vite.config.js`. You can also configure environment variables in `.env`:
```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/traffic
```

---

## 3. Production Build & Verification

```bash
npm run build
```

This compiles optimized, minified static assets to `dist/` (gzip size $\approx 176\text{ kB}$), ready for serving via Nginx or CDN.

To test the production build locally:
```bash
npm run preview
```
