import { useCallback, useEffect, useRef, useState } from 'react'
import { api, formatUpdateBadge } from '../lib/helpers'

export function useUpdateCheck() {
  const [status, setStatus] = useState(null)
  const [checking, setChecking] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [footerMessage, setFooterMessage] = useState('')
  const retried = useRef(false)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/update/status')
      setStatus(data)
      return data
    } catch {
      return null
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!status || status.latest_version || status.error || retried.current) return undefined
    retried.current = true
    const timer = window.setTimeout(() => { load() }, 2000)
    return () => window.clearTimeout(timer)
  }, [status, load])

  const checkNow = async () => {
    setChecking(true)
    setFooterMessage('')
    try {
      const { data } = await api.post('/update/check')
      setStatus(data)
      if (data?.update_available) setModalOpen(true)
      else if (data?.current_version) setFooterMessage(`Up to date · v${data.current_version}`)
    } catch {
      setFooterMessage('')
    } finally {
      setChecking(false)
    }
  }

  return { status, checking, modalOpen, setModalOpen, footerMessage, checkNow }
}

export function UpdateBadge({ status, onOpen }) {
  if (!status?.update_available) return null
  const label = formatUpdateBadge(status.latest_version)
  if (status.release_url) {
    return <a className="update-badge" href={status.release_url} target="_blank" rel="noopener noreferrer" onClick={onOpen}>{label}</a>
  }
  return <button type="button" className="update-badge" onClick={onOpen}>{label}</button>
}

export function UpdateModal({ status, open, onClose }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open || !status?.update_available) return null
  return <div className="update-modal-backdrop" onClick={onClose}>
    <div className="update-modal" role="dialog" aria-modal="true" aria-labelledby="update-heading" onClick={(event) => event.stopPropagation()}>
      <div className="eyebrow">RELEASE</div>
      <h2 id="update-heading">Update available</h2>
      <p className="muted">This install is v{status.current_version}. GitHub latest stable is v{status.latest_version}.</p>
      <div className="form-actions">
        <button type="button" className="text-button" onClick={onClose}>CLOSE</button>
        {status.release_url
          ? <a className="btn-primary" href={status.release_url} target="_blank" rel="noopener noreferrer">OPEN RELEASE</a>
          : <button type="button" className="btn-primary" disabled>OPEN RELEASE</button>}
      </div>
    </div>
  </div>
}

export function AppFooter({ status, checking, message, onCheck }) {
  const version = status?.current_version
  return <footer className="footer">
    <span className="footer-copy">{version ? `DeusCFO v${version}` : 'DeusCFO'}</span>
    <span aria-hidden="true">·</span>
    <button type="button" className="text-button" disabled={checking} onClick={onCheck}>{checking ? 'CHECKING…' : 'CHECK FOR UPDATES'}</button>
    {message && <span className="footer-copy" role="status">{message}</span>}
  </footer>
}
