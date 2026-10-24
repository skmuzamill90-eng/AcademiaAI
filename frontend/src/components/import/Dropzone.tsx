import { useRef, useState, type DragEvent } from 'react'
import { FileSpreadsheet, UploadCloud } from 'lucide-react'

export default function Dropzone({ onFile, disabled, maxMb, accept }: {
  onFile: (file: File) => void; disabled?: boolean; maxMb: number; accept: string[]
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const pick = (files: FileList | null) => { const f = files?.[0]; if (f) onFile(f) }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); if (!disabled) pick(e.dataTransfer.files) }
  return (
    <div className={`dropzone ${over ? 'is-over' : ''} ${disabled ? 'is-disabled' : ''}`}
      onDragOver={e => { e.preventDefault(); if (!disabled) setOver(true) }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
      <FileSpreadsheet size={28} aria-hidden="true" />
      <strong>Drag and drop a spreadsheet here</strong>
      <span>Excel ({accept.filter(a => a !== '.csv').join(', ')}) or CSV · up to {maxMb} MB</span>
      <button type="button" className="button button-secondary" disabled={disabled} onClick={() => input.current?.click()}>
        <UploadCloud size={16} /> Choose file
      </button>
      <input ref={input} type="file" className="sr-only" tabIndex={-1} aria-label="Choose a spreadsheet file to import" data-testid="file-input"
        accept={accept.join(',')} disabled={disabled} onChange={e => { pick(e.target.files); e.target.value = '' }} />
    </div>
  )
}
