import { useState } from 'react'
import { api } from '../api'
import { fmtDist, haversine } from '../geo'

export default function PanelGeocercas({
  geocercas, dentro, eventos, userPos, punto, setPunto, radio, setRadio, setModoMapa, modoMapa, onCambio,
}) {
  const [nombre, setNombre] = useState('')
  const [error, setError] = useState(null)

  const crear = async () => {
    setError(null)
    if (!punto) return setError('Elige un punto en el mapa o usa tu ubicación.')
    try {
      await api.crearGeocerca({ nombre: nombre.trim() || 'Mi geocerca', lat: punto.lat, lon: punto.lon, radio_m: radio })
      setNombre('')
      setPunto(null)
      onCambio()
    } catch (e) {
      setError(e.message)
    }
  }

  const borrar = async (id) => {
    await api.borrarGeocerca(id).catch(() => {})
    onCambio()
  }

  return (
    <div>
      <div className="tarjeta">
        <h3>Crear geocerca</h3>
        <label>Nombre</label>
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Ej: Entrada del trabajo" />
        <label>Radio: {radio} m</label>
        <input type="range" min="50" max="1000" step="10" value={radio} onChange={(e) => setRadio(Number(e.target.value))} />
        <div className="fila">
          <button className={`btn ${modoMapa === 'geocerca' ? 'primario' : 'sec'}`} onClick={() => setModoMapa(modoMapa === 'geocerca' ? null : 'geocerca')}>
            📌 {modoMapa === 'geocerca' ? 'Haz clic en el mapa…' : 'Elegir punto en el mapa'}
          </button>
          <button className="btn sec" disabled={!userPos} onClick={() => setPunto({ lat: userPos.lat, lon: userPos.lon })}>
            📡 Mi ubicación
          </button>
        </div>
        {punto && <p className="muted">Centro: {punto.lat.toFixed(5)}, {punto.lon.toFixed(5)} (círculo naranja en el mapa)</p>}
        <button className="btn primario" onClick={crear}>Guardar geocerca</button>
        {error && <p className="error-msg">{error}</p>}
      </div>

      <div className="tarjeta">
        <h3>Geocercas activas ({geocercas.length})</h3>
        {geocercas.length === 0 && <p className="muted">Aún no hay geocercas.</p>}
        {geocercas.map((g) => (
          <div key={g.id} className="item-geo">
            <div>
              <strong>{g.nombre}</strong> <span className={`badge ${dentro[g.id] ? 'ok' : 'info'}`}>{dentro[g.id] ? 'DENTRO' : 'fuera'}</span>
              <div className="muted">
                {Math.round(g.radio_m)} m · origen: {g.origen}
                {userPos && ` · a ${fmtDist(haversine(userPos.lat, userPos.lon, g.lat, g.lon))}`}
              </div>
            </div>
            <button className="btn sec" onClick={() => borrar(g.id)}>🗑</button>
          </div>
        ))}
      </div>

      <div className="tarjeta">
        <h3>Eventos detectados</h3>
        {eventos.length === 0 && <p className="muted">Se registran al entrar/salir de una geocerca con el GPS (o el modo simulación).</p>}
        {eventos.slice(0, 12).map((e) => (
          <div key={e.id} className="muted">{e.creado_en} — <strong>{e.tipo}</strong> en {e.geocerca}</div>
        ))}
      </div>
    </div>
  )
}
