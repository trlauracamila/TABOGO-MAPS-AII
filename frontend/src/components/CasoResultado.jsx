import { fmtDist, fmtDur } from '../geo'

const ESTADOS = {
  completado: ['ok', 'Completado'],
  requiere_informacion: ['aviso', 'Requiere más información'],
  sin_resultados: ['aviso', 'Sin resultados en el mapa'],
}
const VERIF = {
  confirmado_por_mapa: ['ok', 'Confirmado por el servicio de mapas'],
  parcial: ['aviso', 'Verificación parcial: confirma en sitio'],
  datos_consultados: ['ok', 'Resultados reales consultados'],
  sin_resultados: ['error', 'Sin resultados'],
}

export default function CasoResultado({ caso }) {
  const [clase, etiqueta] = ESTADOS[caso.estado] || ['aviso', caso.estado]
  const a = caso.analisis
  const geo = caso.geo
  const rec = caso.recomendacion
  const destino = geo?.destino
  const verif = geo ? VERIF[geo.verificacion] : null

  return (
    <div className="resultado">
      <div className="fila-titulo">
        <h3>{caso.id}</h3>
        <span className={`badge ${clase}`}>{etiqueta}</span>
      </div>

      {rec && (
        <div className="tarjeta">
          <h4>{rec.titulo}</h4>
          <p>{rec.resumen}</p>
          {rec.pasos_sugeridos?.length > 0 && (
            <ol>{rec.pasos_sugeridos.map((p, i) => <li key={i}>{p}</li>)}</ol>
          )}
          {rec.advertencias?.map((w, i) => <p key={i} className="advertencia">⚠️ {w}</p>)}
        </div>
      )}

      {destino && (
        <div className="tarjeta destacada">
          <h4>📍 {destino.nombre}</h4>
          <p><strong>Dirección (servicio de mapas):</strong> {destino.direccion || 'sin dirección registrada'}</p>
          <p className="muted">Fuente: {destino.fuente} · {destino.lat.toFixed(5)}, {destino.lon.toFixed(5)}</p>
          {verif && <span className={`badge ${verif[0]}`}>{verif[1]}</span>}
          {geo.ruta && (
            <p className="ruta-resumen">🧭 {fmtDist(geo.ruta.distancia_m)} · {fmtDur(geo.ruta.duracion_s)} ({geo.ruta.modo})</p>
          )}
          {geo.notas?.map((n, i) => <p key={i} className="muted">• {n}</p>)}
        </div>
      )}

      {a && (
        <div className="tarjeta">
          <h4>Análisis estructurado de la IA</h4>
          <table className="tabla">
            <tbody>
              <tr><td>Tipo de solicitud</td><td>{a.tipo_solicitud}</td></tr>
              <tr><td>Necesidad</td><td>{a.resumen_necesidad}</td></tr>
              <tr><td>Información</td><td>{a.estado_informacion} — {a.motivo_estado}</td></tr>
              <tr><td>Lugar visto por la IA</td><td>{a.lugar.nombre || '— (no identificado)'}</td></tr>
              <tr><td>Confianza</td><td>{a.confianza_identificacion}</td></tr>
              {a.lugar.direccion_estimada && (
                <tr><td>Dirección en la imagen</td><td>{a.lugar.direccion_estimada} <em>(sin verificar)</em></td></tr>
              )}
              {a.lugar.texto_visible?.length > 0 && <tr><td>Texto visible</td><td>{a.lugar.texto_visible.join(' · ')}</td></tr>}
              {a.lugar.pistas_visuales?.length > 0 && <tr><td>Pistas visuales</td><td>{a.lugar.pistas_visuales.join(' · ')}</td></tr>}
              {a.hechos_observados?.length > 0 && <tr><td>Hechos observados</td><td>{a.hechos_observados.join(' · ')}</td></tr>}
              {a.hipotesis?.length > 0 && <tr><td>Hipótesis (no confirmadas)</td><td>{a.hipotesis.join(' · ')}</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {caso.acciones?.length > 0 && (
        <div className="tarjeta">
          <h4>Acciones del sistema</h4>
          <ul className="lista">
            {caso.acciones.map((x, i) => (
              <li key={i}>
                <span className={`badge ${x.estado === 'ejecutada' ? 'ok' : x.estado === 'fallida' ? 'error' : 'aviso'}`}>{x.estado}</span>{' '}
                <strong>{x.tipo}</strong> — {x.detalle}{x.id != null ? ` (id: ${x.id})` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {geo?.ruta?.pasos?.length > 0 && (
        <details className="tarjeta">
          <summary>Indicaciones de la ruta ({geo.ruta.pasos.length} pasos)</summary>
          <ol>{geo.ruta.pasos.map((p, i) => <li key={i}>{p}</li>)}</ol>
        </details>
      )}

      {caso.traza?.length > 0 && (
        <details className="tarjeta" open>
          <summary>Trazabilidad: agentes y herramientas</summary>
          {caso.traza.map((t, i) => (
            <div key={i} className="traza-item">
              <strong>{i + 1}. {t.agente}</strong> {t.usa_ia && <span className="badge info">IA</span>}
              <span className="muted"> · {t.ms} ms</span>
              <div className="muted">{t.responsabilidad}</div>
              <div>→ {t.salida}</div>
              {t.herramientas?.map((h, j) => (
                <div key={j} className="herr">🛠 {h.nombre} {h.ok ? '✓' : '✗'} <span className="muted">{h.resumen}</span></div>
              ))}
            </div>
          ))}
        </details>
      )}
    </div>
  )
}
