# SSE Log Streaming — Manual Verification Checklist

After deploying the secure-admin-auth change (Phase B Batch B-β), verify
these steps in a real browser session to confirm the SSE migration is
working correctly.

## 1. No token in EventSource URL

1. Open the admin panel and navigate to **Settings → System**.
2. Open DevTools → **Network** tab, filter by `logs`.
3. Click a service to start the log stream.
4. Confirm the EventSource request URL is **exactly**:

   ```
   /api/admin/system/<service>/logs?tail=100
   ```

   There must be **no** `?token=` or `&token=` parameter in the URL.

## 2. No JWT visible in Next.js access logs

1. Tail the Next.js process logs (or Docker logs for `msia-admin-panel`):

   ```bash
   docker-compose logs -f admin-panel
   ```

2. While the log stream is active, confirm that **no log line** contains
   `?token=` in the request path.

## 3. Logs stream successfully via cookie auth

1. With a valid logged-in session (admin_token cookie present), navigate to
   **Settings → System** and select any service.
2. Confirm that log lines appear in the UI within a few seconds.
3. Confirm the Network entry for the EventSource shows status **200** and
   `Content-Type: text/event-stream`.

## 4. Logout stops the stream with 401

1. While a log stream is active, open a second tab and perform **logout**
   (via the user menu → Cerrar sesión).
2. Return to the system page (or wait for the next reconnect attempt).
3. Confirm:
   - The EventSource reconnects and receives an error event (HTTP 401 from
     the Next.js proxy).
   - The stream stops updating.
   - The UI shows no new log lines.

## Notes

- The Next.js proxy route (`/api/admin/system/[service]/logs/route.ts`) reads
  the `admin_token` httpOnly cookie and forwards it as `Authorization: Bearer`
  to the backend. The browser never sends the token in the URL.
- The backend SSE endpoint (`api/routes/system.py`) uses the standard
  `Depends(get_current_user)` guard, same as all other protected endpoints.
- The `EventSource` API does not support custom headers, so the Next.js API
  route acts as the authenticated proxy between the browser and backend.
