async function req(path, opts) {
  const r = await fetch(`/api${path}`, opts)
  let data = null
  try {
    data = await r.json()
  } catch {
    /* sin cuerpo JSON */
  }
  if (!r.ok) {
    const d = data?.detail
    throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `Error ${r.status}`)
  }
  return data
}

const json = (body, method = 'POST') => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null)).toString()

export const api = {
  salud: () => req('/salud'),
  analizar: (formData) => req('/analizar-caso', { method: 'POST', body: formData }),
  casos: () => req('/casos'),
  caso: (id) => req(`/casos/${id}`),
  mensajes: (id) => req(`/casos/${id}/mensajes`),
  chat: (id, body) => req(`/casos/${id}/chat`, json(body)),
  servicios: () => req('/servicios'),
  buscar: (q, lat, lon) => req(`/geo/buscar?${qs({ q, lat, lon })}`),
  inversa: (lat, lon) => req(`/geo/inversa?${qs({ lat, lon })}`),
  ruta: (p) => req(`/geo/ruta?${qs(p)}`),
  geocercas: () => req('/geocercas'),
  crearGeocerca: (body) => req('/geocercas', json(body)),
  borrarGeocerca: (id) => req(`/geocercas/${id}`, { method: 'DELETE' }),
  eventoGeocerca: (id, body) => req(`/geocercas/${id}/eventos`, json(body)),
  eventos: () => req('/eventos-geocerca'),
}
