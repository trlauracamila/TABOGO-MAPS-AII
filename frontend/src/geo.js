export function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371000
  const rad = (d) => (d * Math.PI) / 180
  const dp = rad(lat2 - lat1)
  const dl = rad(lon2 - lon1)
  const a = Math.sin(dp / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

export function fmtDist(m) {
  if (m == null) return '—'
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

export function fmtDur(s) {
  if (s == null) return '—'
  const min = Math.round(s / 60)
  if (min < 60) return `${Math.max(min, 1)} min`
  return `${Math.floor(min / 60)} h ${min % 60} min`
}
