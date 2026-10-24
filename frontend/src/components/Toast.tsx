import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { Check, CircleAlert, Info, X } from 'lucide-react'

type Tone = 'success' | 'error' | 'info'
interface ToastItem { id: number; tone: Tone; message: string }
interface ToastApi { push: (tone: Tone, message: string) => void }
const Ctx = createContext<ToastApi | null>(null)

/** Lightweight toast region (polite live region). Errors stay until dismissed; others auto-close. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)
  const dismiss = useCallback((id: number) => setItems(list => list.filter(t => t.id !== id)), [])
  const push = useCallback((tone: Tone, message: string) => {
    const id = nextId.current++
    setItems(list => [...list.slice(-3), { id, tone, message }])
    if (tone !== 'error') setTimeout(() => dismiss(id), 5000)
  }, [dismiss])
  const api = useMemo(() => ({ push }), [push])
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toast-region" role="region" aria-label="Notifications" aria-live="polite">
        {items.map(t => <ToastView key={t.id} item={t} onClose={() => dismiss(t.id)} />)}
      </div>
    </Ctx.Provider>
  )
}

function ToastView({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const Icon = item.tone === 'success' ? Check : item.tone === 'error' ? CircleAlert : Info
  return (
    <div className={`toast toast-${item.tone}`} role={item.tone === 'error' ? 'alert' : 'status'}>
      <Icon size={16} /><span>{item.message}</span>
      <button className="icon-button" onClick={onClose} aria-label="Dismiss notification"><X size={15} /></button>
    </div>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
