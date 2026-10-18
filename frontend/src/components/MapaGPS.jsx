import { useEffect, useRef } from 'react'
import L from 'leaflet'

const COLORES = {
  turismo: '#f59e0b', educacion: '#8b5cf6', transporte_publico: '#0ea5e9', combustible: '#ef4444',
  carga_electrica: '#22c55e', parqueadero: '#64748b', salud: '#ec4899', seguridad: '#14b8a6',
}

function contenidoPopup({ nombre, direccion, extra, lat, lon }, cb) {
  const div = document.createElement('div')
  const t = document.createElement('strong')
  t.textContent = nombre
  div.appendChild(t)
  for (const texto of [direccion, extra]) {
    if (!texto) continue
    const p = document.createElement('div')
    p.textContent = texto
    div.appendChild(p)
  }
  const b = document.createElement('button')
  b.className = 'popup-btn'
  b.textContent = '🧭 Ruta hasta aquí'
  b.onclick = () => cb.current.onIrA?.(lat, lon, nombre, direccion)
  div.appendChild(b)
  return div
}

const iconoUsuario = L.divIcon({ className: 'user-dot', html: '<span></span>', iconSize: [20, 20] })
const iconoDestino = L.divIcon({ className: 'dest-pin', html: '📍', iconSize: [30, 30], iconAnchor: [15, 28] })

export default function MapaGPS({
  userPos, seguir, geocercas, dentro, previewGeocerca, destino, ruta, propios, mostrarPropios,
  candidatos, modoMapa, onClickMapa, onIrA,
}) {
  const divRef = useRef(null)
  const mapRef = useRef(null)
  const capas = useRef({})
  const primeraVez = useRef(false)
  const cb = useRef({})
  cb.current = { onClickMapa, onIrA }

  // ---- inicializar mapa (OpenStreetMap)
  useEffect(() => {
    const map = L.map(divRef.current).setView([4.6097, -74.0817], 13)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map)
    map.on('click', (e) => cb.current.onClickMapa?.(e.latlng.lat, e.latlng.lng))
    mapRef.current = map
    capas.current = {}
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(divRef.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
      capas.current = {}
      primeraVez.current = false
    }
  }, [])

  useEffect(() => {
    divRef.current?.classList.toggle('mapa-crosshair', !!modoMapa)
  }, [modoMapa])

  // ---- posición del usuario (GPS real o simulado)
  useEffect(() => {
    const map = mapRef.current
    const c = capas.current
    if (!map) return
    if (!userPos) {
      c.user?.remove(); c.prec?.remove(); c.user = c.prec = null
      return
    }
    const ll = [userPos.lat, userPos.lon]
    if (!c.user) {
      c.prec = L.circle(ll, { radius: 0, color: '#38bdf8', weight: 1, fillOpacity: 0.12 }).addTo(map)
      c.user = L.marker(ll, { icon: iconoUsuario, zIndexOffset: 1000 }).addTo(map).bindTooltip('Tu posición')
    } else {
      c.user.setLatLng(ll)
      c.prec.setLatLng(ll)
    }
    c.prec.setRadius(Math.min(userPos.precision || 0, 500))
    if (seguir) {
      if (!primeraVez.current) {
        map.setView(ll, 16)
        primeraVez.current = true
      } else {
        map.panTo(ll)
      }
    }
  }, [userPos, seguir])

  // ---- geocercas
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    capas.current.geo?.remove()
    const lg = L.layerGroup().addTo(map)
    capas.current.geo = lg
    geocercas.forEach((g) => {
      const dentroG = !!dentro[g.id]
      L.circle([g.lat, g.lon], {
        radius: g.radio_m, color: dentroG ? '#22c55e' : '#6366f1', weight: 2, fillOpacity: dentroG ? 0.25 : 0.12,
      }).bindTooltip(`${g.nombre} · ${Math.round(g.radio_m)} m${dentroG ? ' · DENTRO' : ''}`).addTo(lg)
    })
    if (previewGeocerca) {
      L.circle([previewGeocerca.lat, previewGeocerca.lon], {
        radius: previewGeocerca.radio_m, color: '#f59e0b', dashArray: '6 6', weight: 2, fillOpacity: 0.08,
      }).bindTooltip('Nueva geocerca (vista previa)').addTo(lg)
    }
  }, [geocercas, dentro, previewGeocerca])

  // ---- datos propios
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    capas.current.propios?.remove()
    if (!mostrarPropios) return
    const lg = L.layerGroup().addTo(map)
    capas.current.propios = lg
    propios.forEach((s) => {
      L.circleMarker([s.lat, s.lon], {
        radius: 7, color: '#0f172a', weight: 1, fillColor: COLORES[s.categoria] || '#94a3b8', fillOpacity: 0.95,
      }).bindPopup(() => contenidoPopup({ nombre: s.nombre, direccion: s.direccion,
        extra: `Categoría: ${s.categoria} (dato propio)`, lat: s.lat, lon: s.lon }, cb)).addTo(lg)
    })
  }, [propios, mostrarPropios])

  // ---- candidatos de una búsqueda
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    capas.current.cand?.remove()
    const lg = L.layerGroup().addTo(map)
    capas.current.cand = lg
    candidatos.forEach((s) => {
      L.circleMarker([s.lat, s.lon], { radius: 8, color: '#fff', weight: 2, fillColor: '#fb923c', fillOpacity: 1 })
        .bindPopup(() => contenidoPopup({ nombre: s.nombre, direccion: s.direccion,
          extra: `Fuente: ${s.fuente}${s.distancia_m != null ? ` · ${s.distancia_m} m` : ''}`, lat: s.lat, lon: s.lon }, cb))
        .addTo(lg)
    })
  }, [candidatos])

  // ---- destino
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    capas.current.destino?.remove()
    capas.current.destino = null
    if (!destino) return
    capas.current.destino = L.marker([destino.lat, destino.lon], { icon: iconoDestino, zIndexOffset: 900 })
      .addTo(map)
      .bindPopup(() => {
        const d = document.createElement('div')
        const t = document.createElement('strong')
        t.textContent = destino.nombre
        d.appendChild(t)
        if (destino.direccion) {
          const p = document.createElement('div')
          p.textContent = destino.direccion
          d.appendChild(p)
        }
        return d
      })
    map.setView([destino.lat, destino.lon], Math.max(map.getZoom(), 16))
  }, [destino])

  // ---- ruta
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    capas.current.ruta?.remove()
    capas.current.ruta = null
    if (!ruta?.geometria?.length) return
    const line = L.polyline(ruta.geometria, { color: '#38bdf8', weight: 6, opacity: 0.9 }).addTo(map)
    capas.current.ruta = line
    map.fitBounds(line.getBounds(), { padding: [50, 50] })
  }, [ruta])

  return <div ref={divRef} className="mapa" />
}
