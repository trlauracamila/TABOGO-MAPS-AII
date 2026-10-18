import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api'

export default function PanelChat({ caso, userPos, onGeocercaCreada }) {
  const [mensajes, setMensajes] = useState([])
  const [texto, setTexto] = useState('')
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)
  const finRef = useRef(null)
  const casoId = caso?.id

  useEffect(() => {
    setMensajes([])
    setError(null)
    if (!casoId) return
    api.mensajes(casoId).then(setMensajes).catch(() => {})
  }, [casoId])

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [mensajes, cargando])

  if (!caso) {
    return <div className="tarjeta"><h3>Chat contextual</h3><p>Primero analiza un caso en la pestaña “Analizar”; el chat responde sobre ese caso.</p></div>
  }

  const enviar = async () => {
    const m = texto.trim()
    if (!m || cargando) return
    setTexto('')
    setError(null)
    setMensajes((x) => [...x, { rol: 'user', contenido: m }])
    setCargando(true)
    try {
      const r = await api.chat(caso.id, { mensaje: m, lat: userPos?.lat, lon: userPos?.lon })
      setMensajes((x) => [...x, { rol: 'assistant', contenido: r.respuesta, herramientas: r.herramientas }])
      if (r.geocerca_creada) onGeocercaCreada()
    } catch (e) {
      setError(e.message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="chat">
      <h3>Chat del caso {caso.id}</h3>
      <div className="chat-mensajes">
        {mensajes.length === 0 && (
          <p className="muted">Prueba: “¿Qué farmacias hay cerca?”, “¿Cuánto tardo caminando?”, “Crea una geocerca de 200 m en el destino”, “¿Qué servicios propios hay cerca?”</p>
        )}
        {mensajes.map((m, i) => (
          <div key={i} className={`burbuja ${m.rol}`}>
            {m.rol === 'assistant' ? <ReactMarkdown>{m.contenido}</ReactMarkdown> : m.contenido}
            {m.herramientas?.length > 0 && (
              <div className="herr-chat">
                {m.herramientas.map((h, j) => <span key={j} className={`badge ${h.ok ? 'info' : 'error'}`}>🛠 {h.nombre}</span>)}
              </div>
            )}
          </div>
        ))}
        {cargando && <div className="burbuja assistant muted">Consultando herramientas…</div>}
        <div ref={finRef} />
      </div>
      {error && <p className="error-msg">{error}</p>}
      <div className="fila">
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Pregunta sobre este caso…"
          onKeyDown={(e) => e.key === 'Enter' && enviar()} />
        <button className="btn primario" onClick={enviar} disabled={cargando}>Enviar</button>
      </div>
    </div>
  )
}
