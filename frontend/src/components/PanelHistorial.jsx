import { useEffect, useState } from 'react'
import { api } from '../api'

export default function PanelHistorial({ onAbrir, version }) {
  const [casos, setCasos] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    api.casos().then(setCasos).catch((e) => setError(e.message))
  }, [version])

  return (
    <div className="tarjeta">
      <h3>Historial y persistencia (SQLite)</h3>
      {error && <p className="error-msg">{error}</p>}
      {casos.length === 0 && <p className="muted">Todavía no hay casos guardados.</p>}
      {casos.map((c) => (
        <div key={c.id} className="item-caso" onClick={() => api.caso(c.id).then(onAbrir)}>
          <div><strong>{c.id}</strong> <span className={`badge ${c.estado === 'completado' ? 'ok' : 'aviso'}`}>{c.estado}</span></div>
          <div>{c.descripcion}</div>
          <div className="muted">
            {c.creado_en}{c.destino ? ` · destino: ${c.destino}` : ''}
          </div>
          <div className="muted">Agentes: {c.agentes.join(' → ')}</div>
          <div className="muted">Acciones: {c.acciones.join(', ') || 'ninguna'}</div>
        </div>
      ))}
    </div>
  )
}
