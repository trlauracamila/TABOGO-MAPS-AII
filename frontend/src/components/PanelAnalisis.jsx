import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import CasoResultado from './CasoResultado'

export default function PanelAnalisis({ userPos, caso, onResultado }) {
  const [descripcion, setDescripcion] = useState('')
  const [archivo, setArchivo] = useState(null)
  const [preview, setPreview] = useState(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)
  const camaraRef = useRef(null)
  const galeriaRef = useRef(null)

  useEffect(() => {
    if (!archivo) return setPreview(null)
    const url = URL.createObjectURL(archivo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [archivo])

  const elegir = (e) => {
    const f = e.target.files?.[0]
    if (f) setArchivo(f)
    e.target.value = ''
  }

  const enviar = async (e) => {
    e.preventDefault()
    setError(null)
    if (!descripcion.trim() && !archivo) return setError('Escribe una descripción o adjunta una foto.')
    const fd = new FormData()
    fd.append('descripcion', descripcion)
    if (userPos) {
      fd.append('lat', userPos.lat)
      fd.append('lon', userPos.lon)
      if (userPos.precision != null) fd.append('precision', userPos.precision)
    }
    if (archivo) fd.append('imagen', archivo)
    setCargando(true)
    try {
      onResultado(await api.analizar(fd))
    } catch (err) {
      setError(err.message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div>
      <form onSubmit={enviar} className="tarjeta">
        <h3>Nuevo caso</h3>
        <label>¿Qué necesitas?</label>
        <textarea rows={3} value={descripcion} onChange={(e) => setDescripcion(e.target.value)}
          placeholder="Ej: ¿Qué lugar es este y cómo llego? · Necesito una estación de carga cerca · Cómo llego a la Plaza de Bolívar" />

        <label>Foto del lugar (opcional)</label>
        <div className="fila">
          <button type="button" className="btn" onClick={() => camaraRef.current.click()}>📷 Tomar foto</button>
          <button type="button" className="btn sec" onClick={() => galeriaRef.current.click()}>🖼 Elegir imagen</button>
          {archivo && <button type="button" className="btn sec" onClick={() => setArchivo(null)}>Quitar</button>}
        </div>
        <input ref={camaraRef} type="file" accept="image/*" capture="environment" hidden onChange={elegir} />
        <input ref={galeriaRef} type="file" accept="image/*" hidden onChange={elegir} />
        {preview && <img src={preview} alt="Vista previa" className="preview" />}

        <p className="muted">
          {userPos
            ? `📡 Se enviará tu posición (${userPos.fuente === 'simulada' ? 'simulada' : 'GPS'}): ${userPos.lat.toFixed(5)}, ${userPos.lon.toFixed(5)}`
            : '⚠️ Sin ubicación todavía: activa el GPS o usa el modo simulación (clic en el mapa).'}
        </p>
        <button className="btn primario" disabled={cargando}>
          {cargando ? 'Los agentes están trabajando…' : 'Analizar con IA'}
        </button>
        {error && <p className="error-msg">{error}</p>}
      </form>
      {caso && <CasoResultado caso={caso} />}
    </div>
  )
}
