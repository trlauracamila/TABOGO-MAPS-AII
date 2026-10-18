import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { fmtDist, fmtDur, haversine } from './geo'
import MapaGPS from './components/MapaGPS'
import PanelAnalisis from './components/PanelAnalisis'
import PanelChat from './components/PanelChat'
import PanelGeocercas from './components/PanelGeocercas'
import PanelHistorial from './components/PanelHistorial'

const TABS = [
  ['analizar', '🔎 Analizar'],
  ['chat', '💬 Chat'],
  ['geocercas', '⭕ Geocercas'],
  ['historial', '🗂 Historial'],
]

export default function App() {
  const [tab, setTab] = useState('analizar')
  const [salud, setSalud] = useState(null)

  // ---- GPS
  const [userPos, setUserPos] = useState(null)
  const [simulacion, setSimulacion] = useState(false)
  const [gpsError, setGpsError] = useState(null)
  const [seguir, setSeguir] = useState(true)
  const [direccionActual, setDireccionActual] = useState(null)

  // ---- caso / destino / ruta
  const [caso, setCaso] = useState(null)
  const [destino, setDestino] = useState(null)
  const [ruta, setRuta] = useState(null)
  const [candidatos, setCandidatos] = useState([])
  const [versionHistorial, setVersionHistorial] = useState(0)

  // ---- datos propios, geocercas y alertas
  const [propios, setPropios] = useState([])
  const [mostrarPropios, setMostrarPropios] = useState(true)
  const [geocercas, setGeocercas] = useState([])
  const [dentro, setDentro] = useState({})
  const [eventos, setEventos] = useState([])
  const [alertas, setAlertas] = useState([])
  const [modoMapa, setModoMapa] = useState(null)
  const [puntoGeocerca, setPuntoGeocerca] = useState(null)
  const [radioGeocerca, setRadioGeocerca] = useState(150)

  // ---- búsqueda de direcciones
  const [consulta, setConsulta] = useState('')
  const [resultadosBusqueda, setResultadosBusqueda] = useState([])

  const estadoGeo = useRef({})
  const ultimaInversa = useRef(null)
  const llegada = useRef(null)

  const pushAlerta = useCallback((texto, tipo = 'info') => {
    const id = Date.now() + Math.random()
    setAlertas((a) => [...a, { id, texto, tipo }])
    setTimeout(() => setAlertas((a) => a.filter((x) => x.id !== id)), 9000)
  }, [])

  const cargarGeocercas = useCallback(() => {
    api.geocercas().then(setGeocercas).catch(() => {})
    api.eventos().then(setEventos).catch(() => {})
  }, [])

  // ---- carga inicial
  useEffect(() => {
    api.salud().then(setSalud).catch(() => setSalud({ ok: false }))
    api.servicios().then(setPropios).catch(() => {})
    cargarGeocercas()
  }, [cargarGeocercas])

  // ---- GPS real (se desactiva en modo simulación)
  useEffect(() => {
    if (simulacion) return
    if (!('geolocation' in navigator)) {
      setGpsError('Tu navegador no soporta geolocalización. Usa el modo simulación.')
      return
    }
    setGpsError(null)
    const id = navigator.geolocation.watchPosition(
      (p) => {
        setGpsError(null)
        setUserPos({ lat: p.coords.latitude, lon: p.coords.longitude, precision: p.coords.accuracy, fuente: 'gps' })
      },
      (e) => setGpsError(
        e.code === 1 ? 'Permiso de ubicación denegado. Actívalo en el navegador o usa el modo simulación.'
          : e.code === 3 ? 'Se agotó el tiempo esperando el GPS. Reintenta o usa el modo simulación.'
            : 'No se pudo obtener tu ubicación. Usa el modo simulación.'),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [simulacion])

  // ---- dirección actual (geocodificación inversa, solo si te moviste > 60 m)
  useEffect(() => {
    if (!userPos) return
    const u = ultimaInversa.current
    if (u && haversine(u.lat, u.lon, userPos.lat, userPos.lon) < 60) return
    ultimaInversa.current = { lat: userPos.lat, lon: userPos.lon }
    api.inversa(userPos.lat, userPos.lon).then((r) => setDireccionActual(r.direccion)).catch(() => {})
  }, [userPos])

  // ---- motor de geocercas: detecta entradas y salidas
  useEffect(() => {
    if (!userPos) return
    const nuevos = {}
    geocercas.forEach((g) => {
      const d = haversine(userPos.lat, userPos.lon, g.lat, g.lon)
      const antes = !!estadoGeo.current[g.id]
      const ahora = antes ? d <= g.radio_m * 1.1 : d <= g.radio_m // histéresis del 10 % contra el "rebote" del GPS
      nuevos[g.id] = ahora
      if (ahora !== antes) {
        const tipo = ahora ? 'entrada' : 'salida'
        pushAlerta(ahora ? `📍 Entraste a la geocerca “${g.nombre}”` : `🚪 Saliste de la geocerca “${g.nombre}”`, ahora ? 'ok' : 'aviso')
        api.eventoGeocerca(g.id, { tipo, lat: userPos.lat, lon: userPos.lon })
          .then(() => api.eventos().then(setEventos))
          .catch(() => {})
      }
    })
    estadoGeo.current = nuevos
    setDentro(nuevos)
  }, [userPos, geocercas, pushAlerta])

  // ---- aviso de llegada al destino
  useEffect(() => {
    if (!destino || !userPos) return
    const d = haversine(userPos.lat, userPos.lon, destino.lat, destino.lon)
    const clave = `${destino.lat},${destino.lon}`
    if (d <= 30 && llegada.current !== clave) {
      llegada.current = clave
      pushAlerta(`🏁 Llegaste a ${destino.nombre}`, 'ok')
    } else if (d > 60 && llegada.current === clave) {
      llegada.current = null
    }
  }, [userPos, destino, pushAlerta])

  // ---- acciones
  const aplicarCaso = useCallback((c) => {
    setCaso(c)
    setDestino(c.geo?.destino || null)
    setRuta(c.geo?.ruta || null)
    setCandidatos(c.geo?.candidatos || [])
    setSeguir(false)
    setVersionHistorial((v) => v + 1)
    cargarGeocercas()
    setTab('analizar')
  }, [cargarGeocercas])

  const irA = useCallback(async (lat, lon, nombre, direccion) => {
    setDestino({ nombre, direccion, lat, lon })
    setSeguir(false)
    if (!userPos) {
      setRuta(null)
      pushAlerta('Activa el GPS o marca tu posición (modo simulación) para calcular la ruta.', 'aviso')
      return
    }
    try {
      setRuta(await api.ruta({ origen_lat: userPos.lat, origen_lon: userPos.lon, destino_lat: lat, destino_lon: lon, modo: 'drive' }))
    } catch (e) {
      setRuta(null)
      pushAlerta(e.message, 'error')
    }
  }, [userPos, pushAlerta])

  const onClickMapa = (lat, lon) => {
    if (modoMapa === 'geocerca') {
      setPuntoGeocerca({ lat, lon })
      setModoMapa(null)
    } else if (simulacion) {
      setUserPos({ lat, lon, precision: 5, fuente: 'simulada' })
    }
  }

  const buscarDireccion = async (e) => {
    e.preventDefault()
    if (!consulta.trim()) return
    try {
      setResultadosBusqueda(await api.buscar(consulta, userPos?.lat, userPos?.lon))
    } catch (err) {
      pushAlerta(err.message, 'error')
    }
  }

  const distRestante = destino && userPos ? haversine(userPos.lat, userPos.lon, destino.lat, destino.lon) : null

  return (
    <div className="app">
      <header className="cabecera">
        <h1>TABOGO MAPS IA</h1>
        <span className="muted">
          {salud
            ? salud.ok
              ? `IA: ${salud.modelo_ia}${salud.gemini_configurado ? '' : ' (⚠ falta GEMINI_API_KEY)'} · Mapas: ${salud.proveedor_mapas}`
              : '⚠ Backend no disponible (¿está corriendo uvicorn en el puerto 8000?)'
            : 'Conectando…'}
        </span>
      </header>

      <div className="layout">
        <aside className="panel">
          <nav className="tabs">
            {TABS.map(([id, nombre]) => (
              <button key={id} className={tab === id ? 'activa' : ''} onClick={() => setTab(id)}>{nombre}</button>
            ))}
          </nav>
          <div className="panel-contenido">
            {tab === 'analizar' && <PanelAnalisis userPos={userPos} caso={caso} onResultado={aplicarCaso} />}
            {tab === 'chat' && <PanelChat caso={caso} userPos={userPos} onGeocercaCreada={cargarGeocercas} />}
            {tab === 'geocercas' && (
              <PanelGeocercas geocercas={geocercas} dentro={dentro} eventos={eventos} userPos={userPos}
                punto={puntoGeocerca} setPunto={setPuntoGeocerca} radio={radioGeocerca} setRadio={setRadioGeocerca}
                modoMapa={modoMapa} setModoMapa={setModoMapa} onCambio={cargarGeocercas} />
            )}
            {tab === 'historial' && <PanelHistorial onAbrir={aplicarCaso} version={versionHistorial} />}
          </div>
        </aside>

        <section className="zona-mapa">
          <div className="barra-mapa">
            <label className="chk">
              <input type="checkbox" checked={simulacion} onChange={(e) => setSimulacion(e.target.checked)} />
              Modo simulación (clic en el mapa mueve tu posición)
            </label>
            <label className="chk">
              <input type="checkbox" checked={seguir} onChange={(e) => setSeguir(e.target.checked)} /> Seguirme
            </label>
            <label className="chk">
              <input type="checkbox" checked={mostrarPropios} onChange={(e) => setMostrarPropios(e.target.checked)} /> Datos propios
            </label>
            <form className="busqueda" onSubmit={buscarDireccion}>
              <input value={consulta} onChange={(e) => setConsulta(e.target.value)} placeholder="Buscar dirección o lugar…" />
              <button className="btn">Buscar</button>
            </form>
          </div>

          {resultadosBusqueda.length > 0 && (
            <div className="resultados-busqueda">
              {resultadosBusqueda.map((r, i) => (
                <div key={i} className="item-busqueda" onClick={() => { irA(r.lat, r.lon, r.nombre, r.direccion); setResultadosBusqueda([]) }}>
                  <strong>{r.nombre}</strong><div className="muted">{r.direccion}</div>
                </div>
              ))}
              <button className="btn sec" onClick={() => setResultadosBusqueda([])}>Cerrar</button>
            </div>
          )}

          <div className="mapa-wrap">
            <MapaGPS userPos={userPos} seguir={seguir} geocercas={geocercas} dentro={dentro}
              previewGeocerca={puntoGeocerca ? { ...puntoGeocerca, radio_m: radioGeocerca } : null}
              destino={destino} ruta={ruta} propios={propios} mostrarPropios={mostrarPropios}
              candidatos={candidatos} modoMapa={modoMapa} onClickMapa={onClickMapa} onIrA={irA} />
            <div className="alertas">
              {alertas.map((a) => <div key={a.id} className={`alerta ${a.tipo}`}>{a.texto}</div>)}
            </div>
          </div>

          <div className="estado-gps">
            {gpsError && <div className="error-msg">{gpsError}</div>}
            <div>
              📡 {userPos
                ? `${userPos.fuente === 'simulada' ? 'Posición simulada' : 'GPS'}: ${userPos.lat.toFixed(5)}, ${userPos.lon.toFixed(5)}${userPos.precision != null && userPos.fuente !== 'simulada' ? ` (±${Math.round(userPos.precision)} m)` : ''}`
                : 'Esperando ubicación…'}
              {direccionActual && <span className="muted"> · {direccionActual}</span>}
            </div>
            {destino && (
              <div>
                🧭 Destino: <strong>{destino.nombre}</strong>
                {distRestante != null && ` · a ${fmtDist(distRestante)} en línea recta`}
                {ruta && ` · ruta: ${fmtDist(ruta.distancia_m)}, ${fmtDur(ruta.duracion_s)}`}
                <button className="btn sec mini" onClick={() => { setDestino(null); setRuta(null) }}>Quitar</button>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
