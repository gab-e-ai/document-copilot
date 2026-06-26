interface CitationData {
  chunk_id: string
  excerpt: string
  company: string
  filing_type: string
  filing_date: string
  accession_number: string
}

interface Props {
  citation: CitationData
  index: number
}

export function CitationCard({ citation, index }: Props) {
  const dateLabel = citation.filing_date
    ? new Date(citation.filing_date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : citation.filing_date

  return (
    <div className="border border-gray-200 rounded-md p-3 text-xs text-gray-700 space-y-1">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-violet-100 text-violet-700 font-semibold text-xs shrink-0">
          {index}
        </span>
        <span className="font-medium">{citation.company}</span>
        <span className="text-gray-400">·</span>
        <span className="text-gray-500">{citation.filing_type}</span>
        <span className="text-gray-400">·</span>
        <span className="text-gray-500">{dateLabel}</span>
      </div>
      <p className="text-gray-600 italic leading-relaxed pl-7">"{citation.excerpt}"</p>
    </div>
  )
}
