// The RAGcat mascot: the mark's cat in reading glasses, as hand-drawn line art
// (web/public/cat/*.webp; each file's generation prompt sits beside it in <name>.webp.json).
// It appears at key moments only: the landing, empty states, reading, publish success.
// Working surfaces such as the Review workspace stay without these illustrations; there the cat
// appears only as the Mark in the Assistant's avatar. Always decorative.

export type CatPose = 'sit' | 'point' | 'read' | 'cheer' | 'sleep'

// Intrinsic sizes of the artwork, so the page reserves the right box before it loads.
const ART: Record<CatPose, [number, number]> = {
  sit: [268, 480],
  point: [316, 444], // leans in from the right; the right edge cuts through its body
  read: [257, 480],
  cheer: [339, 480],
  sleep: [453, 355],
}

export function Cat({ pose = 'sit', size = 120, eager = false, className }: { pose?: CatPose; size?: number; eager?: boolean; className?: string }) {
  const [w, h] = ART[pose]
  return (
    <img
      className={className ? `cat ${className}` : 'cat'}
      src={`/cat/${pose}.webp`}
      width={size}
      height={Math.round((size * h) / w)}
      alt=""
      aria-hidden="true"
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      draggable={false}
    />
  )
}
