import { columnLetter, type Issue } from '../../lib/importLogic'

export default function PreviewTable({ headers, rows, fieldLabels, issueIndex, flaggedRows }: {
  headers: string[]; rows: { row: number; cells: string[] }[]
  /** Label of the student field each column is mapped to (undefined when not imported). */
  fieldLabels: (string | undefined)[]; issueIndex?: Map<string, Issue[]>; flaggedRows?: Set<number>
}) {
  return (
    <div className="preview-scroll" tabIndex={0} role="region" aria-label="Spreadsheet preview. Use arrow keys to scroll.">
      <table className="preview-table">
        <thead>
          <tr>
            <th scope="col" className="row-no">Row</th>
            {headers.map((h, i) => (
              <th scope="col" key={i}>
                <span className="col-letter">{columnLetter(i)}</span>
                <span className="col-name">{h}</span>
                <span className={`col-target ${fieldLabels[i] ? '' : 'is-none'}`}>{fieldLabels[i] ? `→ ${fieldLabels[i]}` : 'Not imported'}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.row} className={flaggedRows?.has(r.row) ? 'row-flagged' : undefined}>
              <th scope="row" className="row-no num">{r.row}</th>
              {r.cells.map((cell, c) => {
                const problems = issueIndex?.get(`${r.row}:${c}`)
                return (
                  <td key={c} className={problems ? 'cell-invalid' : cell === '' ? 'cell-empty' : undefined}
                    title={problems?.map(p => p.message).join(' ')} aria-invalid={problems ? true : undefined}>
                    {cell === '' ? '—' : cell}
                    {problems && <span className="sr-only"> Error: {problems.map(p => p.message).join(' ')}</span>}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
