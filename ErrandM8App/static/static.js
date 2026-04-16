/**
 * location.js  —  paste this into your base template or load it as a static file.
 *
 * 1. On runner dashboard: updates the runner's location in the DB silently.
 * 2. On post_task form: fills hidden lat/lng inputs so the task gets coordinates.
 */

// ── Runner dashboard: send location to /update_location/ ──────────────────
function updateRunnerLocation() {
  if (!navigator.geolocation) return;

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      fetch('/update_location/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
        }),
      }).then(r => r.json()).then(data => {
        if (data.status === 'ok') {
          const el = document.getElementById('location-status');
          if (el) el.textContent = '📍 Location active';
        }
      });
    },
    (err) => {
      const el = document.getElementById('location-status');
      if (el) el.textContent = '⚠ Location unavailable — showing all errands';
      console.warn('Geolocation error:', err.message);
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
}

// ── Post-task form: fill hidden lat/lng fields ─────────────────────────────
function capturePickupLocation() {
  if (!navigator.geolocation) return;

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const latField = document.getElementById('pickup_latitude');
      const lngField = document.getElementById('pickup_longitude');
      if (latField) latField.value = pos.coords.latitude;
      if (lngField) lngField.value = pos.coords.longitude;
      const hint = document.getElementById('location-hint');
      if (hint) hint.textContent = '✓ Location captured';
    },
    (err) => {
      const hint = document.getElementById('location-hint');
      if (hint) hint.textContent = 'Could not get location — runners may not see this errand nearby.';
    }
  );
}

// ── CSRF helper ────────────────────────────────────────────────────────────
function getCookie(name) {
  let v = null;
  document.cookie.split(';').forEach(c => {
    const [k, val] = c.trim().split('=');
    if (k === name) v = decodeURIComponent(val);
  });
  return v;
}

// ── Auto-run based on page ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('runner-dashboard')) updateRunnerLocation();
  if (document.getElementById('post-task-form'))   capturePickupLocation();
});